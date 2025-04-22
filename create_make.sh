#!/bin/bash

# Check for repo name argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <make>"
    exit 1
fi

REPO_NAME=$1
TEMPLATE_REPO="OBDb/.make-template"

# Create a new GitHub repository from the template
echo "Creating the new GitHub repository from the template: $TEMPLATE_REPO"
gh repo create OBDb/$REPO_NAME --template $TEMPLATE_REPO --public --clone

# Navigate into the newly cloned repo directory
cd $REPO_NAME || exit

# Configure repository settings (auto-merge, disable merge commit and rebase merge, delete branch on merge)
echo "Configuring repository settings for $REPO_NAME"
gh repo edit OBDb/$REPO_NAME \
    --enable-auto-merge \
    --delete-branch-on-merge \
    --enable-merge-commit=false \
    --enable-rebase-merge=false

# Update the workflow file with the correct make name
echo "Updating workflow configuration with make name: $REPO_NAME"
# Format variables: FILTER_PREFIX adds a dash, SIGNAL_PREFIX removes spaces and uppercase
FILTER_PREFIX="${REPO_NAME}-"
SIGNAL_PREFIX=$(echo "$REPO_NAME" | tr -d ' ' | tr '[:lower:]' '[:upper:]')

# Replace the env section in the workflow file
if [ -f ".github/workflows/daily-update.yml" ]; then
    sed -i '' -e "s/  FILTER_PREFIX: Make-.*$/  FILTER_PREFIX: ${FILTER_PREFIX}/g" .github/workflows/daily-update.yml
    sed -i '' -e "s/  SIGNAL_PREFIX: MAKE.*$/  SIGNAL_PREFIX: ${SIGNAL_PREFIX}/g" .github/workflows/daily-update.yml
    echo "Workflow file updated successfully."

    # Commit and push the changes to main
    echo "Committing and pushing workflow file changes to main..."
    git add .github/workflows/daily-update.yml
    git commit -m "Update workflow with make-specific configuration"
    git push origin main

    echo "Changes committed and pushed to main."
else
    echo "Warning: Workflow file .github/workflows/daily-update.yml not found."
fi

echo "Repository $REPO_NAME has been successfully created and configured."

# Trigger the daily-update.yml workflow after pushing changes
echo "Triggering the daily-update workflow..."
if gh workflow run daily-update.yml -R OBDb/$REPO_NAME; then
    echo "Workflow triggered successfully. You can monitor its progress in the GitHub Actions tab."
else
    echo "Failed to trigger the workflow. Please run it manually from the GitHub Actions tab."
fi
