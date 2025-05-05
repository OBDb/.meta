#!/usr/bin/env python3
import argparse
from pathlib import Path

# Import the shared repository utilities
from repo_utils import clone_repos

# Import functions from our signalsets package
from signalsets.extractor import extract_data

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
    extract_data(
        workspace_dir=args.workspace,
        output_dir=args.output,
        force=args.force,
        filter_prefixes=args.filter_prefix,
        signal_prefix=args.signal_prefix
    )

    print(f"Data extraction complete. The JSON file is ready for use in the React application.")

if __name__ == '__main__':
    main()
