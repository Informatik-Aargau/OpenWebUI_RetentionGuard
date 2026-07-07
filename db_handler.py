"""
Database Handler for RetentionGuard
Provides methods to record batch executions and deleted users to the analytics database.
"""

import os
import logging
import psycopg2
import pandas as pd
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get logger for this module
logger = logging.getLogger(__name__)

# Target database connection (Analytics/KPI data)
TARGET_DB_CONFIG = {
    "host": os.getenv("TARGET_DB_HOST", "#[.....]"),
    "port": os.getenv("TARGET_DB_PORT", "#[.....]"),
    "database": os.getenv("TARGET_DB_NAME", "#[.....]"),
    "user": os.getenv("TARGET_DB_USER"),
    "password": os.getenv("TARGET_DB_PASSWORD"),
}


def get_connection():
    """Create a database connection to the target analytics database."""
    return psycopg2.connect(**TARGET_DB_CONFIG)


def start_batch_execution() -> Optional[int]:
    """
    Start a new batch execution record.
    
    Returns:
        The batch_id of the newly created record, or None on error
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.retentionguard_batch_execution (start)
                VALUES (CURRENT_TIMESTAMP)
                RETURNING id
            """)
            batch_id = cur.fetchone()[0]
        conn.commit()
        logger.info(f"Started batch execution with ID: {batch_id}")
        return batch_id
    except Exception as e:
        logger.error(f"Failed to start batch execution: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def end_batch_execution(batch_id: int, deletions_count: int, exit_code: int,
                       chat_deletions_count: int = 0, file_deletions_count: int = 0) -> bool:
    """
    End a batch execution record by updating the end timestamp, duration, deletions count, and exit code.
    
    Args:
        batch_id: The ID of the batch execution to end
        deletions_count: Number of users deleted in this batch
        exit_code: Exit code of the batch execution (0 for success)
        chat_deletions_count: Number of chats deleted in this batch
        file_deletions_count: Number of files deleted in this batch
    
    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.retentionguard_batch_execution
                SET "end" = CURRENT_TIMESTAMP,
                    duration = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start))::INTEGER,
                    deletions_count = %s,
                    chat_deletions_count = %s,
                    file_deletions_count = %s,
                    exit_code = %s
                WHERE id = %s
            """, (deletions_count, chat_deletions_count, file_deletions_count, exit_code, batch_id))
        conn.commit()
        logger.info(f"Ended batch execution {batch_id} with {deletions_count} user deletions, {chat_deletions_count} chat deletions, {file_deletions_count} file deletions and exit code {exit_code}")
        return True
    except Exception as e:
        logger.error(f"Failed to end batch execution {batch_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def record_deleted_user(batch_id: int, user_id: str, reason: str) -> bool:
    """
    Record a single deleted user.
    
    Args:
        batch_id: The ID of the batch execution
        user_id: The ID of the deleted user
        reason: The reason for deletion
    
    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.retentionguard_deleted (batch_id, user_id, reason)
                VALUES (%s, %s, %s)
            """, (batch_id, user_id, reason))
        conn.commit()
        logger.debug(f"Recorded deleted user {user_id} for batch {batch_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to record deleted user {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def record_deleted_users_bulk(batch_id: int, df_deleted: pd.DataFrame) -> int:
    """
    Record multiple deleted users in bulk.
    
    Args:
        batch_id: The ID of the batch execution
        df_deleted: DataFrame with columns 'id' (user_id) and 'deletion_reason'
    
    Returns:
        Number of successfully recorded deletions
    """
    if df_deleted.empty:
        logger.info("No deleted users to record")
        return 0
    
    # Neue gewünschte Spalten
    required_columns = [
        'id', 'name', 'email', 'role', 'created_at', 'updated_at', 'last_active_at', 'settings', 'deletion_reason'
    ]
    missing_columns = [col for col in required_columns if col not in df_deleted.columns]
    if missing_columns:
        logger.error(f"Missing required columns in DataFrame: {missing_columns}")
        return 0

    conn = None
    recorded_count = 0

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            for _, row in df_deleted.iterrows():
                try:
                    cur.execute("""
                        INSERT INTO public.retentionguard_deleted (
                            batch_id, user_id, "name", email, "role", created_at, updated_at, last_active_at, settings, reason
                        ) VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), to_timestamp(%s), %s, %s)
                    """,
                    (
                        batch_id,
                        str(row['id']),
                        row['name'],
                        row['email'],
                        row['role'],
                        row['created_at'],
                        row['updated_at'],
                        row['last_active_at'],
                        row['settings'],
                        str(row['deletion_reason'])
                    ))
                    recorded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to record deletion for user {row['id']}: {e}")

        conn.commit()
        logger.info(f"Recorded {recorded_count} deleted users for batch {batch_id}")
        return recorded_count

    except Exception as e:
        logger.error(f"Failed to record deleted users in bulk: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()


def get_batch_execution(batch_id: int) -> Optional[dict]:
    """
    Retrieve a batch execution record by ID.
    
    Args:
        batch_id: The ID of the batch execution
    
    Returns:
        Dictionary with batch execution data, or None if not found
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, start, "end", duration, deletions_count, exit_code
                FROM public.retentionguard_batch_execution
                WHERE id = %s
            """, (batch_id,))
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'start': row[1],
                    'end': row[2],
                    'duration': row[3],
                    'deletions_count': row[4],
                    'exit_code': row[5]
                }
            return None
    except Exception as e:
        logger.error(f"Failed to get batch execution {batch_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()
