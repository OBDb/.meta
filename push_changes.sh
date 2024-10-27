#!/bin/bash

# Check for commit message argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <commit-message>"
    exit 1
fi

# Excluded directories
EXCLUDES=( ".vehicle-template" ".github" ".meta" ".schemas" )

COMMIT_MESSAGE="$1"

# Iterate through all directories in the current directory
for dir in */; do
    dir_name="${dir%/}"  # Remove trailing slash

    # Check if the directory is in the exclude list
    skip=false
    for exclude in "${EXCLUDES[@]}"; do
        if [[ "$dir_name" == "$exclude" ]]; then
            skip=true
            break
        fi
    done

    # Skip if it's in the exclude list
    if $skip; then
        echo "Skipping excluded directory: $dir_name"
        continue
    fi

    # Check if the directory is a git repository
    if [ -d "$dir/.git" ]; then
        echo "Processing repository: $dir_name"
        pushd "$dir_name" >> /dev/null || exit

        # Check for local changes first
        if [ -n "$(git status --porcelain)" ]; then
            # Handle local changes as before
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
            # Check for remote wip branch
            git fetch origin
            if git ls-remote --heads origin wip | grep -q wip; then
                echo "Remote 'wip' branch exists in $dir_name."
                
                # Check if PR already exists
                if ! gh pr list --head wip --state open | grep -q .; then
                    echo "No open PR found for wip branch. Creating new PR."
                    
                    # Checkout the wip branch
                    git checkout wip

                    # Create a pull request
                    gh pr create --base main --head wip --title "$COMMIT_MESSAGE" --body ""

                    # Enable auto-merge on the pull request
                    gh pr merge --auto --delete-branch --squash

                    echo "Pull request created and auto-merge enabled for existing wip branch in $dir_name."
                else
                    echo "Pull request already exists for wip branch in $dir_name. Skipping."
                fi
            else
                echo "No wip branch or local changes in $dir_name. Skipping."
            fi
        fi

        popd >> /dev/null || exit
    else
        echo "$dir_name is not a Git repository. Skipping."
    fi
done