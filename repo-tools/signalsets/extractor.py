#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .processor import merge_signalsets, ensure_unique_signal_ids
from .provenance import generate_provenance_report
from .utils import calculate_hash

def extract_data(workspace_dir, output_dir, force=False, filter_prefixes=None, filter_prefix_exclusions=None, signal_prefix=None):
    """Extract and merge signalset data from all repositories.

    Args:
        workspace_dir: Directory containing repositories
        output_dir: Directory to save merged signalset and reports
        force: Force update even if no changes detected
        filter_prefixes: Optional list of prefixes to include
        filter_prefix_exclusions: Optional list of prefixes to exclude
        signal_prefix: Optional prefix to replace vehicle-specific signal prefixes
    """
    merged_signalset = {
        "commands": []
    }

    # Track signal origins throughout the merging process
    global_signal_origins = {}
    global_command_origins = {}

    temp_output_path = Path(output_dir) / 'merged_signalset_temp.json'
    final_output_path = Path(output_dir) / 'merged_signalset.json'
    provenance_report_path = Path(output_dir) / 'signal_provenance_report.json'

    # Organize repositories by filter priority
    all_repos = {}  # Key: repo name, Value: repo data

    # Process each repository and group by matching filter
    repo_groups = []

    # If no filters specified, create a single group with all repositories
    if not filter_prefixes:
        repo_groups.append([])  # Single group with no filter
    else:
        # Create a group for each filter, preserving order
        for prefix in filter_prefixes:
            repo_groups.append([prefix])

    for group_idx, group_filters in enumerate(repo_groups):
        repos_in_group = {}  # Reset for each filter group

        # Process each repository for the current filter group
        for repo_dir in Path(workspace_dir).iterdir():
            if not repo_dir.is_dir():
                continue

            # Skip repositories that don't match the current filter group
            if group_filters:  # If we have filters in this group
                if not any(repo_dir.name.startswith(prefix) for prefix in group_filters):
                    continue

            # Skip repositories that match any exclusion pattern
            if filter_prefix_exclusions and any(repo_dir.name.startswith(prefix) for prefix in filter_prefix_exclusions):
                print(f"Excluding {repo_dir.name} based on exclusion filter")
                continue

            # Skip repositories already processed by previous filter groups
            if repo_dir.name in all_repos:
                continue

            signalsets_dir = repo_dir / 'signalsets' / 'v3'
            if not signalsets_dir.exists():
                print(f"No signalset directory found for {repo_dir.name}, skipping...")
                continue

            # Extract make and model from repo name
            make, model = repo_dir.name.split('-', 1) if '-' in repo_dir.name else (repo_dir.name, '')

            # Find all signalset files in the v3 directory
            signalset_files = list(signalsets_dir.glob('*.json'))

            if not signalset_files:
                print(f"No signalset files found for {make} {model}, skipping...")
                continue

            # Store all signalset files for this make-model
            repos_in_group[repo_dir.name] = {
                "files": signalset_files,
                "make": make,
                "model": model
            }

            # Also add to our master list of repositories
            all_repos[repo_dir.name] = {
                "files": signalset_files,
                "make": make,
                "model": model,
                "priority": group_idx  # Track which filter group this repo matched
            }

        # Print summary of repos found in this filter group
        filter_desc = ", ".join(group_filters) if group_filters else "all repositories"
        exclusion_desc = f" (excluding: {', '.join(filter_prefix_exclusions)})" if filter_prefix_exclusions else ""
        print(f"Processing filter group {group_idx+1}: {filter_desc}{exclusion_desc} ({len(repos_in_group)} repositories)")

        # Process repositories within this filter group in a sorted order
        for repo_name in sorted(repos_in_group.keys()):
            repo_data = repos_in_group[repo_name]
            print(f"Merging signalsets for {repo_name}...")
            repo_signalset = merge_signalsets(
                repo_data["files"],
                repo_data["make"],
                repo_data["model"],
                signal_prefix
            )

            # Track signal origins from this repo
            if "_signal_origins" in repo_signalset:
                for signal_id, sources in repo_signalset["_signal_origins"].items():
                    if signal_id not in global_signal_origins:
                        global_signal_origins[signal_id] = []
                    global_signal_origins[signal_id].extend(sources)

                # Remove the signal origins metadata from the repo signalset before merging
                del repo_signalset["_signal_origins"]

            # Process and track commands from this repo
            for cmd in repo_signalset.get("commands", []):
                hdr = cmd.get('hdr', '')
                eax = cmd.get('eax', '')
                sid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
                if sid != '21' and sid != '22':
                    continue  # Only aggregate service 21/22 commands; all other services are standardized.
                pid = cmd.get('cmd', {}).get(sid, None)
                if 'filter' in cmd:
                    filter = json.dumps(cmd['filter'])
                else:
                    filter = ''
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}:{filter}"

                # Build command source information
                cmd_source = {
                    "repo": repo_name,
                    "make": repo_data["make"],
                    "model": repo_data["model"],
                    "description": cmd.get("description", ""),
                    "file": "combined", # Since commands come from merged signalsets
                    "priority": all_repos[repo_name]["priority"]  # Track priority of this source
                }

                # Track command origins
                if cmd_id not in global_command_origins:
                    global_command_origins[cmd_id] = []

                # Only add if this repo isn't already in the sources for this command
                if not any(src["repo"] == repo_name for src in global_command_origins[cmd_id]):
                    global_command_origins[cmd_id].append(cmd_source)

            # Merge into the global signalset
            # Create a mapping of command IDs to commands in the merged signalset
            command_map = {}
            for idx, cmd in enumerate(merged_signalset["commands"]):
                hdr = cmd.get('hdr', '')
                eax = cmd.get('eax', '')
                sid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
                if sid != '21' and sid != '22':
                    continue  # Only aggregate service 21/22 commands; all other services are standardized.
                pid = cmd.get('cmd', {}).get(sid, None)
                if 'filter' in cmd:
                    filter = json.dumps(cmd['filter'])
                else:
                    filter = ''
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}:{filter}"

            # Add commands or merge signals for existing commands
            for cmd in repo_signalset["commands"]:
                hdr = cmd.get('hdr', '')
                eax = cmd.get('eax', '')
                sid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
                if sid != '21' and sid != '22':
                    continue  # Only aggregate service 21/22 commands; all other services are standardized.
                pid = cmd.get('cmd', {}).get(sid, None)
                if 'filter' in cmd:
                    filter = json.dumps(cmd['filter'])
                else:
                    filter = ''
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}:{filter}"

                if cmd_id in command_map:
                    # Command exists, merge signals
                    existing_cmd = merged_signalset["commands"][command_map[cmd_id]]

                    # Create a set of existing signal IDs for faster lookup
                    existing_signal_ids = {s.get('id') for s in existing_cmd.get('signals', [])}

                    # Add any new signals from this command
                    for signal in cmd.get('signals', []):
                        signal_id = signal.get('id')
                        if signal_id and signal_id not in existing_signal_ids:
                            if 'signals' not in existing_cmd:
                                existing_cmd['signals'] = []
                            existing_cmd['signals'].append(signal)
                            existing_signal_ids.add(signal_id)
                else:
                    # Command doesn't exist, add it
                    merged_signalset["commands"].append(cmd)

    # Print summary of all repositories processed
    print(f"\nProcessed {len(all_repos)} repositories in {len(repo_groups)} filter groups")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Ensure unique signal IDs
    print("Ensuring globally unique signal IDs...")
    merged_signalset = ensure_unique_signal_ids(merged_signalset)

    # Check if we need to update the file
    current_hash = calculate_hash(merged_signalset)

    # Write to temporary file first
    with open(temp_output_path, 'w') as f:
        json.dump(merged_signalset, f, indent=2, sort_keys=True)

    # Run the validation and normalization process
    print("Running validation and normalization...")
    validate_script = Path(__file__).parent.parent / 'validate_json.py'

    if not validate_script.exists():
        print(f"Warning: validate_json.py not found at {validate_script}, skipping validation")
        shutil.move(temp_output_path, final_output_path)
    else:
        try:
            # Use the validation script for consistent outputs
            subprocess.run([
                sys.executable,
                str(validate_script),
                '--input', str(temp_output_path),
                '--output', str(final_output_path)
            ], check=True)

            # Clean up temp file
            os.remove(temp_output_path)
        except subprocess.CalledProcessError as e:
            print(f"Error validating JSON: {e}")
            # Fall back to raw output if validation fails
            shutil.move(temp_output_path, final_output_path)

    # Generate the provenance report
    print(f"Generating signal provenance report...")
    report, summary_path = generate_provenance_report(global_signal_origins, global_command_origins, provenance_report_path)

    signal_count = len(global_signal_origins)
    command_count = len(global_command_origins)
    repo_count = len(report["repoContributions"])
    print(f"Signal provenance report saved:")
    print(f"- JSON report: {provenance_report_path} ({signal_count} signals, {command_count} commands from {repo_count} repositories)")
    print(f"- Markdown summary: {summary_path}")

    print(f"Saved merged signalset to {final_output_path} ({len(merged_signalset['commands'])} commands)")

    # Compare with previous version if it exists
    if final_output_path.exists() and not force:
        try:
            with open(final_output_path) as f:
                old_data = json.load(f)
            old_hash = calculate_hash(old_data)

            if old_hash == current_hash:
                print("No changes detected in the data.")
            else:
                print("Changes detected in the merged signalset.")
        except (json.JSONDecodeError, FileNotFoundError):
            print("Previous file invalid or not found. Creating new file.")

    return merged_signalset