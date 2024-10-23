#!/bin/bash

# Loop through all directories in the current folder
for dir in */ ; do
    if [ -d "$dir" ]; then
        echo "Checking directory: $dir"
        
        # Change into the directory
        cd "$dir"
        
        # Check if it's a git repository
        if [ -d ".git" ]; then
            # Get current remote URL
            current_url=$(git remote get-url origin)
            
            # Check if the current URL contains ElectricSidecar
            if echo "$current_url" | grep -q "ElectricSidecar"; then
                # Create new URL by replacing ElectricSidecar with OBDb
                new_url=${current_url/ElectricSidecar/OBDb}
                
                echo "Updating remote URL in $dir"
                echo "From: $current_url"
                echo "To:   $new_url"
                
                # Update the remote URL
                git remote set-url origin "$new_url"
                
                # Verify the change
                echo "New remote URL: $(git remote get-url origin)"
            else
                echo "Repository doesn't contain 'ElectricSidecar' in remote URL, skipping..."
            fi
        else
            echo "Not a git repository, skipping..."
        fi
        
        # Return to parent directory
        cd ..
    fi
done

echo "Finished updating repository remotes"