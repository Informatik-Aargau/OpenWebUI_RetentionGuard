"""
Database Setup Script
Creates the required tables and indexes for the KPI analytics database.
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

# Target database connection (Analytics/KPI data)
TARGET_DB_CONFIG = {
    "host": os.getenv("TARGET_DB_HOST", "localhost"),
    "port": os.getenv("TARGET_DB_PORT", "5432"),
    "database": os.getenv("TARGET_DB_NAME", "#[.....]"),
    "user": os.getenv("TARGET_DB_USER"),
    "password": os.getenv("TARGET_DB_PASSWORD"),
}

# SQL statements to create tables and indexes
CREATE_TABLES_SQL = """
-- Batch execution tracking table
CREATE TABLE IF NOT EXISTS public.retentionguard_batch_execution (
    id SERIAL PRIMARY KEY,
    start TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "end" TIMESTAMP,
    duration INTEGER,  -- duration in seconds
    deletions_count INTEGER,
    chat_deletions_count INTEGER,
    file_deletions_count INTEGER,
    exit_code INTEGER
);

-- Deletion table
CREATE TABLE IF NOT EXISTS public.retentionguard_deleted (
    id SERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES public.retentionguard_batch_execution(id),
    user_id VARCHAR(255) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    name TEXT,
    email TEXT,
    role TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_active_at TIMESTAMP,
    settings JSONB
);
"""


def get_connection(config: dict):
    """Create a database connection."""
    return psycopg2.connect(**config)


def create_tables():
    """Create all required tables and indexes."""
    print("Connecting to target database...")
    conn = None
    
    try:
        conn = get_connection(TARGET_DB_CONFIG)
        
        print("Creating tables and indexes...")
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES_SQL)
        
        conn.commit()
        print("Database setup completed successfully!")
        return 0
        
    except Exception as e:
        print(f"Error during database setup: {e}", file=sys.stderr)
        if conn:
            conn.rollback()
        return 1
        
    finally:
        if conn:
            conn.close()
