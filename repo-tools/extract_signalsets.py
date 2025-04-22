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

    for signalset_path in signalset_files:
        with open(signalset_path) as f:
            data = json.load(f)

        # Track source file
        source_info = {
            "file": signalset_path.name,
            "make": make,
            "model": model
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
            pid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
            cmd_id = f"{hdr}:{eax}:{pid}"

            # Ensure debug flag exists
            if 'dbg' not in cmd:
                cmd['dbg'] = True

            # Process signals and replace their prefix if needed
            if signal_prefix and 'signals' in cmd:
                for signal in cmd['signals']:
                    original_id = signal.get('id', '')
                    if original_id:
                        # Replace the prefix in the signal ID
                        new_id = replace_signal_prefix(original_id, make, model, signal_prefix)
                        signal['id'] = new_id

                        # Also update the 'name' field if it looks like it contains the ID
                        if 'name' in signal and original_id in signal['name']:
                            signal['name'] = signal['name'].replace(original_id, new_id)

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

    return merged_signalset

def calculate_hash(data):
    """Calculate a hash from the sorted and normalized data for easy comparison."""
    # Convert to a string and hash
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def extract_data(workspace_dir, output_dir, force=False, filter_prefixes=None, signal_prefix=None):
    """Extract and merge signalset data from all repositories."""
    merged_signalset = {
        "commands": []
    }

    model_year_data = []
    temp_output_path = Path(output_dir) / 'merged_signalset_temp.json'
    final_output_path = Path(output_dir) / 'merged_signalset.json'
    model_years_output_path = Path(output_dir) / 'model_years_data.json'

    all_signalsets = {}  # Organize by make-model

    # Process each repository
    for repo_dir in Path(workspace_dir).iterdir():
        if not repo_dir.is_dir():
            continue

        # Skip repositories that don't match any prefix filter if specified
        if filter_prefixes and not any(repo_dir.name.startswith(prefix) for prefix in filter_prefixes):
            continue

        signalsets_dir = repo_dir / 'signalsets' / 'v3'
        if not signalsets_dir.exists():
            print(f"No signalset directory found for {repo_dir.name}, skipping...")
            continue

        # Extract make and model from repo name
        make, model = repo_dir.name.split('-', 1) if '-' in repo_dir.name else (repo_dir.name, '')

        print(f"Processing {make} {model}...")

        # Find all signalset files in the v3 directory
        signalset_files = list(signalsets_dir.glob('*.json'))

        if not signalset_files:
            print(f"No signalset files found for {make} {model}, skipping...")
            continue

        # Store all signalset files for this make-model
        all_signalsets[f"{make}-{model}"] = {
            "files": signalset_files,
            "make": make,
            "model": model
        }

        # Check for model year PID support data
        my_data = load_model_year_data(repo_dir, make, model)
        if my_data:
            model_year_data.append(my_data)
            print(f"  Found model year PID data for {make} {model}")

    # Merge all signalsets in a sorted order for consistent output between runs
    for repo_key in sorted(all_signalsets.keys()):
        repo_data = all_signalsets[repo_key]
        print(f"Merging signalsets for {repo_key}...")
        repo_signalset = merge_signalsets(
            repo_data["files"],
            repo_data["make"],
            repo_data["model"],
            signal_prefix
        )

        # Merge into the global signalset
        # Add commands
        existing_cmd_ids = {
            f"{cmd.get('hdr', '')}:{cmd.get('eax', '')}:{list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''}"
            for cmd in merged_signalset["commands"]
        }

        for cmd in repo_signalset["commands"]:
            hdr = cmd.get('hdr', '')
            eax = cmd.get('eax', '')
            pid = list(cmd.get('cmd', {}).keys())[0] if cmd.get('cmd') else ''
            cmd_id = f"{hdr}:{eax}:{pid}"

            if cmd_id not in existing_cmd_ids:
                merged_signalset["commands"].append(cmd)

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
