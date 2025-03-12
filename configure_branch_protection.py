#!/usr/bin/env python3
import os
import argparse
from pathlib import Path
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
import json
import tempfile

def configure_repo(repo_path, org_name, protection_config, enable_auto_merge=True):
    """
    Configure branch protection and repository settings.

    Args:
        repo_path: Path to the repository
        org_name: GitHub organization name
        protection_config: Dict with branch protection configuration
        enable_auto_merge: Whether to enable auto-merge

    Returns:
        tuple: (repo_name, success, error_message)
    """
    repo_name = repo_path.name

    try:
        # Enable auto-merge and configure branch deletion on merge
        if enable_auto_merge:
            subprocess.run(
                ['gh', 'repo', 'edit', '--enable-auto-merge', '--delete-branch-on-merge',
                 '--enable-merge-commit=false', '--enable-rebase-merge=false'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            print(f"Configured repository settings for {repo_name}")

        # Set up branch protection rules
        # Create a temporary file with the protection rules
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            json.dump(protection_config, temp_file)
            temp_file_path = temp_file.name

        # Apply branch protection rules
        result = subprocess.run(
            ['gh', 'api', '-X', 'PUT', f'/repos/{org_name}/{repo_name}/branches/main/protection',
             '--input', temp_file_path],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Clean up the temporary file
        os.unlink(temp_file_path)

        print(f"Configured branch protection for {repo_name}")
        return repo_name, True, "Configuration successful"

    except subprocess.CalledProcessError as e:
        error_message = f"Command failed: {e.stderr}"
        print(f"Error configuring {repo_name}: {error_message}")
        return repo_name, False, error_message
    except Exception as e:
        error_message = str(e)
        print(f"Error configuring {repo_name}: {error_message}")
        return repo_name, False, error_message

def process_repositories(workspace_dir, org_name, protection_config, enable_auto_merge=True, exclude_prefixes=None):
    """Process all repositories in the workspace directory to configure branch protection."""
    if exclude_prefixes is None:
        exclude_prefixes = ['.']

    workspace_path = Path(workspace_dir)

    # Get all directories in the workspace that are git repositories
    repo_paths = [
        path for path in workspace_path.iterdir()
        if path.is_dir() and (path / '.git').exists() and
        not any(path.name.startswith(prefix) for prefix in exclude_prefixes)
    ]

    if not repo_paths:
        print("No repositories found to process.")
        return {}

    print(f"Found {len(repo_paths)} repositories to process")

    # Determine optimal number of workers based on CPU cores
    num_workers = min(32, multiprocessing.cpu_count() * 2)  # Cap at 32 workers

    # Track results for each repository
    results = {}

    # Process repositories in parallel
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(configure_repo, repo_path, org_name, protection_config, enable_auto_merge): repo_path.name
            for repo_path in repo_paths
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo_name, success, message = future.result()
            results[repo_name] = {
                'success': success,
                'message': message
            }

    # Print summary
    successful = sum(1 for result in results.values() if result['success'])
    failed = len(results) - successful

    print(f"\nProcessing completed:")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed repositories:")
        for repo_name, result in results.items():
            if not result['success']:
                print(f"  {repo_name}: {result['message']}")

    return results

def main():
    parser = argparse.ArgumentParser(description='Configure branch protection for repositories')
    parser.add_argument('--org', default='OBDb', help='GitHub organization name')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--config', help='JSON file with branch protection configuration')
    parser.add_argument('--disable-auto-merge', action='store_true', help='Disable auto-merge configuration')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')
    parser.add_argument('--output', help='Output JSON file to save results')

    args = parser.parse_args()

    # Default branch protection configuration (similar to configure_all_repos.sh)
    default_protection_config = {
        "required_status_checks": {
            "strict": True,
            "contexts": [
                "validate-signals",
                "test"
            ]
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0
        },
        "restrictions": None,
        "allow_force_pushes": False,
        "block_creations": True,
        "block_deletions": True
    }

    # Load custom configuration if provided
    protection_config = default_protection_config
    if args.config:
        try:
            with open(args.config, 'r') as f:
                protection_config = json.load(f)
        except Exception as e:
            print(f"Error loading configuration file: {str(e)}")
            sys.exit(1)

    results = process_repositories(
        args.workspace,
        args.org,
        protection_config,
        enable_auto_merge=not args.disable_auto_merge,
        exclude_prefixes=args.exclude
    )

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

if __name__ == '__main__':
    main()
