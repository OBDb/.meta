#!/usr/bin/env python3
import os
import argparse
from pathlib import Path
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
import json

def create_pr_for_repo(repo_path, branch_name, commit_message, pr_title=None, dry_run=False):
    """
    Create a branch, commit changes, push, and create a PR.

    Args:
        repo_path: Path to the repository
        branch_name: Name of the branch to create
        commit_message: Commit message
        pr_title: PR title (defaults to commit message if not provided)
        dry_run: If True, print commands without executing them

    Returns:
        tuple: (repo_name, success, error_message)
    """
    repo_name = repo_path.name

    if pr_title is None:
        pr_title = commit_message

    try:
        # Check if there are any changes to commit
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        if not result.stdout.strip():
            print(f"No changes to commit in {repo_name}. Skipping.")
            return repo_name, True, "No changes to commit"

        print(f"\nChanges detected in {repo_name}:")
        print(result.stdout.strip())

        # Check if branch already exists
        result = subprocess.run(
            ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'],
            cwd=str(repo_path),
            capture_output=True,
        )

        if result.returncode == 0:
            print(f"Branch '{branch_name}' already exists in {repo_name}. Skipping.")
            return repo_name, False, f"Branch '{branch_name}' already exists"

        # Check if remote branch exists
        result = subprocess.run(
            ['git', 'ls-remote', '--heads', 'origin', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        if branch_name in result.stdout:
            print(f"Remote branch '{branch_name}' already exists in {repo_name}. Skipping.")
            return repo_name, False, f"Remote branch '{branch_name}' already exists"

        # Print or execute commands
        commands = [
            f"git checkout -b {branch_name}",
            "git add .",
            f"git commit -m \"{commit_message}\"",
            f"git push -u origin {branch_name}",
            f"gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\"",
            "gh pr merge --auto --delete-branch --squash"
        ]

        if dry_run:
            print(f"\nDRY RUN: Commands that would be executed for {repo_name}:")
            for cmd in commands:
                print(f"  $ {cmd}")
            return repo_name, True, "Dry run completed"

        # Create new branch
        print(f"\nExecuting commands for {repo_name}:")
        print(f"  $ git checkout -b {branch_name}")
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Add all changes
        print(f"  $ git add .")
        subprocess.run(
            ['git', 'add', '.'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Commit changes
        print(f"  $ git commit -m \"{commit_message}\"")
        subprocess.run(
            ['git', 'commit', '-m', commit_message],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Push branch to remote
        print(f"  $ git push -u origin {branch_name}")
        subprocess.run(
            ['git', 'push', '-u', 'origin', branch_name],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Create PR
        print(f"  $ gh pr create --base main --head {branch_name} --title \"{pr_title}\" --body \"\"")
        subprocess.run(
            ['gh', 'pr', 'create', '--base', 'main', '--head', branch_name, '--title', pr_title, '--body', ''],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        # Enable auto-merge
        print(f"  $ gh pr merge --auto --delete-branch --squash")
        subprocess.run(
            ['gh', 'pr', 'merge', '--auto', '--delete-branch', '--squash'],
            check=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        print(f"Created PR for {repo_name}")
        return repo_name, True, "PR created successfully"

    except subprocess.CalledProcessError as e:
        error_message = f"Command failed: {e.stderr}"
        print(f"Error creating PR for {repo_name}: {error_message}")
        return repo_name, False, error_message
    except Exception as e:
        error_message = str(e)
        print(f"Error creating PR for {repo_name}: {error_message}")
        return repo_name, False, error_message

def process_repositories(workspace_dir, branch_name, commit_message, pr_title=None, exclude_prefixes=None, dry_run=False):
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
    num_workers = min(32, multiprocessing.cpu_count() * 2)  # Cap at 32 workers

    # Track results for each repository
    results = {}

    # Process repositories in parallel
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(create_pr_for_repo, repo_path, branch_name, commit_message, pr_title, dry_run): repo_path.name
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
    parser = argparse.ArgumentParser(description='Create PRs for changes in repositories')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--branch', default='update-template', help='Branch name to create')
    parser.add_argument('--message', required=True, help='Commit message')
    parser.add_argument('--title', help='PR title (defaults to commit message if not provided)')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')
    parser.add_argument('--output', help='Output JSON file to save results')
    parser.add_argument('--repo', help='Process only this specific repository (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without executing them')

    args = parser.parse_args()

    # If a specific repo is specified, process only that one
    if args.repo:
        repo_path = Path(args.workspace) / args.repo
        if not repo_path.exists():
            print(f"Error: Repository {args.repo} not found in {args.workspace}")
            sys.exit(1)

        mode = "DRY RUN" if args.dry_run else "Processing"
        print(f"{mode} single repository: {args.repo}")
        result = create_pr_for_repo(repo_path, args.branch, args.message, args.title, args.dry_run)
        results = {args.repo: {'success': result[1], 'message': result[2]}}
    else:
        results = process_repositories(
            args.workspace,
            args.branch,
            args.message,
            pr_title=args.title,
            exclude_prefixes=args.exclude,
            dry_run=args.dry_run
        )

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

if __name__ == '__main__':
    main()
