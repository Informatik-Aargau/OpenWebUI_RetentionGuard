import requests
import os
import argparse
from dotenv import load_dotenv


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Upload KUBECONFIG file to GitLab CI/CD')
    parser.add_argument('--environment', '-e', default='stage', 
                        help='Environment (prod or stage). Default: stage')
    args = parser.parse_args()
    env_lower = args.environment.lower()

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load environment variables from .env file if it exists (for GitLab credentials)
    env_file = os.path.join(script_dir, f'.env_{env_lower}')
    if os.path.exists(env_file):
        load_dotenv(env_file)
    
    # Path to KUBECONFIG file
    kubeconfig_file_path = os.path.join(script_dir, f'.KUBECONFIG_{env_lower}')
    
    if not os.path.exists(kubeconfig_file_path):
        print(f"✗ Error: KUBECONFIG file not found at {kubeconfig_file_path}")
        return

    # Read the KUBECONFIG file
    with open(kubeconfig_file_path, 'r', encoding='utf-8') as f:
        kubeconfig_content = f.read()

    # Write to output file for verification (plain text)
    output_file_path = os.path.join(script_dir, f'.KUBECONFIG_{env_lower}.txt')
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(kubeconfig_content)

    print(f"Successfully copied {kubeconfig_file_path} to {output_file_path}")
    
    # Push to GitLab CI/CD variable
    GITLAB_TOKEN = os.getenv('GITLAB_TOKEN')
    GITLAB_URL = os.getenv('GITLAB_URL', 'https://#[.....]')
    PROJECT_ID = os.getenv('GITLAB_PROJECT_ID')

    if GITLAB_TOKEN and PROJECT_ID:
        try:
            # URL encode project ID if it contains slashes
            import urllib.parse
            project_id_encoded = urllib.parse.quote(PROJECT_ID, safe='')
            
            # Variable name: KUBECONFIG (environment scope differentiates stage/prod)
            variable_name = 'KUBECONFIG'
            
            # Include environment_scope filter in URL to target specific variable
            url = f"{GITLAB_URL}/api/v4/projects/{project_id_encoded}/variables/{variable_name}?filter[environment_scope]={env_lower}"
            headers = {
                'PRIVATE-TOKEN': GITLAB_TOKEN,
                'Content-Type': 'application/json'
            }
            data = {
                'value': kubeconfig_content,
                'variable_type': 'file',  # File type variable
                'masked': False,  # File type variables cannot be masked
                'protected': True,  # Only available on protected branches
                'environment_scope': env_lower
            }
            
            # Try to update existing variable, or create if it doesn't exist
            response = requests.put(url, headers=headers, json=data)
            
            if response.status_code == 404:
                # Variable doesn't exist, create it
                url = f"{GITLAB_URL}/api/v4/projects/{project_id_encoded}/variables"
                data['key'] = variable_name
                response = requests.post(url, headers=headers, json=data)
            
            if response.status_code in [200, 201]:
                print(f"✓ Successfully updated GitLab CI/CD variable {variable_name} (type: file) for environment '{env_lower}'")
            else:
                print(f"✗ Failed to update GitLab variable: {response.status_code}")
                print(f"  Response: {response.text}")
        except Exception as e:
            print(f"✗ Error updating GitLab variable: {e}")
    else:
        print("\nℹ To push to GitLab CI/CD, set these environment variables:")
        print("  - GITLAB_TOKEN (personal access token with 'api' scope)")
        print("  - GITLAB_PROJECT_ID (project ID or 'namespace/project')")
        print("  - GITLAB_URL (optional, defaults to https://#[.....])") 


if __name__ == '__main__':
    main()
