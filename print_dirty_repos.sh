#!/bin/bash

# Enumerate all folders in the current directory
for dir in */ ; do
    # Check if the folder is a git repository
    if [ -d "$dir/.git" ]; then
        cd "$dir" || exit

        # Check for local changes using git status --porcelain
        if [ -n "$(git status --porcelain)" ]; then
            echo "Local changes found in: $dir"
        fi

        cd ..
    fi
done