#!/usr/bin/env python3
import os
import shutil
import argparse
from pathlib import Path
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys

def setup_template_repo(org_name, workspace_dir):
    """Clone or update the template repository."""
    template_repo = ".vehicle-template"
    template_path = Path(workspace_dir) / template_repo

    try:
        if not template_path.exists():
            # Clone new repository
            subprocess.run(
                ['gh', 'repo', 'clone', f'{org_name}/{template_repo}', str(template_path)],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Cloned {template_repo}")
        else:
            # Update existing repository
            subprocess.run(
                ['git', 'fetch', '--all'],
                check=True,
                cwd=str(template_path),
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', 'reset', '--hard', 'origin/main'],
                check=True,
                cwd=str(template_path),
                capture_output=True,
                text=True
            )
            print(f"Updated {template_repo}")
        return template_path
    except subprocess.CalledProcessError as e:
        print(f"Error processing {template_repo}: {e.stderr}")
        sys.exit(1)

def copy_files_to_repo(repo_path, template_path, files_to_copy, preserve_existing=False):
    """
    Copy specified files from template to a repository.

    Args:
        repo_path: Path to the target repository
        template_path: Path to the template repository
        files_to_copy: List of file paths relative to repo root to copy
        preserve_existing: If True, don't overwrite existing files

    Returns:
        tuple: (repo_name, list of copied files, success status)
    """
    repo_name = repo_path.name
    copied_files = []

    try:
        for file_path in files_to_copy:
            src_file = template_path / file_path
            dst_file = repo_path / file_path

            # Create parent directories if they don't exist
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Check if destination file exists and we're preserving existing files
            if dst_file.exists() and preserve_existing:
                print(f"Skipping existing file in {repo_name}: {file_path}")
                continue

            # Copy the file
            if src_file.is_file():
                shutil.copy2(src_file, dst_file)
                copied_files.append(file_path)
                print(f"Copied {file_path} to {repo_name}")
            else:
                print(f"Warning: Source file {file_path} not found in template")

        return repo_name, copied_files, True
    except Exception as e:
        print(f"Error copying files to {repo_name}: {str(e)}")
        return repo_name, [], False

def process_repositories(org_name, workspace_dir, files_to_copy, exclude_prefixes=None, preserve_existing=False):
    """Process all repositories in the workspace directory."""
    if exclude_prefixes is None:
        exclude_prefixes = ['.']

    workspace_path = Path(workspace_dir)

    # Ensure template repo is available
    template_path = setup_template_repo(org_name, workspace_dir)

    # Get all directories in the workspace
    repo_paths = [
        path for path in workspace_path.iterdir()
        if path.is_dir() and path.name != '.vehicle-template' and
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
            executor.submit(copy_files_to_repo, repo_path, template_path, files_to_copy, preserve_existing): repo_path.name
            for repo_path in repo_paths
        }

        # Process completed tasks
        for future in as_completed(future_to_repo):
            repo_name, copied_files, success = future.result()
            results[repo_name] = {
                'copied_files': copied_files,
                'success': success
            }

    # Print summary
    successful = sum(1 for result in results.values() if result['success'])
    failed = len(results) - successful

    print(f"\nProcessing completed:")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")

    return results

def main():
    parser = argparse.ArgumentParser(description='Copy template files to repositories')
    parser.add_argument('--org', default='OBDb', help='GitHub organization name')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory containing cloned repos')
    parser.add_argument('--files', required=True, nargs='+', help='Files to copy from template (relative paths)')
    parser.add_argument('--preserve', action='store_true', help='Preserve existing files (don\'t overwrite)')
    parser.add_argument('--exclude', nargs='+', default=['.'], help='Repository name prefixes to exclude')

    args = parser.parse_args()

    results = process_repositories(
        args.org,
        args.workspace,
        args.files,
        exclude_prefixes=args.exclude,
        preserve_existing=args.preserve
    )

    # Count repositories with changes
    repos_with_changes = sum(1 for result in results.values() if result['copied_files'])
    print(f"Files copied to {repos_with_changes} repositories")

if __name__ == '__main__':
    main()
