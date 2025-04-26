#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import argparse
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import hashlib
import sys

def handle_repo(org_name, repo, workspace_dir):
    """Clone or update a single repository."""
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
    """Clone all repositories from a GitHub organization using parallel processing."""
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
        return

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

def extract_year_range_from_filename(filename):
    """Extract year range from filename pattern like 'aaaa-bbbb.json'."""
    # Use regex to extract year range from filename
    year_pattern = re.compile(r'(\d{4})-(\d{4})\.json$')
    match = year_pattern.search(filename)

    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        return (start_year, end_year)

    return None

def load_model_year_data(repo_dir, make, model):
    """Load model year PID support data if it exists."""
    model_years_path = repo_dir / 'service01' / 'modelyears.json'
    if not model_years_path.exists():
        return None

    try:
        with open(model_years_path) as f:
            data = json.load(f)

        # Add make and model information to the data
        return {
            'make': make,
            'model': model,
            'modelYears': data
        }
    except Exception as e:
        print(f"Error loading model year data for {make}-{model}: {e}")
        return None

def replace_signal_prefix(signal_id, make, model, new_prefix):
    """
    Replace the vehicle-specific prefix of a signal ID with a new prefix.
    Example: 'RAV4_VSS' becomes 'TOYOTA_VSS' if new_prefix is 'TOYOTA'
    """
    if not signal_id or not new_prefix:
        return signal_id

    # Try to identify the original prefix by finding the first underscore
    if '_' in signal_id:
        # Replace everything before the first underscore with the new prefix
        return f"{new_prefix}{signal_id[signal_id.find('_'):]}"
    else:
        # If no underscore exists, just prepend the prefix with an underscore
        return f"{new_prefix}_{signal_id}"

def are_signals_equal(signal1, signal2):
    """
    Compare two signal definitions to determine if they are functionally equal.
    Ignores ID field since that's what we're checking conflicts for.
    """
    # Create copies and remove 'id' field for comparison
    s1_compare = signal1.copy()
    s2_compare = signal2.copy()

    # Fields that shouldn't affect equality comparison
    exclude_fields = ['id', 'name', 'description', 'path', 'comment']

    for field in exclude_fields:
        s1_compare.pop(field, None)
        s2_compare.pop(field, None)

    # Compare core definition attributes
    return json.dumps(s1_compare, sort_keys=True) == json.dumps(s2_compare, sort_keys=True)

def merge_signalsets(signalset_files, make, model, signal_prefix=None):
    """
    Merge multiple signalset files into a single unified signalset structure.
    Combines commands and signals from all input files.
    """
    merged_signalset = {
        "commands": []
    }

    # Track commands by their unique identifier (combination of hdr/eax/pid)
    command_map = {}

    # Track signals by their ID to detect conflicts
    signal_registry = {}  # Maps signal ID to its definition
    signal_versions = {}  # Tracks version numbers for signals with same base ID
    signal_origins = {}   # Track where each signal came from

    for signalset_path in signalset_files:
        with open(signalset_path) as f:
            data = json.load(f)

        # Track source file
        source_info = {
            "file": signalset_path.name,
            "make": make,
            "model": model,
            "repo": f"{make}-{model}"
        }

        # Extract year range from filename if available
        years = extract_year_range_from_filename(signalset_path.name)
        if years:
            source_info["yearRange"] = {"start": years[0], "end": years[1]}

        # Process commands
        for cmd in data.get('commands', []):
            # Create a unique identifier for this command
            hdr = cmd.get('hdr', '')
            eax = cmd.get('eax', '')
            sid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
            pid = cmd.get('cmd', {}).get(sid, None)
            cmd_id = f"{hdr}:{eax}:{sid}:{pid}"

            # Ensure debug flag exists
            if 'dbg' not in cmd:
                cmd['dbg'] = True

            # Process signals and replace their prefix if needed
            if 'signals' in cmd:
                new_signals = []
                for signal in cmd['signals']:
                    original_id = signal.get('id', '')

                    if original_id:
                        # Replace the prefix in the signal ID if needed
                        base_id = original_id
                        if signal_prefix:
                            base_id = replace_signal_prefix(original_id, make, model, signal_prefix)

                        # Check for signal conflicts
                        if base_id in signal_registry:
                            # Check if the existing signal has the same definition
                            if are_signals_equal(signal, signal_registry[base_id]):
                                # Skip duplicate signals with identical definitions
                                # Still record this repo as a source for the signal
                                if base_id in signal_origins:
                                    if source_info["repo"] not in [src["repo"] for src in signal_origins[base_id]]:
                                        signal_origins[base_id].append(source_info)
                                continue
                            else:
                                # Signal with same ID but different definition
                                # Add a version suffix to the ID
                                if base_id not in signal_versions:
                                    signal_versions[base_id] = 1  # First conflict means version 2

                                signal_versions[base_id] += 1
                                versioned_id = f"{base_id}_v{signal_versions[base_id]}"

                                # Update the ID
                                signal['id'] = versioned_id

                                # Update name if it contains the original ID
                                if 'name' in signal and original_id in signal['name']:
                                    signal['name'] = signal['name'].replace(original_id, versioned_id)

                                # Register the new versioned signal
                                signal_registry[versioned_id] = signal

                                # Record origin of this versioned signal
                                signal_origins[versioned_id] = [source_info]
                        else:
                            # New signal, no conflicts
                            signal['id'] = base_id

                            # Update name if using new prefix
                            if signal_prefix and original_id != base_id and 'name' in signal and original_id in signal['name']:
                                signal['name'] = signal['name'].replace(original_id, base_id)

                            # Register the signal
                            signal_registry[base_id] = signal

                            # Record origin of this signal
                            signal_origins[base_id] = [source_info]

                    # Add this signal to our new signals list
                    new_signals.append(signal)

                # Replace the signals array with our processed version
                cmd['signals'] = new_signals

            if cmd_id in command_map:
                # Merge signals if command already exists
                existing_cmd = command_map[cmd_id]
                existing_signals = {s.get('id'): s for s in existing_cmd.get('signals', [])}

                for signal in cmd.get('signals', []):
                    signal_id = signal.get('id')
                    if signal_id not in existing_signals:
                        existing_cmd.setdefault('signals', []).append(signal)
            else:
                # Add new command
                command_map[cmd_id] = cmd
                merged_signalset["commands"].append(cmd)

    # Add signal origins to the result
    merged_signalset["_signal_origins"] = signal_origins

    return merged_signalset

def calculate_hash(data):
    """Calculate a hash from the sorted and normalized data for easy comparison."""
    # Convert to a string and hash
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def generate_provenance_report(signal_origins, cmd_origins, output_path):
    """
    Generate a GitHub Actions-friendly report showing which vehicle repositories
    contributed to which signals and commands in the merged result.

    Args:
        signal_origins: Dictionary mapping signal IDs to their source information
        cmd_origins: Dictionary mapping command IDs to their source information
        output_path: Path to save the report
    """
    # Generate a detailed report
    report = {
        "signalCount": len(signal_origins),
        "commandCount": len(cmd_origins),
        "repoContributions": {},
        "commands": {},
        "signals": {}
    }

    # Track contributions by repository
    for signal_id, sources in signal_origins.items():
        # Add detailed signal info
        report["signals"][signal_id] = {
            "sources": [
                {
                    "repo": source["repo"],
                    "make": source["make"],
                    "model": source["model"],
                    "file": source.get("file", "unknown"),
                    "url": f"https://github.com/OBDb/{source['repo']}/blob/main/signalsets/v3/{source.get('file', 'default.json')}"
                }
                for source in sources
            ]
        }

        # Track contribution counts by repository
        for source in sources:
            repo_name = source["repo"]
            if repo_name not in report["repoContributions"]:
                report["repoContributions"][repo_name] = {
                    "make": source["make"],
                    "model": source["model"],
                    "signalCount": 0,
                    "commandCount": 0,
                    "signals": [],
                    "commands": [],
                    "url": f"https://github.com/OBDb/{repo_name}/blob/main/signalsets/v3/default.json"
                }

            if signal_id not in report["repoContributions"][repo_name]["signals"]:
                report["repoContributions"][repo_name]["signalCount"] += 1
                report["repoContributions"][repo_name]["signals"].append(signal_id)

    # Add command origins to the report
    for cmd_id, sources in cmd_origins.items():
        report["commands"][cmd_id] = {
            "sources": [
                {
                    "repo": source["repo"],
                    "make": source["make"],
                    "model": source["model"],
                    "file": source.get("file", "unknown"),
                    "url": f"https://github.com/OBDb/{source['repo']}/blob/main/signalsets/v3/{source.get('file', 'default.json')}"
                }
                for source in sources
            ],
            "description": sources[0].get("description", "")  # Use the first source's description
        }

        # Track contribution counts by repository
        for source in sources:
            repo_name = source["repo"]
            if repo_name not in report["repoContributions"]:
                report["repoContributions"][repo_name] = {
                    "make": source["make"],
                    "model": source["model"],
                    "signalCount": 0,
                    "commandCount": 0,
                    "signals": [],
                    "commands": [],
                    "url": f"https://github.com/OBDb/{repo_name}/blob/main/signalsets/v3/default.json"
                }

            if cmd_id not in report["repoContributions"][repo_name]["commands"]:
                report["repoContributions"][repo_name]["commandCount"] += 1
                report["repoContributions"][repo_name]["commands"].append(cmd_id)

    # Sort repositories by total contribution count (signals + commands)
    sorted_repos = sorted(
        report["repoContributions"].items(),
        key=lambda x: (x[1]["signalCount"] + x[1]["commandCount"], x[1]["signalCount"]),
        reverse=True
    )

    # Generate GitHub Actions-friendly summary output
    summary = []

    # Add header with overall statistics
    summary.append(f"\n**Total signals in merged output:** {report['signalCount']}")
    summary.append(f"**Total commands in merged output:** {report['commandCount']}")
    summary.append(f"**Total contributing repositories:** {len(report['repoContributions'])}\n")

    # Add repository contribution table
    summary.append("## Repository Contributions")
    summary.append("\n| Repository | Make | Model | Signal Count | Command Count | Total Contributions |")
    summary.append("| --- | --- | --- | ---: | ---: | ---: |")

    for repo_name, data in sorted_repos:
        total = data["signalCount"] + data["commandCount"]
        # Create markdown link to the repository
        repo_link = f"[{repo_name}]({data['url']})"
        summary.append(f"| {repo_link} | {data['make']} | {data['model']} | {data['signalCount']} | {data['commandCount']} | {total} |")

    # Add detailed signal provenance section
    summary.append("\n## Signal Provenance")
    summary.append("\nThis table shows the top 30 signals with the most contributing repositories:")
    summary.append("\n| Signal ID | Contributing Repositories | Source Count |")
    summary.append("| --- | --- | ---: |")

    # Sort signals by number of contributing repos
    sorted_signals = sorted(
        report["signals"].items(),
        key=lambda x: len(x[1]["sources"]),
        reverse=True
    )[:30]  # Limit to top 30

    for signal_id, data in sorted_signals:
        # Create list of repo links
        repo_links = []
        for src in data["sources"]:
            repo_name = src["repo"]
            repo_url = src["url"]
            repo_links.append(f"[{repo_name}]({repo_url})")

        # Join unique links with commas
        unique_links = []
        seen_repos = set()
        for link in repo_links:
            repo_name = link[link.find('[')+1:link.find(']')]
            if repo_name not in seen_repos:
                unique_links.append(link)
                seen_repos.add(repo_name)

        repo_list = ", ".join(unique_links)
        summary.append(f"| `{signal_id}` | {repo_list} | {len(data['sources'])} |")

    # Add detailed command provenance section
    summary.append("\n## Command Provenance")
    summary.append("\nThis table shows the top 30 commands with the most contributing repositories:")
    summary.append("\n| Command ID | Description | Contributing Repositories | Source Count |")
    summary.append("| --- | --- | --- | ---: |")

    # Sort commands by number of contributing repos
    sorted_commands = sorted(
        report["commands"].items(),
        key=lambda x: len(x[1]["sources"]),
        reverse=True
    )[:30]  # Limit to top 30

    for cmd_id, data in sorted_commands:
        # Create list of repo links
        repo_links = []
        for src in data["sources"]:
            repo_name = src["repo"]
            repo_url = src["url"]
            repo_links.append(f"[{repo_name}]({repo_url})")

        # Join unique links with commas
        unique_links = []
        seen_repos = set()
        for link in repo_links:
            repo_name = link[link.find('[')+1:link.find(']')]
            if repo_name not in seen_repos:
                unique_links.append(link)
                seen_repos.add(repo_name)

        repo_list = ", ".join(unique_links)
        description = data["description"][:50] + "..." if len(data["description"]) > 50 else data["description"]
        summary.append(f"| `{cmd_id}` | {description} | {repo_list} | {len(data['sources'])} |")

    # Note about full report
    summary.append(f"\n\nFor complete details, see the full JSON report at `{output_path}`")

    # Save the full JSON report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Save the GitHub Actions-friendly markdown summary
    summary_path = output_path.with_suffix('.md')
    with open(summary_path, 'w') as f:
        f.write("\n".join(summary))

    return report, summary_path

def extract_data(workspace_dir, output_dir, force=False, filter_prefixes=None, signal_prefix=None):
    """Extract and merge signalset data from all repositories."""
    merged_signalset = {
        "commands": []
    }

    # Track signal origins throughout the merging process
    global_signal_origins = {}
    global_command_origins = {}

    model_year_data = []
    temp_output_path = Path(output_dir) / 'merged_signalset_temp.json'
    final_output_path = Path(output_dir) / 'merged_signalset.json'
    model_years_output_path = Path(output_dir) / 'model_years_data.json'
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

            # Check for model year PID support data
            my_data = load_model_year_data(repo_dir, make, model)
            if my_data:
                model_year_data.append(my_data)
                print(f"  Found model year PID data for {make} {model}")

        # Print summary of repos found in this filter group
        filter_desc = ", ".join(group_filters) if group_filters else "all repositories"
        print(f"Processing filter group {group_idx+1}: {filter_desc} ({len(repos_in_group)} repositories)")

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
                pid = cmd.get('cmd', {}).get(sid, None)
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}"

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
                pid = cmd.get('cmd', {}).get(sid, None)
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}"
                command_map[cmd_id] = idx

            # Add commands or merge signals for existing commands
            for cmd in repo_signalset["commands"]:
                hdr = cmd.get('hdr', '')
                eax = cmd.get('eax', '')
                sid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
                pid = cmd.get('cmd', {}).get(sid, None)
                cmd_id = f"{hdr}:{eax}:{sid}:{pid}"

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

    # Check if we need to update the file
    current_hash = calculate_hash(merged_signalset)

    # Write to temporary file first
    with open(temp_output_path, 'w') as f:
        json.dump(merged_signalset, f, indent=2, sort_keys=True)

    # Run the validation and normalization process
    print("Running validation and normalization...")
    validate_script = Path(__file__).parent / 'validate_json.py'

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

    # Save model year data with custom formatting
    if model_year_data:
        with open(model_years_output_path, 'w') as f:
            # Use custom JSON encoder to format arrays on single lines
            class CompactJSONEncoder(json.JSONEncoder):
                def encode(self, obj):
                    if isinstance(obj, list) and all(isinstance(x, str) for x in obj):
                        # For arrays of strings (PID arrays), keep them on one line
                        parts = [self.encode(item) for item in obj]
                        return "[" + ", ".join(parts) + "]"
                    return super().encode(obj)

            json_str = json.dumps(model_year_data, cls=CompactJSONEncoder, indent=2, sort_keys=True)
            # Further compact ECU command arrays by regex replacing multi-line arrays
            import re
            json_str = re.sub(r'\[\n\s+("[0-9A-F]{2}",?\s*)+\n\s+\]', lambda m: m.group(0).replace('\n', ' ').replace('  ', ''), json_str)
            f.write(json_str)
        print(f"Saved model year data to {model_years_output_path} ({len(model_year_data)} vehicles)")
    else:
        print("No model year data found.")

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

def main():
    parser = argparse.ArgumentParser(description='Extract OBD parameter data')
    parser.add_argument('--org', default='OBDb', help='GitHub organization name')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory for cloning repos')
    parser.add_argument('--output', default='public/data', help='Output directory for JSON data')
    parser.add_argument('--fetch', action='store_true', help='Fetch/update repositories before extraction')
    parser.add_argument('--force', action='store_true', help='Force update even if no changes detected')
    parser.add_argument('--filter-prefix', action='append', help='Filter repositories to only those with the specified prefix (can be used multiple times)')
    parser.add_argument('--signal-prefix', help='Replace vehicle-specific signal ID prefixes with this prefix')
    args = parser.parse_args()

    # Only clone/update repositories if --fetch is specified
    if args.fetch:
        print("Fetching repositories...")
        clone_repos(args.org, args.workspace, args.filter_prefix)
    elif not Path(args.workspace).exists():
        print(f"Error: Workspace directory '{args.workspace}' does not exist. Use --fetch to clone repositories.")
        return

    # Extract data from the repositories
    print("Extracting data from repositories...")
    extract_data(workspace_dir=args.workspace,
                output_dir=args.output,
                force=args.force,
                filter_prefixes=args.filter_prefix,
                signal_prefix=args.signal_prefix)

    print(f"Data extraction complete. The JSON file is ready for use in the React application.")

if __name__ == '__main__':
    main()
