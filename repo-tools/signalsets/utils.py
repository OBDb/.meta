#!/usr/bin/env python3
import hashlib
import json
import re

def calculate_hash(data):
    """Calculate a hash from the sorted and normalized data for easy comparison."""
    # Convert to a string and hash
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def extract_year_range_from_filename(filename):
    """Extract year range from filename pattern like 'aaaa-bbbb.json'."""
    # Use regex to extract year range from filename
    year_pattern = re.compile(r'(\d{4})-(\d{4})\.json$')
    match = year_pattern.search(filename)

    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        return (start_year, end_year)

    return None

def replace_signal_prefix(signal_id, new_prefix):
    """
    Replace the vehicle-specific prefix of a signal ID with a new prefix.
    Example: 'RAV4_VSS' becomes 'TOYOTA_VSS' if new_prefix is 'TOYOTA'
    """
    if not signal_id or not new_prefix:
        return signal_id

    # Try to identify the original prefix by finding the first underscore
    if '_' in signal_id:
        # Replace everything before the first underscore with the new prefix
        return f"{new_prefix}{signal_id[signal_id.find('_'):]}"
    else:
        # If no underscore exists, just prepend the prefix with an underscore
        return f"{new_prefix}_{signal_id}"

def are_signals_equal(signal1, signal2):
    """
    Compare two signal definitions to determine if they are functionally equal.
    Ignores ID field since that's what we're checking conflicts for.
    """
    # Create copies and remove 'id' field for comparison
    s1_compare = signal1.copy()
    s2_compare = signal2.copy()

    # Fields that shouldn't affect equality comparison
    exclude_fields = ['id', 'name', 'description', 'path', 'comment']

    for field in exclude_fields:
        s1_compare.pop(field, None)
        s2_compare.pop(field, None)

    # Compare core definition attributes
    return json.dumps(s1_compare, sort_keys=True) == json.dumps(s2_compare, sort_keys=True)