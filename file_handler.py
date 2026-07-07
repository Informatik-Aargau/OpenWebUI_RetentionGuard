import os
import logging
import requests
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

# Get logger for this module
logger = logging.getLogger(__name__)


def get_orphaned_files() -> Optional[pd.DataFrame]:
    """
    Retrieve files from the PostgreSQL database that are not referenced
    by any chat, knowledge base, or channel, and older than the configured
    threshold (DELETE_FILES_OLDER_THAN_DAYS, default 92).

    Returns:
        DataFrame with column ['id'], or None on error
    """
    connection = None
    cursor = None

    try:
        db_config = {
            "dbname": os.getenv("SOURCE_DB_NAME"),
            "user": os.getenv("TARGET_DB_USER"),
            "password": os.getenv("TARGET_DB_PASSWORD"),
            "host": os.getenv("TARGET_DB_HOST"),
            "port": os.getenv("TARGET_DB_PORT")
        }

        missing_vars = [key for key, value in db_config.items() if not value]
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            return None

        days = int(os.getenv("DELETE_FILES_OLDER_THAN_DAYS", "92"))
        threshold_epoch = int((datetime.now() - timedelta(days=days)).timestamp())

        logger.debug(f"Connecting to database {db_config['dbname']} at {db_config['host']}:{db_config['port']}")

        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()

        query = """
            SELECT T1.id
            FROM public.file T1
            LEFT JOIN public.chat_file T2 ON T1.id = T2.file_id
            LEFT JOIN public.knowledge_file T3 ON T1.id = T3.file_id
            LEFT JOIN public.channel_file T4 ON T1.id = T4.file_id
            WHERE T2.file_id IS NULL AND T3.file_id IS NULL AND T4.file_id IS NULL
                AND T1.created_at < %s
        """
        logger.debug(f"Executing orphaned files query with threshold epoch: {threshold_epoch} ({datetime.fromtimestamp(threshold_epoch).isoformat()})")
        cursor.execute(query, (threshold_epoch,))

        results = cursor.fetchall()

        df = pd.DataFrame(results, columns=['id'])

        logger.info(f"Found {len(df)} orphaned files older than {days} days (not referenced by any chat, knowledge base, or channel)")
        logger.debug(f"First few rows: {df.head()}")

        return df

    except psycopg2.Error as e:
        logger.error(f"Database error while fetching orphaned files: {str(e)}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error while fetching orphaned files: {str(e)}")
        return None

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _get_api_base_url() -> Optional[str]:
    """Derive the base API URL from OPENAI_API_USER (e.g. https://host/api/v1/users -> https://host/api/v1)."""
    api_user_url = os.getenv("OPENAI_API_USER")
    if not api_user_url:
        logger.error("OPENAI_API_USER environment variable not set")
        return None
    base = api_user_url.rstrip("/")
    if base.endswith("/users"):
        base = base[:-len("/users")]
    return base


def delete_file(file_id: str, dry_run: bool = True) -> pd.DataFrame:
    """
    Delete a single file from OpenWebUI via the REST API.

    Args:
        file_id: ID of the file to delete
        dry_run: If True, only simulate the deletion (default: True)

    Returns:
        DataFrame with deletion result
    """
    base_url = _get_api_base_url()
    bearer_token = os.getenv("OPENAI_API_KEY")

    if not base_url or not bearer_token:
        if not bearer_token:
            logger.error("OPENAI_API_KEY environment variable not set")
        return pd.DataFrame()

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "accept": "application/json"
    }

    url = f"{base_url}/files/{file_id}"

    try:
        if dry_run:
            logger.warning(f"DRY RUN: Would delete file {file_id}")
            logger.info(f"DRY RUN: DELETE request would be sent to: {url}")
            return pd.DataFrame([{
                "file_id": file_id,
                "action": "delete_file",
                "dry_run": True,
                "status": "simulated",
                "message": "Dry run - no actual deletion performed"
            }])

        logger.info(f"Deleting file {file_id}")
        logger.debug(f"Request URL: {url}")

        response = requests.delete(url, headers=headers)

        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response content: {response.text}")

        if response.status_code == 200:
            logger.info(f"Successfully deleted file {file_id}")
            return pd.DataFrame([{
                "file_id": file_id,
                "action": "delete_file",
                "dry_run": False,
                "status": "success",
                "message": "File deleted successfully"
            }])
        else:
            logger.error(f"Failed to delete file {file_id}. Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return pd.DataFrame([{
                "file_id": file_id,
                "action": "delete_file",
                "dry_run": False,
                "status": "failed",
                "status_code": response.status_code,
                "message": response.text
            }])

    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {str(e)}")
        return pd.DataFrame([{
            "file_id": file_id,
            "action": "delete_file",
            "dry_run": dry_run,
            "status": "error",
            "message": str(e)
        }])


def delete_files_bulk(df_files: pd.DataFrame, dry_run: bool = True) -> pd.DataFrame:
    """
    Delete multiple files from OpenWebUI via the REST API.

    Args:
        df_files: DataFrame containing file data with 'id' column
        dry_run: If True, only simulate the deletions (default: True)

    Returns:
        DataFrame with deletion results for all files
    """
    if df_files.empty:
        logger.warning("Empty DataFrame provided for bulk file deletion")
        return pd.DataFrame()

    if 'id' not in df_files.columns:
        logger.error("DataFrame must contain 'id' column")
        return pd.DataFrame()

    logger.info(f"Starting bulk deletion of {len(df_files)} files (dry_run={dry_run})")

    results = []
    for _, row in df_files.iterrows():
        result_df = delete_file(str(row['id']), dry_run=dry_run)
        results.append(result_df)

    if results:
        df_results = pd.concat(results, ignore_index=True)

        if dry_run:
            logger.info(f"DRY RUN: Simulated deletion of {len(df_results)} files")
        else:
            success_count = len(df_results[df_results['status'] == 'success'])
            failed_count = len(df_results[df_results['status'] == 'failed'])
            error_count = len(df_results[df_results['status'] == 'error'])
            logger.info(f"Bulk file deletion complete: {success_count} successful, {failed_count} failed, {error_count} errors")

        return df_results
    else:
        return pd.DataFrame()
