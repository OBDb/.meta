#!/bin/bash

# Excluded directories
EXCLUDES=( ".vehicle-template" ".github" ".meta" ".schemas" )

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
        pushd "$dir_name" || exit

        gh repo edit --enable-auto-merge --delete-branch-on-merge --enable-merge-commit=false --enable-rebase-merge=false

        gh api -X PUT /repos/OBDb/$dir_name/branches/main/protection --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "validate-signals",
      "test",
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
        popd || exit
    else
        echo "$dir_name is not a Git repository. Skipping."
    fi
done
