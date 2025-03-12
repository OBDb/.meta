#!/bin/bash

# Excluded directories
EXCLUDES=( ".vehicle-template" ".github" ".meta" ".schemas" )

# Enumerate all subdirectories in the current directory
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

    echo "Adding response tests to: $dir_name"
    pushd "$dir_name" || exit

    # if .github/workflows/response_tests.yml already exists, skip this directory
    if [ -f ".github/workflows/response_tests.yml" ]; then
        echo "response_tests.yml already exists. Skipping."
        popd || exit
        continue
    fi

    # Copy the response tests scaffolding
    cp "../.vehicle-template/.github/workflows/response_tests.yml" .github/workflows/response_tests.yml
    cp -r "../.vehicle-template/.vscode" .vscode
    cp -r "../.vehicle-template/tests" tests
    cp "../.vehicle-template/.gitignore/" .gitignore

    popd || exit
done