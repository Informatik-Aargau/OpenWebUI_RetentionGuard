import os
import requests
import logging
import json
import pandas as pd
from datetime import date

# Get logger for this module
logger = logging.getLogger(__name__)

def get_user_data_bulk(emails: list[str]) -> pd.DataFrame:
    """
    Get active user counts and latest Austrittsdatum for multiple email addresses in bulk from MDM API endpoints.
    Checks both MDM_API_USER and MDM_API_USER_EGOV endpoints.
    Processes emails in chunks to avoid overwhelming the API.
    
    Args:
        emails: List of email addresses to check
        
    Returns:
        DataFrame with columns ['email', 'count', 'austrittsdatum'], or empty DataFrame on error
    """
    
    if not emails:
        logger.warning("Empty email list provided")
        return pd.DataFrame(columns=['email', 'count', 'austrittsdatum'])
    
    # Normalize all emails to lowercase for consistent comparison
    emails = [email.lower() for email in emails]
    
    # Get chunk size from environment variable, default to 100
    chunk_size = int(os.getenv("MDM_BULK_REQUEST_CHUNK_SIZE", "100"))
    logger.info(f"Processing {len(emails)} emails in chunks of {chunk_size}")
    
    headers = {
        "client_id": os.getenv("MDM_API_USER_CLIENT_ID"),
        "client_secret": os.getenv("MDM_API_USER_CLIENT_SECRET"),
        "Content-Type": "application/json"
    }

    today = date.today().isoformat()
    
    # Get API endpoints from environment variables
    api_urls = [
        ("MDM_API_USER", os.getenv("MDM_API_USER"), "Email", "Status", "Austrittsdatum"),
        ("MDM_API_USER_EGOV", os.getenv("MDM_API_USER_EGOV"), "email", "status", "austrittsdatum")
    ]
    
    # List to collect all user data DataFrames
    all_users_dfs = []
    
    # Split emails into chunks
    email_chunks = [emails[i:i + chunk_size] for i in range(0, len(emails), chunk_size)]
    logger.info(f"Split emails into {len(email_chunks)} chunks")
    
    for chunk_index, email_chunk in enumerate(email_chunks, 1):
        logger.debug(f"Processing chunk {chunk_index}/{len(email_chunks)} with {len(email_chunk)} emails")
        
        for api_name, api_url, email_field, status_field, austrittsdatum_field in api_urls:
            if not api_url:
                logger.error(f"API URL {api_name} not configured in environment variables")
                return pd.DataFrame(columns=['email', 'count', 'austrittsdatum'])
            
            # Build filter with email chunk for this specific API (get all records)
            filter_obj = {
                "where": {
                    email_field: {"inq": email_chunk}
                },
                "fields": {
                    email_field: True,
                    status_field: True,
                    austrittsdatum_field: True
                }
            }
            
            # Encode filter as JSON string for query parameter
            params = {
                "filter": json.dumps(filter_obj)
            }
            
            try:
                response = requests.get(api_url, headers=headers, params=params)
                logger.debug(f"Bulk request URL for {api_name} (chunk {chunk_index}): {response.url}")
                
                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"Fetched {len(user_data)} users from {api_name} (chunk {chunk_index})")
                    
                    # Convert to DataFrame immediately
                    if user_data:
                        df_users = pd.DataFrame(user_data)
                        # Normalize email column name and convert to lowercase
                        df_users = df_users.rename(columns={email_field: 'email', status_field: 'status', austrittsdatum_field: 'austrittsdatum'})
                        df_users['email'] = df_users['email'].str.lower()
                        all_users_dfs.append(df_users)
                            
                else:
                    logger.error(f"Failed to fetch users from {api_name} (chunk {chunk_index}). Status code: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return pd.DataFrame(columns=['email', 'count', 'austrittsdatum'])
            except Exception as e:
                logger.error(f"Error fetching data from {api_name} (chunk {chunk_index}): {str(e)}")
                return pd.DataFrame(columns=['email', 'count', 'austrittsdatum'])
    
    # Combine all DataFrames
    if all_users_dfs:
        df_combined = pd.concat(all_users_dfs, ignore_index=True)
        
        # Filter for active users and count them
        df_active = df_combined[
            ((df_combined['status'] == 1) & 
            (df_combined['austrittsdatum'] >= today)) |
            ((df_combined['status'] == 1) & 
            (df_combined['austrittsdatum'] == '9999-12-31'))
        ]
        df_counts = df_active.groupby('email').size().reset_index(name='count')
        
        # Get latest Austrittsdatum per email (from all records)
        if 'austrittsdatum' in df_combined.columns:
            df_austrittsdatum = df_combined.groupby('email')['austrittsdatum'].max().reset_index()
            df_austrittsdatum = df_austrittsdatum.rename(columns={'austrittsdatum': 'austrittsdatum'})
        else:
            df_austrittsdatum = pd.DataFrame(columns=['email', 'austrittsdatum'])
    else:
        df_counts = pd.DataFrame(columns=['email', 'count'])
        df_austrittsdatum = pd.DataFrame(columns=['email', 'austrittsdatum'])
    
    # Create DataFrame with all emails
    df_all_emails = pd.DataFrame({'email': emails})
    
    # Merge counts and austrittsdatum
    df_result = df_all_emails.merge(df_counts, on='email', how='left')
    df_result = df_result.merge(df_austrittsdatum, on='email', how='left')
    df_result['count'] = df_result['count'].fillna(0).astype(int)
    
    logger.info(f"Returning DataFrame with {len(df_result)} users (email, count, austrittsdatum)")
    return df_result
