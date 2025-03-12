#!/usr/bin/env python3
import os
import argparse
from pathlib import Path
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
import json
import time
import random
import re

def execute_with_retry(cmd, cwd, max_retries=5, initial_wait=2, backoff_factor=2, rate_limit_pattern=None):
    """
    Execute a command with retry logic and exponential backoff.

    Args:
        cmd: Command to execute as list
        cwd: Working directory
        max_retries: Maximum number of retries
        initial_wait: Initial wait time in seconds
        backoff_factor: Backoff factor for wait time
        rate_limit_pattern: Regex pattern to identify rate limiting errors

    Returns:
        subprocess.CompletedProcess: Result of the command
    """
    if rate_limit_pattern is None:
        # Default pattern for GitHub API rate limiting errors
        rate_limit_pattern = r"(was submitted too quickly|rate limit exceeded|secondary rate limit)"

    wait_time = initial_wait

    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                cmd,
                check=True,
                cwd=str(cwd),
                capture_output=True,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            # Check if this is a rate limit error
            if attempt < max_retries and e.stderr and re.search(rate_limit_pattern, e.stderr, re.IGNORECASE):
                # Add some randomness to avoid all processes retrying at the same time
                jitter = random.uniform(0.8, 1.2)
                actual_wait = wait_time * jitter

                print(f"  Rate limit detected. Waiting {actual_wait:.1f}s before retry {attempt+1}/{max_retries}...")
                time.sleep(actual_wait)

                # Increase wait time for next attempt
                wait_time *= backoff_factor
            else:
                # Not a rate limit error or out of retries
                raise

def check_remote_branch(repo_path, branch_name):
    """
    Check if a branch exists remotely.

    Args:
        repo_path: Path to the repository
        branch_name: Branch name to check

    Returns:
        bool: True if branch exists remotely, False otherwise
    """
    try:
        # Make sure we have the latest information from origin
        subprocess.run(
            ['git', 'fetch', 'origin'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Check if remote branch exists
        result = subprocess.run(
            ['git', 'ls-remote', '--heads', 'origin', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        return branch_name in result.stdout
    except subprocess.CalledProcessError:
        return False

def check_open_pr(repo_path, branch_name):
    """
    Check if an open PR exists for the branch.

    Args:
        repo_path: Path to the repository
        branch_name: Branch name to check

    Returns:
        str or None: PR number if an open PR exists, None otherwise
    """
    try:
        result = subprocess.run(
            ['gh', 'pr', 'list', '--head', branch_name, '--state', 'open', '--json', 'number'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            prs = json.loads(result.stdout)
            if prs:
                return str(prs[0]['number'])
        return None
    except subprocess.CalledProcessError:
        return None

def close_pr_and_delete_branch(repo_path, pr_number, branch_name, dry_run=False):
    """
    Close a PR and delete the associated branch.

    Args:
        repo_path: Path to the repository
        pr_number: PR number to close
        branch_name: Branch name to delete
        dry_run: If True, print commands without executing them

    Returns:
        bool: True if successful, False otherwise
    """
    repo_name = repo_path.name

    try:
        # Commands to execute
        print(f"Will close PR #{pr_number} and delete branch '{branch_name}' in {repo_name}")

        if dry_run:
            print(f"  DRY RUN: gh pr close {pr_number} --delete-branch")
            return True

        # Close PR and delete the branch
        print(f"  $ gh pr close {pr_number} --delete-branch")
        execute_with_retry(
            ['gh', 'pr', 'close', pr_number, '--delete-branch'],
            cwd=str(repo_path)
        )

        print(f"Successfully closed PR #{pr_number} and deleted branch '{branch_name}' in {repo_name}")
        return True
    except Exception as e:
        print(f"Error closing PR #{pr_number} in {repo_name}: {str(e)}")
        return False

def delete_remote_branch(repo_path, branch_name, dry_run=False):
    """
    Delete a remote branch without an associated PR.

    Args:
        repo_path: Path to the repository
        branch_name: Branch name to delete
        dry_run: If True, print commands without executing them

    Returns:
        bool: True if successful, False otherwise
    """
    repo_name = repo_path.name

    try:
        print(f"Will delete remote branch '{branch_name}' in {repo_name} (no open PR)")

        if dry_run:
            print(f"  DRY RUN: git push origin --delete {branch_name}")
            return True

        # Delete the remote branch
        print(f"  $ git push origin --delete {branch_name}")
        execute_with_retry(
            ['git', 'push', 'origin', '--delete', branch_name],
            cwd=str(repo_path)
        )

        print(f"Successfully deleted remote branch '{branch_name}' in {repo_name}")
        return True
    except Exception as e:
        print(f"Error deleting branch '{branch_name}' in {repo_name}: {str(e)}")
        return False

def process_repository(repo_path, branch_name, dry_run=False):
    """
    Process a single repository to check for and close PRs for a specific branch.

    Args:
        repo_path: Path to the repository
        branch_name: Branch name to check
        dry_run: If True, print commands without executing them

    Returns:
        tuple: (repo_name, success, message, actions_taken)
    """
    repo_name = repo_path.name

    try:
        print(f"Processing {repo_name}...")

        # Check if branch exists remotely
        branch_exists = check_remote_branch(repo_path, branch_name)

        if not branch_exists:
            print(f"  Branch '{branch_name}' does not exist remotely in {repo_name}. Skipping.")
            return repo_name, True, f"Branch '{branch_name}' does not exist remotely", None

        # Check if an open PR exists for the branch
        pr_number = check_open_pr(repo_path, branch_name)

        if pr_number:
            # PR exists, close it and delete the branch
            success = close_pr_and_delete_branch(repo_path, pr_number, branch_name, dry_run)
            action = "closed_pr_and_deleted_branch"
            message = f"Closed PR #{pr_number} and deleted branch '{branch_name}'"
        else:
            # Branch exists but no PR, just delete the branch
            success = delete_remote_branch(repo_path, branch_name, dry_run)
            action = "deleted_branch_only"
            message = f"Deleted remote branch '{branch_name}' (no open PR)"

        return repo_name, success, message, action

    except Exception as e:
        error_message = str(e)
        print(f"Error processing {repo_name}: {error_message}")
        return repo_name, False, error_message, None

def process_repositories(workspace_dir, branch_name, exclude_prefixes=None, dry_run=False, max_workers=None):
    """
    Process all repositories in the workspace directory to close PRs and delete branches.

    Args:
        workspace_dir: Directory containing the repositories
        branch_name: Branch name to check
        exclude_prefixes: List of repository name prefixes to exclude
        dry_run: If True, print commands without executing them
        max_workers: Number of worker threads to use

    Returns:
        dict: Results for each repository
    """
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
    if max_workers is None:
        # For GitHub API, we should be more conservative with parallel requests
        # to avoid hitting rate limits too frequently
        max_workers = min(8, multiprocessing.cpu_count())

    print(f"Using {max_workers} worker threads")
    mode = "DRY RUN" if dry_run else "ACTIVE MODE"
    print(f"Running in {mode}")

    # Track results for each repository
    results = {}

    # Count of actions
    actions = {
        "closed_pr_and_deleted_branch": 0,
        "deleted_branch_only": 0,
        "skipped": 0
    }

    # Process repositories in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(process_repository, repo_path, branch_name, dry_run): repo_path.name
            for repo_path in repo_paths
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo_name = future_to_repo[future]
            try:
                repo_name, success, message, action = future.result()
                results[repo_name] = {
                    'success': success,
                    'message': message,
                    'action': action
                }

                # Update action counts
                if action == "closed_pr_and_deleted_branch":
                    actions["closed_pr_and_deleted_branch"] += 1
                elif action == "deleted_branch_only":
                    actions["deleted_branch_only"] += 1
                else:
                    actions["skipped"] += 1

            except Exception as e:
                print(f"Error processing {repo_name}: {str(e)}")
                results[repo_name] = {
                    'success': False,
                    'message': str(e),
                    'action': None
                }

    # Print summary
    successful = sum(1 for result in results.values() if result['success'])
    failed = len(results) - successful

    print(f"\nProcessing completed:")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")
    print(f"Actions taken:")
    print(f"  PRs closed and branches deleted: {actions['closed_pr_and_deleted_branch']}")
    print(f"  Branches deleted (no PR): {actions['deleted_branch_only']}")
    print(f"  Repositories skipped (no matching branch): {actions['skipped']}")

    if failed > 0:
        print("\nFailed repositories:")
        for repo_name, result in results.items():
            if not result['success']:
                print(f"  {repo_name}: {result['message']}")

    return results

def main():
    parser = argparse.ArgumentParser(description='Close PRs and delete branches for repositories')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--branch', required=True, help='Branch name to check for PRs')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')
    parser.add_argument('--output', help='Output JSON file to save results')
    parser.add_argument('--repo', help='Process only this specific repository (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without executing them')
    parser.add_argument('--workers', type=int, help='Number of worker threads (default: 8)')

    args = parser.parse_args()

    # If a specific repo is specified, process only that one
    if args.repo:
        repo_path = Path(args.workspace) / args.repo
        if not repo_path.exists():
            print(f"Error: Repository {args.repo} not found in {args.workspace}")
            sys.exit(1)

        mode = "DRY RUN" if args.dry_run else "ACTIVE MODE"
        print(f"{mode} - Processing single repository: {args.repo}")
        result = process_repository(repo_path, args.branch, args.dry_run)
        results = {args.repo: {'success': result[1], 'message': result[2], 'action': result[3]}}
    else:
        results = process_repositories(
            args.workspace,
            args.branch,
            exclude_prefixes=args.exclude,
            dry_run=args.dry_run,
            max_workers=args.workers
        )

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

        # Count and display successful/failed counts from results
        successful = sum(1 for result in results.values() if result.get('success', False))
        failed = len(results) - successful
        print(f"Results summary: {successful} successful, {failed} failed")

if __name__ == '__main__':
    main()
