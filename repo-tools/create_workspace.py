#!/usr/bin/env python3
import json
import os
import shutil
import argparse
from pathlib import Path
import sys

# Import the shared repository utilities
from repo_utils import clone_repos

def main():
    parser = argparse.ArgumentParser(description='Extract OBD parameter data for the OBDb Explorer')
    parser.add_argument('--org', default='OBDb', help='GitHub organization name')
    parser.add_argument('--workspace', default='workspace', help='Workspace directory for cloning repos')
    parser.add_argument('--filter-prefix', action='append', help='Filter repositories to only those with the specified prefix (can be used multiple times)')
    args = parser.parse_args()

    clone_repos(args.org, args.workspace, args.filter_prefix)

if __name__ == '__main__':
    main()

