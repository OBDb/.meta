#!/bin/bash

# Check for repo name argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <new-repo-name>"
    exit 1
fi

REPO_NAME=$1
TEMPLATE_REPO="OBDb/.vehicle-template"

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

# Set up branch protection rules for the main branch
echo "Setting up branch protection for main branch in $REPO_NAME"
gh api -X PUT /repos/OBDb/$REPO_NAME/branches/main/protection --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "validate-signals"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "block_creations": true,
  "block_deletions": true
}
EOF

echo "Repository $REPO_NAME has been successfully created and configured."