#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

def handle_repo(org_name, repo, workspace_dir):
    """
    Clone or update a single repository.

    Args:
        org_name: GitHub organization name
        repo: Repository name
        workspace_dir: Directory to clone into

    Returns:
        bool: True if successful, False otherwise
    """
    repo_path = Path(workspace_dir) / repo
    try:
        if not repo_path.exists():
            # Clone new repository
            subprocess.run(
                ['gh', 'repo', 'clone', f'{org_name}/{repo}', str(repo_path)],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Cloned {repo}")
        else:
            # Update existing repository
            subprocess.run(
                ['git', 'fetch', '--all'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', 'reset', '--hard', 'origin/main'],
                check=True,
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
            print(f"Updated {repo}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing {repo}: {e.stderr}")
        return False

def clone_repos(org_name, workspace_dir, filter_prefixes=None):
    """
    Clone all repositories from a GitHub organization using parallel processing.

    Args:
        org_name: GitHub organization name
        workspace_dir: Directory to clone repositories into
        filter_prefixes: Optional list of repository name prefixes to filter by

    Returns:
        tuple: (successful_count, failed_count)
    """
    # Create workspace directory if it doesn't exist
    Path(workspace_dir).mkdir(parents=True, exist_ok=True)

    # Get all repo names using GitHub API with pagination
    cmd = [
        'gh', 'api',
        '-H', 'Accept: application/vnd.github+json',
        '-H', 'X-GitHub-Api-Version: 2022-11-28',
        f'/orgs/{org_name}/repos',
        '--jq', '.[].name',
        '-X', 'GET',
        '--paginate'
    ]

    try:
        repos = subprocess.check_output(cmd).decode().strip().split('\n')
    except subprocess.CalledProcessError as e:
        print(f"Error fetching repositories: {e}")
        return 0, 0

    # Filter out excluded repos
    filtered_repos = [
        repo for repo in repos
        if '.' not in repo
    ]

    # Apply prefix filters if specified
    if filter_prefixes:
        # Find repos that match any of the specified prefixes
        prefix_filtered_repos = []
        for repo in filtered_repos:
            if any(repo.startswith(prefix) for prefix in filter_prefixes):
                prefix_filtered_repos.append(repo)

        filtered_repos = prefix_filtered_repos
        print(f"Filtered to {len(filtered_repos)} repositories starting with any of: {', '.join(filter_prefixes)}")
    else:
        print(f"Found {len(filtered_repos)} repositories to process")

    # Determine optimal number of workers based on CPU cores
    num_workers = min(32, multiprocessing.cpu_count() * 2)  # Cap at 32 workers

    # Process repositories in parallel
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        future_to_repo = {
            executor.submit(handle_repo, org_name, repo, workspace_dir): repo
            for repo in filtered_repos
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                if future.result():
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"Error processing {repo}: {str(e)}")
                failed += 1

    print(f"\nProcessing completed:")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")
    if failed > 0:
        print("Check the error messages above for details about failed repositories.")

    return successful, failed