import os
import requests
import logging
import pandas as pd
from typing import Optional

# Get logger for this module
logger = logging.getLogger(__name__)


def get_all_user_infos() -> Optional[pd.DataFrame]:
    """
    Retrieve all user information from the OpenWebUI REST API.
    Handles pagination to fetch all users across multiple pages.
    
    Returns:
        DataFrame with columns ['id', 'email', 'role', 'updated_at', 'last_active_at'], or None on error
    """
    
    base_api_url = os.getenv("OPENAI_API_USER")
    bearer_token = os.getenv("OPENAI_API_KEY")
    
    if not base_api_url:
        logger.error("OPENAI_API_USER environment variable not set")
        return None
    
    if not bearer_token:
        logger.error("OPENAI_API_KEY environment variable not set")
        return None
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    
    try:
        all_users = []
        page = 1
        total_users = None
        
        while True:
            # Construct URL with page parameter
            api_url = f"{base_api_url}/?page={page}"
            
            logger.info(f"Fetching users from OpenWebUI API (page {page})")
            logger.debug(f"Request URL: {api_url}")
            
            response = requests.get(api_url, headers=headers)
            
            logger.debug(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'users' not in data:
                    logger.error(f"Response does not contain 'users' field on page {page}")
                    return None
                
                users = data['users']
                total = data.get('total', 0)
                
                # Store total on first iteration
                if total_users is None:
                    total_users = total
                    logger.info(f"Total users to fetch: {total_users}")
                
                logger.info(f"Fetched {len(users)} users on page {page} (total collected: {len(all_users) + len(users)}/{total_users})")
                
                # If no users returned, we've reached the end
                if not users:
                    logger.info(f"No more users returned on page {page}, stopping pagination")
                    break
                
                # Add users from this page to our collection
                all_users.extend(users)
                
                # Check if we've collected all users
                if len(all_users) >= total_users:
                    logger.info(f"Collected all {len(all_users)} users")
                    break
                
                # Move to next page
                page += 1
                
            else:
                logger.error(f"Failed to fetch users on page {page}. Status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
        
        logger.info(f"Successfully fetched {len(all_users)} users across {page} page(s)")
        
        if not all_users:
            logger.warning("No users returned from API")
            return pd.DataFrame(columns=['id', 'email', 'role', 'updated_at', 'last_active_at'])
        
        # Convert to DataFrame
        df = pd.DataFrame(all_users)

        # Neue gewünschte Reihenfolge und zusätzliche Felder
        required_columns = ['id', 'name', 'email', 'role', 'created_at', 'updated_at', 'last_active_at', 'settings']

        # Ensure all required columns exist
        for col in required_columns:
            if col not in df.columns:
                logger.warning(f"Column '{col}' not found in API response, adding with None values")
                df[col] = None

        # Select and reorder columns
        df = df[required_columns]

        # Remove rows with null emails
        df = df[df['email'].notna()]

        logger.info(f"Returning {len(df)} users with valid emails")
        logger.debug(f"First few rows: {df.head()}")

        return df
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error while fetching users: {str(e)}")
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error while fetching users: {str(e)}")
        return None


def delete_user(user_id: str, email: str = None, dry_run: bool = True) -> pd.DataFrame:
    """
    Delete user from the OpenWebUI REST API.
    
    Args:
        user_id: ID of the user to delete
        email: Email address of the user (for logging purposes)
        dry_run: If True, only simulate the deletion without actually making the API call (default: True)
        
    Returns:
        DataFrame with deletion result, or empty DataFrame on error
    """
    
    api_url = os.getenv("OPENAI_API_USER")
    bearer_token = os.getenv("OPENAI_API_KEY")
    
    if not api_url:
        logger.error("OPENAI_API_USER environment variable not set")
        return pd.DataFrame()
    
    if not bearer_token:
        logger.error("OPENAI_API_KEY environment variable not set")
        return pd.DataFrame()
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    
    # Construct the full URL with user_id parameter
    url = f"{api_url}/{user_id}"
    
    # Prepare user identifier for logging
    user_identifier = f"{email} (ID: {user_id})" if email else f"ID: {user_id}"
    
    try:
        if dry_run:
            logger.warning(f"DRY RUN: Would delete user {user_identifier}")
            logger.info(f"DRY RUN: DELETE request would be sent to: {url}")
            # Return a DataFrame indicating this was a dry run
            result = {
                "user_id": user_id,
                "email": email,
                "action": "delete",
                "dry_run": True,
                "status": "simulated",
                "message": "Dry run - no actual deletion performed"
            }
            return pd.DataFrame([result])
        
        logger.info(f"Deleting user {user_identifier}")
        logger.debug(f"Request URL: {url}")
        
        response = requests.delete(url, headers=headers)
        
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response content: {response.text}")
        
        if response.status_code == 200:
            # Check if response has content before parsing
            if not response.text or response.text.strip() == "":
                logger.info(f"User {user_identifier} deleted successfully (empty response)")
                result = {
                    "user_id": user_id,
                    "email": email,
                    "action": "delete",
                    "dry_run": False,
                    "status": "success",
                    "message": "User deleted successfully"
                }
                return pd.DataFrame([result])
            
            try:
                response_data = response.json()
            except requests.exceptions.JSONDecodeError as json_err:
                logger.warning(f"Could not parse JSON response for {user_identifier}, but status was 200: {json_err}")
                result = {
                    "user_id": user_id,
                    "email": email,
                    "action": "delete",
                    "dry_run": False,
                    "status": "success",
                    "message": "User deleted (response not JSON)"
                }
                return pd.DataFrame([result])
            
            logger.info(f"Successfully deleted user {user_identifier}")
            logger.debug(f"Response data: {response_data}")
            
            # Convert to DataFrame
            if isinstance(response_data, dict):
                response_data['user_id'] = user_id
                response_data['email'] = email
                response_data['action'] = 'delete'
                response_data['dry_run'] = False
                df = pd.DataFrame([response_data])
            elif isinstance(response_data, list):
                df = pd.DataFrame(response_data)
                df['user_id'] = user_id
                df['email'] = email
            else:
                logger.warning(f"Unexpected response format: {type(response_data)}")
                result = {
                    "user_id": user_id,
                    "email": email,
                    "action": "delete",
                    "dry_run": False,
                    "status": "success",
                    "message": str(response_data)
                }
                return pd.DataFrame([result])
            
            return df
            
        else:
            logger.error(f"Failed to delete user {user_identifier}. Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            result = {
                "user_id": user_id,
                "email": email,
                "action": "delete",
                "dry_run": False,
                "status": "failed",
                "status_code": response.status_code,
                "message": response.text
            }
            return pd.DataFrame([result])
            
    except Exception as e:
        logger.error(f"Error deleting user {user_identifier}: {str(e)}")
        result = {
            "user_id": user_id,
            "email": email,
            "action": "delete",
            "dry_run": dry_run,
            "status": "error",
            "message": str(e)
        }
        return pd.DataFrame([result])


def delete_users_bulk(df_users: pd.DataFrame, dry_run: bool = True) -> pd.DataFrame:
    """
    Delete multiple users from the OpenWebUI REST API.
    
    Args:
        df_users: DataFrame containing user data with 'id' and 'email' columns
        dry_run: If True, only simulate the deletions without actually making API calls (default: True)
        
    Returns:
        DataFrame with deletion results for all users
    """
    
    if df_users.empty:
        logger.warning("Empty DataFrame provided for bulk deletion")
        return pd.DataFrame()
    
    if 'id' not in df_users.columns:
        logger.error("DataFrame must contain 'id' column")
        return pd.DataFrame()
    
    # Email column is optional but recommended
    has_email = 'email' in df_users.columns
    
    logger.info(f"Starting bulk deletion of {len(df_users)} users (dry_run={dry_run})")
    
    results = []
    for idx, row in df_users.iterrows():
        user_id = row['id']
        email = row['email'] if has_email else None
        
        result_df = delete_user(user_id, email=email, dry_run=dry_run)
        results.append(result_df)
    
    # Combine all results into single DataFrame
    if results:
        df_results = pd.concat(results, ignore_index=True)
        
        # Log summary
        if dry_run:
            logger.info(f"DRY RUN: Simulated deletion of {len(df_results)} users")
        else:
            success_count = len(df_results[df_results['status'] == 'success'])
            failed_count = len(df_results[df_results['status'] == 'failed'])
            error_count = len(df_results[df_results['status'] == 'error'])
            logger.info(f"Bulk deletion complete: {success_count} successful, {failed_count} failed, {error_count} errors")
        
        return df_results
    else:
        return pd.DataFrame()
