import os
import logging
import sys
import pandas as pd
from datetime import date, timedelta, datetime
from dotenv import find_dotenv, load_dotenv
from logging_utils import setup_logging
import mdm_handler
import postgres_handler
import openwebui_handler
import chat_handler
import file_handler
import db_handler
from create_db import create_tables

# Get logger for this module
logger = logging.getLogger(__name__)

def main():
    load_dotenv(find_dotenv())
    # Set up logging (can be configured via environment variable)
    log_level = os.getenv("LOG_LEVEL", "INFO")

    setup_logging(log_level)
    
    logger.critical("Starting aargaugpt-retentionguard application")
    
    # Example of different log levels
    logger.critical("This critical log Message gets followed by one message at every level error->warning->info->debug. Depending on the setting of LOG_LEVEL, some of these may not appear.")
    logger.error("This is an error message")
    logger.warning("This is a warning message")
    logger.info("This is an info message")
    logger.debug("This is a debug message")

    logger.debug(f"TEST_ENV_VAR: {os.getenv('TEST_ENV_VAR')}")

    # Ensure database tables exist
    exit_code = create_tables()
    if exit_code != 0:
        sys.exit(exit_code)

    # Start batch execution tracking
    batch_id = db_handler.start_batch_execution()
    if batch_id is None:
        logger.error("Failed to start batch execution tracking")
        sys.exit(1)
    
    deletions_count = 0
    batch_exit_code = 0

    #Get the list of users from PostgreSQL database
    #df_users = postgres_handler.get_all_user_emails()
    df_users = openwebui_handler.get_all_user_infos()
    
    if df_users is None or df_users.empty:
        logger.error("No users retrieved from database")
        return
    
    # Extract email list for API calls
    emails = df_users['email'].tolist()

    # Get user data (active counts and latest Austrittsdatum per email) in one bulk operation
    df = mdm_handler.get_user_data_bulk(emails)
    
    if not df.empty:
        # Merge id und alle gewünschten Felder aus OpenWebUI
        df = df.merge(
            df_users[['id', 'name', 'email', 'role', 'created_at', 'updated_at', 'last_active_at', 'settings']],
            on='email', how='left')
        
        # Convert timestamps to datetime for comparison
        df['updated_at_dt'] = pd.to_datetime(df['updated_at'], unit='s', errors='coerce')
        df['last_active_at_dt'] = pd.to_datetime(df['last_active_at'], unit='s', errors='coerce')
        
        # Get the most recent activity timestamp
        df['last_activity'] = df[['updated_at_dt', 'last_active_at_dt']].max(axis=1)
        
        # Reorder columns to have id first (für CSV-Ausgabe, nicht für DB)
        columns = ['id', 'name', 'email', 'count', 'austrittsdatum', 'role', 'created_at', 'updated_at', 'last_active_at', 'settings', 'last_activity']
        df = df[columns]
        
        # Sort by count first, then by email
        df = df.sort_values(by=['count', 'email'])
        
        # Calculate thresholds
        mdm_threshold = (date.today() - timedelta(int(os.getenv("DELETE_AFTER_DAYS_INACTIVE", "62")))).isoformat() # Austritt mit bestehender Email.
        pending_threshold = datetime.now() - timedelta(days=int(os.getenv("DELETE_AFTER_DAYS_INACTIVE", "62")))
        #no_mdm_account_threshold = datetime.now() - timedelta(days=2) #Schliesst aus, dass neue Nutzer gelöscht werden, bevor sie überhaupt ein MDM-Konto haben. 2 Tage Puffer ab Erstellungsdatum.
        no_mdm_account_threshold = datetime.now() - timedelta(days=int(os.getenv("DELETE_AFTER_DAYS_INACTIVE", "62"))) # Schliesst aus, dass neue Nutzer gelöscht werden, bevor sie überhaupt ein MDM-Konto haben.
                                                                                                                       # Schliesst ebenfalls aus, dass Nutzer mit gelöschter Email in MDM, noch aufbewahrt werden.
                                                                                                                       # Austritt mit gelöschter Email.
        
        # Create dataframe with inactive users with deletion reasons
        df['deletion_reason'] = ''
        
        # Condition 1: No active MDM account (count < 1) with austrittsdatum in the past
        mdm_inactive = (
            (df['count'] < 1) & 
            (df['austrittsdatum'].notna() & (df['austrittsdatum'] < mdm_threshold))
        )
        df.loc[mdm_inactive, 'deletion_reason'] = 'No active MDM account'

        # Condition 2: No MDM account at all (count == 0) AND austrittsdatum is NA
        mdm_no_account = (
            (df['count'] < 1) & 
            (df['austrittsdatum'].isna()) & 
            (df['last_activity'] < no_mdm_account_threshold)
        )
        df.loc[mdm_no_account & (df['deletion_reason'] != ''), 'deletion_reason'] += ' + No MDM account at all'
        df.loc[mdm_no_account & (df['deletion_reason'] == ''), 'deletion_reason'] = 'No MDM account at all'
        
        # Condition 3: Pending user inactive for more than 31 days
        logger.debug(f"Calculating pending user inactivity with threshold: {pending_threshold}, last_activity sample: {df['last_activity'].tail(5)}")
        pending_inactive = (
            (df['role'] == 'pending') & 
            (df['last_activity'].notna()) & 
            (df['last_activity'] < pending_threshold)
        )

        df.loc[pending_inactive & (df['deletion_reason'] != ''), 'deletion_reason'] += ' + Pending user inactive for >31 days'
        df.loc[pending_inactive & (df['deletion_reason'] == ''), 'deletion_reason'] = 'Pending user inactive for >31 days'
        
        
        # Filter for users with any deletion reason
        df_inactive_users = df[df['deletion_reason'] != ''].copy()
        
        logger.info(f"Found {len(df_inactive_users)} inactive users:")
        logger.info(f"  - MDM inactive (austrittsdatum < {mdm_threshold}): {len(df[mdm_inactive])}")
        logger.info(f"  - No MDM account at all: {len(df[mdm_no_account])}")
        logger.info(f"  - Pending inactive (>31 days): {len(df[pending_inactive])}")

        # Save results to CSV file with semicolon delimiter
        output_file = "/outputs/user_counts_overwrite.csv"
        output_file_inactive = "/outputs/inactive_user_counts_overwrite.csv"
        try:
            if os.getenv("CREATE_OUTPUT_CSVS", "0") == "1":
                df.to_csv(output_file, sep=';', index=False, encoding='utf-8')
                df_inactive_users.to_csv(output_file_inactive, sep=';', index=False, encoding='utf-8')
                logger.info(f"Successfully saved {len(df)} user counts to {output_file}")
                logger.info(f"Successfully saved {len(df_inactive_users)} inactive user counts and Austrittsdatum to {output_file_inactive}")
        except Exception as e:
            logger.error(f"Failed to save user counts to CSV: {str(e)}")

        # Delete all inactive users from OpenWebUI (dry run by default)
        if not df_inactive_users.empty:
            logger.info(f"Processing {len(df_inactive_users)} inactive users for deletion from OpenWebUI")
            dry_run = bool(int(os.getenv("DELETE_DRY_RUN", "1")))
            
            # Safety check: force dry_run if deletion count exceeds threshold
            dry_run_threshold_enabled = bool(int(os.getenv("DRY_RUN_IF_MORE_THAN_N_DELETIONS", "1")))
            dry_run_threshold = int(os.getenv("DRY_RUN_IF_MORE_THAN_N_USER_DELETIONS", "30"))
            
            if dry_run_threshold_enabled and len(df_inactive_users) > dry_run_threshold:
                logger.warning(f"Deletion count ({len(df_inactive_users)}) exceeds threshold ({dry_run_threshold}). Forcing dry_run mode.")
                dry_run = True
            
            logger.info(f"Dry run mode is {'enabled' if dry_run else 'disabled'}")
            df_delete_results = openwebui_handler.delete_users_bulk(df_inactive_users, dry_run=dry_run)
            print("\n=== OpenWebUI Bulk Delete Results ===")
            print(df_delete_results)
            print("====================================\n")
            
            # Record deletions to database (only for actual deletions, not dry runs)
            if not dry_run and not df_delete_results.empty:
                # Filter for successful deletions
                df_successful = df_delete_results[df_delete_results['status'] == 'success']
                deletions_count = len(df_successful)
                
                # Merge alle gewünschten Felder für DB-Logging
                merge_cols = [
                    'id', 'name', 'email', 'role', 'created_at', 'updated_at', 'last_active_at', 'settings', 'deletion_reason'
                ]
                df_to_record = df_successful.merge(
                    df_inactive_users[merge_cols],
                    left_on='user_id',
                    right_on='id',
                    how='left',
                    suffixes=('', '_inactive')
                )
                # Setze die id-Spalte korrekt (user_id → id)
                df_to_record['id'] = df_to_record['user_id']
                # Nur die gewünschten Spalten für DB-Logging
                df_to_record = df_to_record[merge_cols]

                # Record deleted users to database
                recorded = db_handler.record_deleted_users_bulk(batch_id, df_to_record)
                logger.info(f"Recorded {recorded} deletions to database")
    
    # ===== Chat Cleanup: Delete old non-archived chats =====
    chat_deletions_count = 0
    df_old_chats = chat_handler.get_old_non_archived_chats()

    if df_old_chats is not None and not df_old_chats.empty:
        logger.info(f"Processing {len(df_old_chats)} old non-archived chats for deletion")
        dry_run = bool(int(os.getenv("DELETE_DRY_RUN", "1")))

        # Safety check: force dry_run if deletion count exceeds threshold
        dry_run_threshold_enabled = bool(int(os.getenv("DRY_RUN_IF_MORE_THAN_N_DELETIONS", "1")))
        dry_run_threshold = int(os.getenv("DRY_RUN_IF_MORE_THAN_N_CHAT_DELETIONS", "100"))

        if dry_run_threshold_enabled and len(df_old_chats) > dry_run_threshold:
            logger.warning(f"Chat deletion count ({len(df_old_chats)}) exceeds threshold ({dry_run_threshold}). Forcing dry_run mode.")
            dry_run = True

        logger.info(f"Chat cleanup dry run mode is {'enabled' if dry_run else 'disabled'}")
        df_chat_delete_results = chat_handler.delete_chats_bulk(df_old_chats, dry_run=dry_run)
        print("\n=== OpenWebUI Bulk Chat Delete Results ===")
        print(df_chat_delete_results)
        print("==========================================\n")

        if not dry_run and not df_chat_delete_results.empty:
            df_successful_chats = df_chat_delete_results[df_chat_delete_results['status'] == 'success']
            chat_deletions_count = len(df_successful_chats)
            logger.info(f"Successfully deleted {chat_deletions_count} chats")
    else:
        logger.info("No old non-archived chats found for deletion")

    # ===== File Cleanup: Delete orphaned files =====
    file_deletions_count = 0
    df_orphaned_files = file_handler.get_orphaned_files()

    if df_orphaned_files is not None and not df_orphaned_files.empty:
        logger.info(f"Processing {len(df_orphaned_files)} orphaned files for deletion")
        dry_run = bool(int(os.getenv("DELETE_DRY_RUN", "1")))

        # Safety check: force dry_run if deletion count exceeds threshold
        dry_run_threshold_enabled = bool(int(os.getenv("DRY_RUN_IF_MORE_THAN_N_DELETIONS", "1")))
        dry_run_threshold = int(os.getenv("DRY_RUN_IF_MORE_THAN_N_FILE_DELETIONS", "100"))

        if dry_run_threshold_enabled and len(df_orphaned_files) > dry_run_threshold:
            logger.warning(f"File deletion count ({len(df_orphaned_files)}) exceeds threshold ({dry_run_threshold}). Forcing dry_run mode.")
            dry_run = True

        logger.info(f"File cleanup dry run mode is {'enabled' if dry_run else 'disabled'}")
        df_file_delete_results = file_handler.delete_files_bulk(df_orphaned_files, dry_run=dry_run)
        print("\n=== OpenWebUI Bulk File Delete Results ===")
        print(df_file_delete_results)
        print("==========================================\n")

        if not dry_run and not df_file_delete_results.empty:
            df_successful_files = df_file_delete_results[df_file_delete_results['status'] == 'success']
            file_deletions_count = len(df_successful_files)
            logger.info(f"Successfully deleted {file_deletions_count} orphaned files")
    else:
        logger.info("No orphaned files found for deletion")

    # End batch execution tracking
    db_handler.end_batch_execution(batch_id, deletions_count, batch_exit_code,
                                   chat_deletions_count=chat_deletions_count,
                                   file_deletions_count=file_deletions_count)

if __name__ == "__main__":
    main()
