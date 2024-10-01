#!/bin/bash

# Check for commit message argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <commit-message>"
    exit 1
fi

COMMIT_MESSAGE="$1"

# Iterate through all directories in the current directory
for dir in */; do
    dir_name="${dir%/}"  # Remove trailing slash

    # Check if the directory is a git repository
    if [ -d "$dir/.git" ]; then
        echo "Processing repository: $dir_name"
        pushd "$dir_name" || exit

        # Check for local changes
        if [ -n "$(git status --porcelain)" ]; then
            # Check if the wip branch already exists
            if git show-ref --verify --quiet refs/heads/wip; then
                echo "Branch 'wip' already exists in $dir_name. Skipping."
                popd || exit
                continue
            fi

            # Create a new branch
            git checkout -b wip

            # Add changes to staging
            git add .

            # Commit the changes
            git commit -m "$COMMIT_MESSAGE"

            # Push the new branch to the remote
            git push -u origin wip

            # Create a pull request
            gh pr create --base main --head wip --title "$COMMIT_MESSAGE" --body ""

            # Enable auto-merge on the pull request
            gh pr merge --auto --delete-branch --squash

            echo "Pull request created and auto-merge enabled for $dir_name."
        else
            echo "No changes detected in $dir_name. Skipping."
        fi

        popd || exit
    else
        echo "$dir_name is not a Git repository. Skipping."
    fi
done