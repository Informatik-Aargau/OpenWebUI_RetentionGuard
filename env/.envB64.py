import base64
import requests
import os
import argparse
from dotenv import load_dotenv


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Encode .env file to Base64 and push to GitLab CI/CD')
    parser.add_argument('--environment', '-e', default='STAGE', 
                        help='GitLab environment scope (e.g., PROD, STAGE). Default: STAGE')
    args = parser.parse_args()
    env_lower = args.environment.lower()

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file_path = os.path.join(script_dir, f'.env_{env_lower}')
    # Load environment variables from .env file
    load_dotenv(env_file_path)

    # Read the .env file
    with open(env_file_path, 'r', encoding='utf-8') as f:
        env_content = f.read()

    # Encode to Base64
    env_b64 = base64.b64encode(env_content.encode('utf-8')).decode('utf-8')

    # Write to .envB64.txt file in the same directory
    output_file_path = os.path.join(script_dir, f'.envB64_{env_lower}.txt')
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(env_b64)

    print(f"Successfully encoded {env_file_path} to {output_file_path}")
    # Optional: Push to GitLab CI/CD variable
    GITLAB_TOKEN = os.getenv('GITLAB_TOKEN')  # Set this in your environment
    GITLAB_URL = os.getenv('GITLAB_URL', 'https://#[.....]')  # Default to gitlab.com
    PROJECT_ID = os.getenv('GITLAB_PROJECT_ID')  # Your project ID or 'namespace/project'

    if GITLAB_TOKEN and PROJECT_ID:
        try:
            # URL encode project ID if it contains slashes
            import urllib.parse
            project_id_encoded = urllib.parse.quote(PROJECT_ID, safe='')
            
            # Include environment_scope filter in URL to target specific variable
            url = f"{GITLAB_URL}/api/v4/projects/{project_id_encoded}/variables/B64_DOTENV?filter[environment_scope]={args.environment}"
            headers = {
                'PRIVATE-TOKEN': GITLAB_TOKEN,
                'Content-Type': 'application/json'
            }
            data = {
                'value': env_b64,
                'variable_type': 'env_var',  # 'env_var' or 'file'
                'masked': True,  # Hides value in job logs
                'protected': True,  # Only available on protected branches
                'environment_scope': args.environment
            }
            
            # Try to update existing variable, or create if it doesn't exist
            response = requests.put(url, headers=headers, json=data)
            
            if response.status_code == 404:
                # Variable doesn't exist, create it
                url = f"{GITLAB_URL}/api/v4/projects/{project_id_encoded}/variables"
                data['key'] = 'B64_DOTENV'
                response = requests.post(url, headers=headers, json=data)
            
            if response.status_code in [200, 201]:
                print(f"✓ Successfully updated GitLab CI/CD variable B64_DOTENV for environment '{args.environment}'")
            else:
                print(f"✗ Failed to update GitLab variable: {response.status_code}")
                print(f"  Response: {response.text}")
        except Exception as e:
            print(f"✗ Error updating GitLab variable: {e}")
    else:
        print("\nℹ To push to GitLab CI/CD, set these environment variables:")
        print("  - GITLAB_TOKEN (personal access token with 'api' scope)")
        print("  - GITLAB_PROJECT_ID (project ID or 'namespace/project')")
        print("  - GITLAB_URL (optional, defaults to https://gitlab.com)")


if __name__ == '__main__':
    main()