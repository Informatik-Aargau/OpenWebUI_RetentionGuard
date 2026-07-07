import os
import logging
import psycopg2
import pandas as pd
from typing import Optional

# Get logger for this module
logger = logging.getLogger(__name__)


def get_all_user_emails() -> Optional[pd.DataFrame]:
    """
    Retrieve all user IDs and email addresses from the user table in the PostgreSQL database.
    
    Returns:
        DataFrame with columns ['id', 'email'], or None on error
    """
    connection = None
    cursor = None
    
    try:
        # Get database connection parameters from environment variables
        db_config = {
            "dbname": os.getenv("CONF_DB_NAME"),
            "user": os.getenv("CONF_DB_USER"),
            "password": os.getenv("CONF_DB_USER_PASSWORD"),
            "host": os.getenv("CONF_DB_HOST"),
            "port": os.getenv("CONF_DB_PORT")
        }
        
        # Validate that all required environment variables are set
        missing_vars = [key for key, value in db_config.items() if not value]
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            return None
        
        logger.debug(f"Connecting to database {db_config['dbname']} at {db_config['host']}:{db_config['port']}")
        
        # Establish connection to PostgreSQL
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()
        
        # Execute query to fetch id, email, role, updated_at, and last_active_at
        query = "SELECT id, email, role, updated_at, last_active_at FROM \"user\""
        logger.debug(f"Executing query: {query}")
        cursor.execute(query)
        
        # Fetch all results
        results = cursor.fetchall()
        
        # Convert to DataFrame
        df = pd.DataFrame(results, columns=['id', 'email', 'role', 'updated_at', 'last_active_at'])
        # Remove rows with null emails
        df = df[df['email'].notna()]
        
        logger.info(f"Successfully retrieved {len(df)} users (id, email, role, updated_at, last_active_at) from database")
        logger.debug(f"First few rows: {df.head()}")
        
        return df
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {str(e)}")
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error while fetching emails: {str(e)}")
        return None
        
    finally:
        # Clean up database resources
        if cursor:
            cursor.close()
            logger.debug("Database cursor closed")
        if connection:
            connection.close()
            logger.debug("Database connection closed")
