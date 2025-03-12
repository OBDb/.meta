#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

def update_default_json(repo_path):
    """
    Check if the signalsets/v3/default.json file matches a specific pattern and update it.

    Args:
        repo_path: Path to the repository

    Returns:
        tuple: (repo_name, status, message)
    """
    repo_name = repo_path.name
    file_path = repo_path / "signalsets" / "v3" / "default.json"

    try:
        # Check if the file exists
        if not file_path.exists():
            return repo_name, "skipped", "File does not exist"

        # Read the file content
        with open(file_path, 'r') as f:
            content = f.read().strip()

        # Check if the content matches the pattern
        target_pattern = '{ "commands": []\n}'
        if content == target_pattern:
            # Update the file
            new_content = '{ "commands": [\n\n]\n}\n'
            with open(file_path, 'w') as f:
                f.write(new_content)
            return repo_name, "updated", "File updated successfully"
        else:
            return repo_name, "skipped", f"Content doesn't match pattern"

    except Exception as e:
        return repo_name, "error", f"Error: {str(e)}"

def process_repositories(workspace_dir, exclude_prefixes=None):
    """Process all repositories in the workspace directory."""
    if exclude_prefixes is None:
        exclude_prefixes = ['.']

    workspace_path = Path(workspace_dir)

    # Get all directories in the workspace
    repo_paths = [
        path for path in workspace_path.iterdir()
        if path.is_dir() and
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
            executor.submit(update_default_json, repo_path): repo_path.name
            for repo_path in repo_paths
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo_name, status, message = future.result()
            results[repo_name] = {
                'status': status,
                'message': message
            }
            print(f"{repo_name}: {status} - {message}")

    # Print summary
    updated = sum(1 for result in results.values() if result['status'] == "updated")
    skipped = sum(1 for result in results.values() if result['status'] == "skipped")
    errors = sum(1 for result in results.values() if result['status'] == "error")

    print(f"\nProcessing completed:")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")

    return results

def main():
    parser = argparse.ArgumentParser(description='Update default.json files in repositories')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')

    args = parser.parse_args()

    results = process_repositories(
        args.workspace,
        exclude_prefixes=args.exclude
    )

if __name__ == '__main__':
    main()
