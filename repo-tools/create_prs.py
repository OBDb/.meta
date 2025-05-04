#!/usr/bin/env python3
import os
import argparse
import subprocess
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# Import the shared repository utilities
from repo_utils import clone_repos, handle_repo

def get_vehicle_repos(workspace_dir):
    """
    Get all vehicle repos in the workspace (directories without a dot prefix).

    Args:
        workspace_dir: Path to workspace directory

    Returns:
        list: List of vehicle repository paths
    """
    workspace_path = Path(workspace_dir)
    vehicle_repos = []

    for item in workspace_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            vehicle_repos.append(item)

    return vehicle_repos

def create_branch_and_pr(org_name, repo_name, repo_path, branch_name, title, body, auto_merge=True):
    """
    Create a branch, commit changes that are already staged, and open a PR with auto-merge enabled.

    Args:
        org_name: GitHub organization name
        repo_name: Repository name
        repo_path: Path to repository
        branch_name: Name of branch to create
        title: PR title
        body: PR description
        auto_merge: Whether to enable auto-merge for the PR

    Returns:
        str: PR URL or None if failed
    """
    try:
        # Make sure we're on main branch first and up to date
        subprocess.run(
            ['git', 'checkout', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        subprocess.run(
            ['git', 'pull'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Create and checkout new branch
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Check if there are any changes to commit
        status = subprocess.run(
            ['git', 'status', '--porcelain'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        ).stdout.strip()

        if not status:
            print(f"No changes to commit in {repo_name}")
            # Clean up branch since we don't need it
            subprocess.run(
                ['git', 'checkout', 'main'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            print(f"Cleaned up unused branch {branch_name} in {repo_name}")
            return None

        # Add all changes
        subprocess.run(
            ['git', 'add', '.'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Commit changes
        subprocess.run(
            ['git', 'commit', '-m', title],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Push branch
        subprocess.run(
            ['git', 'push', '--set-upstream', 'origin', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Create PR
        pr_output = subprocess.run(
            [
                'gh', 'pr', 'create',
                '--repo', f'{org_name}/{repo_name}',
                '--title', title,
                '--body', body,
                '--base', 'main'
            ],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        ).stdout.strip()

        # Extract PR URL from output
        pr_url = pr_output.strip()

        if auto_merge:
            # Enable auto-merge
            pr_number = pr_url.split('/')[-1]
            subprocess.run(
                [
                    'gh', 'pr', 'merge',
                    pr_number,
                    '--auto',
                    '--squash'
                ],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

        print(f"Created PR for {repo_name}: {pr_url}")
        return pr_url

    except subprocess.CalledProcessError as e:
        print(f"Error creating PR for {repo_name}: {e.stderr}")
        return None

def cleanup_repo(repo_path, branch_name):
    """
    Clean up local repository after PR is merged:
    - Fetch updates from remote with pruning
    - Checkout main branch
    - Rebase main on origin/main
    - Delete the working branch

    Args:
        repo_path: Path to repository
        branch_name: Name of branch to delete

    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    try:
        # Fetch updates from remote with pruning
        subprocess.run(
            ['git', 'fetch', '--all', '-p'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Checkout main branch
        subprocess.run(
            ['git', 'checkout', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Rebase main on origin/main
        subprocess.run(
            ['git', 'rebase', 'origin/main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Delete the working branch
        subprocess.run(
            ['git', 'branch', '-D', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        print(f"Cleaned up repository at {repo_path}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error cleaning up repository at {repo_path}: {e.stderr}")
        return False

def monitor_pr_status(repo_path, pr_url, branch_name):
    """
    Monitor PR status until it is merged or closed.

    Args:
        repo_path: Path to repository
        pr_url: URL of the PR to monitor
        branch_name: Name of branch to clean up if PR is merged

    Returns:
        bool: True if PR was merged successfully, False otherwise
    """
    pr_number = pr_url.split('/')[-1]
    max_attempts = 30
    attempt = 0

    while attempt < max_attempts:
        try:
            # Get PR status
            pr_status = subprocess.run(
                ['gh', 'pr', 'view', pr_number, '--json', 'state,mergedAt'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            ).stdout.strip()

            pr_data = json.loads(pr_status)

            if pr_data.get('mergedAt'):
                print(f"PR {pr_url} was merged successfully!")

                # Clean up the repository after successful merge
                cleanup_success = cleanup_repo(repo_path, branch_name)
                if not cleanup_success:
                    print(f"Warning: Could not clean up repository after PR {pr_url} was merged")

                return True

            if pr_data.get('state') == 'CLOSED':
                print(f"PR {pr_url} was closed without merging")

                # Clean up the repository even when PR was closed without merging
                cleanup_success = cleanup_repo(repo_path, branch_name)
                if not cleanup_success:
                    print(f"Warning: Could not clean up repository after PR {pr_url} was closed")

                return False

            # PR is still open, wait and check again
            print(f"PR {pr_url} is still open, waiting...")
            time.sleep(20)  # Check every 20 seconds

        except subprocess.CalledProcessError as e:
            print(f"Error checking PR status for {pr_url}: {e.stderr}")
            time.sleep(20)  # Wait and try again

        attempt += 1

    print(f"Timed out waiting for PR {pr_url} to merge")
    return False

def process_vehicle_repo(args, vehicle_repo_path):
    """
    Process a single vehicle repository.

    Args:
        args: Command line arguments
        vehicle_repo_path: Path to vehicle repository

    Returns:
        tuple: (repo_name, success)
    """
    repo_name = vehicle_repo_path.name
    print(f"Processing {repo_name}...")

    try:
        # Create branch and PR (assumes changes have already been made)
        branch_name = args.branch
        pr_url = create_branch_and_pr(
            args.org,
            repo_name,
            vehicle_repo_path,
            branch_name,
            args.title,
            args.body,
            auto_merge=args.auto_merge
        )

        if not pr_url:
            return repo_name, False

        # Monitor PR status if requested
        if args.watch:
            return repo_name, monitor_pr_status(vehicle_repo_path, pr_url, branch_name)
        else:
            return repo_name, True

    except Exception as e:
        print(f"Error processing {repo_name}: {str(e)}")
        return repo_name, False

def main():
    parser = argparse.ArgumentParser(description='Create PRs for changes in vehicle repositories')
    parser.add_argument('--org', default='OBDb', help='GitHub organization name')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing repositories')
    parser.add_argument('--branch', default='update-branch', help='Branch name for PR')
    parser.add_argument('--title', default='Update repository', help='PR title')
    parser.add_argument('--body', default='Bulk update.', help='PR description')
    parser.add_argument('--filter-prefix', action='append', help='Filter repositories by prefix')
    parser.add_argument('--watch', action='store_true', help='Watch PRs until they are merged or closed')
    parser.add_argument('--no-auto-merge', dest='auto_merge', action='store_false', help='Disable auto-merge for PRs')
    parser.add_argument('--repo', help='Process only a specific repository (by name)')
    parser.set_defaults(auto_merge=True)
    args = parser.parse_args()

    try:
        # Ensure workspace directory exists
        workspace_dir = Path(args.workspace)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # If workspace_dir is not absolute, make it relative to current directory
        if not workspace_dir.is_absolute():
            workspace_dir = Path.cwd() / workspace_dir

        # Get vehicle repos (filtering if requested)
        if args.repo:
            # Process only the specified repository
            repo_path = workspace_dir / args.repo
            if not repo_path.exists():
                print(f"Error: Repository {args.repo} not found in {workspace_dir}")
                return 1

            vehicle_repos = [repo_path]
            print(f"Processing single repository: {args.repo}")
        else:
            # Get all matching repositories
            all_vehicle_repos = get_vehicle_repos(workspace_dir)

            if args.filter_prefix:
                vehicle_repos = [repo for repo in all_vehicle_repos if any(repo.name.startswith(prefix) for prefix in args.filter_prefix)]
                print(f"Filtered to {len(vehicle_repos)} repositories starting with any of: {', '.join(args.filter_prefix)}")
            else:
                vehicle_repos = all_vehicle_repos
                print(f"Found {len(vehicle_repos)} vehicle repositories")

        if not vehicle_repos:
            print("No vehicle repositories found")
            return 1

        # Process each vehicle repo
        num_workers = min(4, multiprocessing.cpu_count())  # Lower number of workers to avoid API rate limits

        successful = 0
        failed = 0
        results = {}

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(process_vehicle_repo, args, repo_path): repo_path.name
                for repo_path in vehicle_repos
            }

            for future in as_completed(futures):
                repo_name, success = future.result()
                results[repo_name] = success
                if success:
                    successful += 1
                else:
                    failed += 1

        print(f"\nProcessing completed:")
        print(f"Successfully processed: {successful}")
        print(f"Failed: {failed}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())