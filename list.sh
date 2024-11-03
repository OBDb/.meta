#!/bin/bash

# Get all repositories from the OBDb organization
# Filter out non-vehicle repositories and format the output
gh repo list OBDb --limit 1000 | \
  grep -v "\.vehicle-template\|\.github\|\.meta\|\.schemas" | \
  cut -f1 | \
  cut -d'/' -f2 | \
  while read -r repo; do
    # Split into make and model based on repo name
    # Assuming repository names are in the format "Make-Model"
    make=$(echo "$repo" | cut -d'-' -f1)
    model=$(echo "$repo" | cut -d'-' -f2-)
    
    # Replace dashes with spaces in model name
    model=$(echo "$model" | tr '-' ' ')
    
    # Print in a clean format
    echo "$make: $model"
  done | sort