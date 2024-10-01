#!/bin/bash

# Excluded directories
EXCLUDES=( ".vehicle-template" "ElectricSidecar" ".github" "meta" )

# Enumerate all subdirectories in the current directory
for dir in */; do
    dir_name="${dir%/}"  # Remove trailing slash

    # Check if the directory is excluded
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

    echo "Synchronizing schema to: $dir_name"
    pushd "$dir_name" || exit

    # Use rsync to synchronize the schema directory
    rsync -a --delete --exclude='.git/' --exclude='schema/' "../.vehicle-template/schema/" schema/
    rsync -a --delete --exclude='.git/' --exclude='.github/' "../.vehicle-template/.github/" .github/
    
    popd || exit
done