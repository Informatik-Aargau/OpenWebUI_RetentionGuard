import sys
import os

# Add current directory to path to import the other scripts
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import the scripts as modules (using importlib for files with leading dots)
import importlib.util

def load_module(module_path, module_name):
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load the modules
envB64_path = os.path.join(script_dir, '.envB64.py')
kubeconfig_path = os.path.join(script_dir, '.kubeconfig.py')

envB64 = load_module(envB64_path, 'envB64')
kubeconfig = load_module(kubeconfig_path, 'kubeconfig')


def run_script(module, script_name, environment):
    """Run a Python module's main function with the specified environment argument."""
    
    print(f"\n{'='*60}")
    print(f"Running: {script_name} --environment {environment}")
    print(f"{'='*60}")
    
    try:
        # Temporarily modify sys.argv to pass the environment argument
        original_argv = sys.argv.copy()
        sys.argv = [script_name, '--environment', environment]
        
        # Call the module's main function
        module.main()
        
        # Restore original argv
        sys.argv = original_argv
        
        return True
    except SystemExit as e:
        # Restore original argv
        sys.argv = original_argv
        
        if e.code != 0:
            print(f"✗ Script exited with code {e.code}")
            return False
        return True
    except Exception as e:
        # Restore original argv
        sys.argv = original_argv
        
        print(f"✗ Failed to run {script_name}: {e}")
        return False


def main():
    """Run all GitLab variable upload scripts for both stage and prod environments."""
    print("Starting GitLab CI/CD variables update...")
    print("This will upload .env and KUBECONFIG files for both STAGE and PROD environments")
    
    scripts_and_envs = [
        (envB64, '.envB64.py', 'stage'),
        (envB64, '.envB64.py', 'prod'),
        (kubeconfig, '.kubeconfig.py', 'stage'),
        (kubeconfig, '.kubeconfig.py', 'prod'),
    ]
    
    results = []
    for module, script_name, env in scripts_and_envs:
        success = run_script(module, script_name, env)
        results.append((script_name, env, success))
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    all_success = True
    for script, env, success in results:
        status = "✓ SUCCESS" if success else "✗ FAILED"
        print(f"{status}: {script} ({env})")
        if not success:
            all_success = False
    
    print(f"{'='*60}")
    
    if all_success:
        print("\n🎉 All GitLab variables updated successfully!")
        return 0
    else:
        print("\n⚠️ Some updates failed. Please check the output above.")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
