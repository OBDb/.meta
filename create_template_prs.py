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
import tempfile

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

def check_existing_pr(repo_path, branch_name):
    """
    Check if a PR already exists for the branch.

    Args:
        repo_path: Path to the repository
        branch_name: Branch name to check

    Returns:
        bool: True if PR exists, False otherwise
    """
    try:
        result = subprocess.run(
            ['gh', 'pr', 'list', '--head', branch_name, '--state', 'open'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        return len(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False

def check_branch_status(repo_path, branch_name):
    """
    Check if a branch exists and has been pushed, but no PR exists.
    Returns a tuple of (branch_exists_locally, branch_exists_remotely, has_changes, pr_exists, was_merged, remote_already_merged)
    """
    repo_name = repo_path.name

    # Make sure we have the latest information from origin
    subprocess.run(
        ['git', 'fetch', 'origin'],
        check=True,
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    # Check if branch exists locally
    result = subprocess.run(
        ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'],
        cwd=str(repo_path),
        capture_output=True,
    )
    branch_exists_locally = result.returncode == 0

    # Check if remote branch exists
    result = subprocess.run(
        ['git', 'ls-remote', '--heads', 'origin', branch_name],
        check=True,
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )
    branch_exists_remotely = branch_name in result.stdout

    # Check if PR already exists
    pr_exists = check_existing_pr(repo_path, branch_name)

    # Check if the branch was already merged into main (only if it exists locally)
    was_merged = False
    if branch_exists_locally:
        # Create a temporary file to avoid output getting mixed with other process output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            temp_file_path = temp_file.name

        try:
            # Get commit hashes from the branch
            result = subprocess.run(
                ['git', 'log', '--format=%H', branch_name],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            branch_commits = set(result.stdout.strip().split('\n'))

            # Now check if those commits are in main
            result = subprocess.run(
                ['git', 'log', '--format=%H', 'origin/main'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            main_commits = set(result.stdout.strip().split('\n'))

            # If any branch-specific commit is in main, and the branch doesn't exist remotely,
            # we can assume it was merged and the remote branch was deleted
            branch_specific_commits = branch_commits - main_commits
            was_merged = (not branch_exists_remotely) and (len(branch_specific_commits) == 0)

            # Clean up
            os.unlink(temp_file_path)
        except Exception as e:
            print(f"Error checking if branch was merged: {str(e)}")

            # Clean up
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    # Check if remote branch was already merged (only if it exists remotely)
    remote_already_merged = False
    if branch_exists_remotely and not pr_exists:
        try:
            # Get the remote branch's commit
            result = subprocess.run(
                ['git', 'rev-parse', f'origin/{branch_name}'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            remote_branch_commit = result.stdout.strip()

            # Check if this commit is already in origin/main
            result = subprocess.run(
                ['git', 'branch', '-r', '--contains', remote_branch_commit],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

            # If origin/main contains the commit, the branch was already merged
            remote_already_merged = 'origin/main' in result.stdout

        except Exception as e:
            print(f"Error checking if remote branch was merged: {str(e)}")

    # Check if there are uncommitted changes
    result = subprocess.run(
        ['git', 'status', '--porcelain'],
        check=True,
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )
    has_uncommitted_changes = bool(result.stdout.strip())

    # Check if there are changes between current branch and main
    has_committed_changes = False
    if branch_exists_locally and not was_merged:
        # Save current branch
        current_branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        current_branch = current_branch_result.stdout.strip()

        # First ensure we're on the branch
        if current_branch != branch_name:
            subprocess.run(
                ['git', 'checkout', branch_name],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

        # Then check for changes between branch and main
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'main...'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        has_committed_changes = bool(result.stdout.strip())

        # Restore original branch if we changed it
        if current_branch != branch_name:
            subprocess.run(
                ['git', 'checkout', current_branch],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

    return (branch_exists_locally, branch_exists_remotely, has_uncommitted_changes or has_committed_changes, pr_exists, was_merged, remote_already_merged)

def cleanup_merged_branch(repo_path, branch_name):
    """
    Clean up a local branch that has been merged to main.
    - Updates local main branch to match origin/main
    - Deletes the local branch

    Args:
        repo_path: Path to the repository
        branch_name: Name of the branch to delete
    """
    repo_name = repo_path.name
    print(f"Cleaning up merged branch '{branch_name}' in {repo_name}")

    try:
        # Make sure we're not on the branch we want to delete
        print(f"  $ git checkout main")
        subprocess.run(
            ['git', 'checkout', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Update main to match origin/main
        print(f"  $ git pull origin main")
        subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Delete the local branch
        print(f"  $ git branch -D {branch_name}")
        subprocess.run(
            ['git', 'branch', '-D', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        print(f"Successfully cleaned up branch '{branch_name}' in {repo_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cleaning up branch '{branch_name}' in {repo_name}: {e.stderr}")
        return False

def cleanup_remote_merged_branch(repo_path, branch_name):
    """
    Clean up a remote branch that has been merged to main.
    - Updates local main branch to match origin/main
    - Deletes the remote branch
    - Deletes the local branch if it exists

    Args:
        repo_path: Path to the repository
        branch_name: Name of the branch to delete
    """
    repo_name = repo_path.name
    print(f"Cleaning up merged remote branch '{branch_name}' in {repo_name}")

    try:
        # Make sure we're not on the branch we want to delete
        print(f"  $ git checkout main")
        subprocess.run(
            ['git', 'checkout', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Update main to match origin/main
        print(f"  $ git pull origin main")
        subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Delete the remote branch
        print(f"  $ git push origin --delete {branch_name}")
        subprocess.run(
            ['git', 'push', 'origin', '--delete', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Check if local branch exists and delete it if it does
        result = subprocess.run(
            ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'],
            cwd=str(repo_path),
            capture_output=True,
        )

        if result.returncode == 0:
            # Branch exists locally, delete it
            print(f"  $ git branch -D {branch_name}")
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

        print(f"Successfully cleaned up remote branch '{branch_name}' in {repo_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cleaning up remote branch '{branch_name}' in {repo_name}: {e.stderr}")
        return False

def create_pr_for_repo(repo_path, branch_name, commit_message, pr_title=None, dry_run=False, auto_merge=True):
    """
    Create a branch, commit changes, push, and create a PR.

    Args:
        repo_path: Path to the repository
        branch_name: Name of the branch to create
        commit_message: Commit message
        pr_title: PR title (defaults to commit message if not provided)
        dry_run: If True, print commands without executing them
        auto_merge: Whether to enable auto-merge

    Returns:
        tuple: (repo_name, success, error_message)
    """
    repo_name = repo_path.name

    if pr_title is None:
        pr_title = commit_message

    try:
        # Check the current status of the branch
        branch_exists_locally, branch_exists_remotely, has_changes, pr_exists, was_merged, remote_already_merged = check_branch_status(repo_path, branch_name)

        # Handle the case where the remote branch was already merged
        if remote_already_merged:
            print(f"Remote branch '{branch_name}' in {repo_name} exists but was already merged into main (no PR exists).")
            if not dry_run:
                cleanup_remote_merged_branch(repo_path, branch_name)
            return repo_name, True, f"Remote branch '{branch_name}' was already merged into main and has been cleaned up"

        # Handle the case where the branch was already merged
        if was_merged:
            print(f"Branch '{branch_name}' in {repo_name} was already merged into main.")
            if not dry_run:
                cleanup_merged_branch(repo_path, branch_name)
            return repo_name, True, f"Branch '{branch_name}' was already merged into main and has been cleaned up"

        # Handle various scenarios
        if pr_exists:
            print(f"PR already exists for branch '{branch_name}' in {repo_name}. Skipping.")
            return repo_name, True, f"PR already exists for branch '{branch_name}'"

        if not has_changes and not (branch_exists_locally or branch_exists_remotely):
            print(f"No changes to commit in {repo_name}. Skipping.")
            return repo_name, True, "No changes to commit"

        # For already pushed branches with no PR, we need to create a PR
        if branch_exists_remotely and not pr_exists:
            print(f"Branch '{branch_name}' exists remotely but no PR exists for {repo_name}.")
            print(f"Will attempt to create PR from existing branch.")

            # Checkout the branch if it exists locally, or fetch and checkout if it only exists remotely
            if not branch_exists_locally:
                print(f"  $ git fetch origin {branch_name}")
                subprocess.run(
                    ['git', 'fetch', 'origin', branch_name],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

                print(f"  $ git checkout {branch_name}")
                subprocess.run(
                    ['git', 'checkout', branch_name],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )
            else:
                print(f"  $ git checkout {branch_name}")
                subprocess.run(
                    ['git', 'checkout', branch_name],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

            # Prepare commands for PR creation
            commands = [
                f"gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\""
            ]

            if auto_merge:
                commands.append("gh pr merge --auto --delete-branch --squash")

            if dry_run:
                print(f"\nDRY RUN: Commands that would be executed for {repo_name}:")
                for cmd in commands:
                    print(f"  $ {cmd}")
                return repo_name, True, "Dry run completed"

            time.sleep(5)

            # Create PR with retries
            print(f"  $ gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\"")
            try:
                execute_with_retry(
                    ['gh', 'pr', 'create', '--base', 'main', '--head', branch_name, '--title', pr_title, '--body', ''],
                    cwd=str(repo_path)
                )
            except subprocess.CalledProcessError as e:
                # Check if PR already exists (sometimes happens due to race conditions)
                if "already exists" in e.stderr or "A pull request for branch" in e.stderr:
                    print(f"  PR already exists (created by another process or between our checks)")
                else:
                    raise

            # Enable auto-merge with retries
            if auto_merge:
                print(f"  $ gh pr merge --auto --delete-branch --squash")
                execute_with_retry(
                    ['gh', 'pr', 'merge', '--auto', '--delete-branch', '--squash'],
                    cwd=str(repo_path)
                )

            print(f"Created PR for {repo_name}")
            return repo_name, True, "PR created successfully for existing branch"

        elif branch_exists_locally and not branch_exists_remotely:
            # This is the case where the branch exists locally but not remotely
            # We need to check if it's because the branch was merged or if we need to push it

            # First check for changes between this branch and main
            current_branch_result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            current_branch = current_branch_result.stdout.strip()

            # Checkout the branch
            subprocess.run(
                ['git', 'checkout', branch_name],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

            # Check for changes against main
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'origin/main...'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

            if not result.stdout.strip():
                # No changes, branch was likely merged and deleted on remote
                print(f"Branch '{branch_name}' exists locally but has no changes compared to origin/main.")
                print(f"This suggests it was already merged. Cleaning up local branch.")

                if not dry_run:
                    cleanup_merged_branch(repo_path, branch_name)

                # Restore original branch if needed
                if current_branch != branch_name and current_branch != 'main':
                    subprocess.run(
                        ['git', 'checkout', current_branch],
                        check=True,
                        cwd=str(repo_path),
                        capture_output=True,
                        text=True
                    )

                return repo_name, True, f"Branch '{branch_name}' was already merged and has been cleaned up"

            # There are changes, we need to push the branch
            print(f"Branch '{branch_name}' exists locally but not remotely for {repo_name} and has changes.")
            print(f"Will push branch and create PR.")

            # Push branch to remote
            print(f"  $ git push -u origin {branch_name}")
            if not dry_run:
                execute_with_retry(
                    ['git', 'push', '-u', 'origin', branch_name],
                    cwd=str(repo_path)
                )

            # Rest of the process for PR creation continues below

        # At this point, we know we need to create a new branch if it doesn't exist locally
        if not branch_exists_locally:
            print(f"\nChanges detected in {repo_name}, creating new branch.")

            # Make sure we're on main before creating a new branch
            print(f"  $ git checkout main")
            if not dry_run:
                subprocess.run(
                    ['git', 'checkout', 'main'],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

            # Create new branch
            print(f"  $ git checkout -b {branch_name}")
            if not dry_run:
                subprocess.run(
                    ['git', 'checkout', '-b', branch_name],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

            # Add all changes
            print(f"  $ git add .")
            if not dry_run:
                subprocess.run(
                    ['git', 'add', '.'],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

            # Commit changes
            print(f"  $ git commit -m \"{commit_message}\"")
            if not dry_run:
                subprocess.run(
                    ['git', 'commit', '-m', commit_message],
                    check=True,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )

            # Push branch to remote
            print(f"  $ git push -u origin {branch_name}")
            if not dry_run:
                execute_with_retry(
                    ['git', 'push', '-u', 'origin', branch_name],
                    cwd=str(repo_path)
                )

        # Print or execute PR creation commands
        commands = [
            f"gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\""
        ]

        if auto_merge:
            commands.append("gh pr merge --auto --delete-branch --squash")

        if dry_run:
            print(f"\nDRY RUN: Commands that would be executed for {repo_name}:")
            for cmd in commands:
                print(f"  $ {cmd}")
            return repo_name, True, "Dry run completed"

        # Create PR with retries
        print(f"  $ gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\"")
        try:
            execute_with_retry(
                ['gh', 'pr', 'create', '--base', 'main', '--head', branch_name, '--title', pr_title, '--body', ''],
                cwd=str(repo_path)
            )
        except subprocess.CalledProcessError as e:
            # Check if PR already exists (sometimes happens due to race conditions)
            if "already exists" in e.stderr or "A pull request for branch" in e.stderr:
                print(f"  PR already exists (created by another process or between our checks)")
            else:
                raise

        # Enable auto-merge with retries
        if auto_merge:
            print(f"  $ gh pr merge --auto --delete-branch --squash")
            execute_with_retry(
                ['gh', 'pr', 'merge', '--auto', '--delete-branch', '--squash'],
                cwd=str(repo_path)
            )

        print(f"Created PR for {repo_name}")
        return repo_name, True, "PR created successfully"
    except Exception as e:
        error_message = str(e)
        print(f"Error creating PR for {repo_name}: {error_message}")
        return repo_name, False, error_message

def process_repositories(workspace_dir, branch_name, commit_message, pr_title=None, exclude_prefixes=None, dry_run=False, max_workers=None, auto_merge=True):
    """Process all repositories in the workspace directory to create PRs."""
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

    # Track results for each repository
    results = {}

    # Process repositories in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(create_pr_for_repo, repo_path, branch_name, commit_message, pr_title, dry_run, auto_merge): repo_path.name
            for repo_path in repo_paths
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo_name = future_to_repo[future]
            try:
                repo_name, success, message = future.result()
                results[repo_name] = {
                    'success': success,
                    'message': message
                }
            except Exception as e:
                print(f"Error processing {repo_name}: {str(e)}")
                results[repo_name] = {
                    'success': False,
                    'message': str(e)
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
    parser = argparse.ArgumentParser(description='Create PRs for changes in repositories')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--branch', default='update-template', help='Branch name to create')
    parser.add_argument('--message', required=True, help='Commit message')
    parser.add_argument('--title', help='PR title (defaults to commit message if not provided)')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')
    parser.add_argument('--output', help='Output JSON file to save results')
    parser.add_argument('--repo', help='Process only this specific repository (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without executing them')
    parser.add_argument('--workers', type=int, help='Number of worker threads (default: 8)')
    parser.add_argument('--no-auto-merge', action='store_true', help='Disable auto-merge for PRs')
    parser.add_argument('--retry-failed', help='JSON file with previous results to retry failed repositories')

    args = parser.parse_args()

    # Load previous results for retry if specified
    retrying = False
    if args.retry_failed and os.path.exists(args.retry_failed):
        try:
            with open(args.retry_failed, 'r') as f:
                previous_results = json.load(f)

            # Filter repositories that failed
            failed_repos = [
                repo for repo, result in previous_results.items()
                if not result.get('success', False)
            ]

            if failed_repos:
                print(f"Retrying {len(failed_repos)} failed repositories from previous run.")
                args.repo = failed_repos
                retrying = True
            else:
                print("No failed repositories found in previous results.")
        except Exception as e:
            print(f"Error loading previous results: {str(e)}")

    # If a specific repo or repos are specified, process only those
    if args.repo and not retrying:
        repo_path = Path(args.workspace) / args.repo
        if not repo_path.exists():
            print(f"Error: Repository {args.repo} not found in {args.workspace}")
            sys.exit(1)

        mode = "DRY RUN" if args.dry_run else "Processing"
        print(f"{mode} single repository: {args.repo}")
        result = create_pr_for_repo(repo_path, args.branch, args.message, args.title, args.dry_run, not args.no_auto_merge)
        results = {args.repo: {'success': result[1], 'message': result[2]}}
    elif args.repo and retrying:
        # Process multiple specific repositories (from retry_failed)
        results = {}
        for repo in args.repo:
            repo_path = Path(args.workspace) / repo
            if not repo_path.exists():
                print(f"Error: Repository {repo} not found in {args.workspace}")
                results[repo] = {'success': False, 'message': 'Repository not found'}
                continue

            mode = "DRY RUN" if args.dry_run else "Processing"
            print(f"{mode} repository: {repo} (retry)")
            result = create_pr_for_repo(repo_path, args.branch, args.message, args.title, args.dry_run, not args.no_auto_merge)
            results[repo] = {'success': result[1], 'message': result[2]}

            # Add a short delay between repositories to avoid rate limiting
            if not args.dry_run and len(args.repo) > 1:
                time.sleep(2)
    else:
        results = process_repositories(
            args.workspace,
            args.branch,
            args.message,
            pr_title=args.title,
            exclude_prefixes=args.exclude,
            dry_run=args.dry_run,
            max_workers=args.workers,
            auto_merge=not args.no_auto_merge
        )

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

        # Count and display successful/failed counts from results
        successful = sum(1 for result in results.values() if result.get('success', False))
        failed = len(results) - successful
        print(f"Results summary: {successful} successful, {failed} failed")

        if failed > 0:
            print(f"You can retry failed repositories with: --retry-failed {args.output}")

if __name__ == '__main__':
    main()
