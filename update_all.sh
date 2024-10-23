#!/bin/bash

# Set the repository owner and total number of repositories per page
REPO_OWNER="OBDb"
REPO_LIMIT=1000  # Adjust this number if you need more

# Function to clone or update a repo
process_repo() {
    local repo_name=$1
    if [ -d "$repo_name" ]; then
        echo "Repository $repo_name already exists. Checking for local changes."
        cd "$repo_name" || exit

        # Check if the working directory is clean
        if [ -z "$(git status --porcelain)" ]; then
            echo "No local changes in $repo_name. Fetching latest changes."
            git fetch origin
            git rebase origin/main
        else
            echo "Local changes detected in $repo_name. Skipping fetch and rebase."
        fi

        cd ..
    else
        echo "Cloning repository $repo_name."
        git clone git@github.com:$REPO_OWNER/$repo_name.git
    fi
}

# Query all repositories up to the specified limit
repos=$(gh repo list $REPO_OWNER --limit $REPO_LIMIT | grep "$REPO_OWNER/" | cut -f1 | cut -d'/' -f2)

# Process each repository
echo "$repos" | while read -r repo_name; do
    process_repo "$repo_name"
done