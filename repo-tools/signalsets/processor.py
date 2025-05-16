#!/usr/bin/env python3
import json
from pathlib import Path

from .utils import are_signals_equal, replace_signal_prefix, extract_year_range_from_filename, get_command_id

def process_signalsets(loaded_signalsets, make, model, signal_prefix=None):
    """
    Process multiple loaded signalset objects into a single unified signalset structure.
    Combines commands and signals from all input datasets for a given make/model.

    Args:
        loaded_signalsets: List of tuples, each containing (signalset_data, filename)
        make: The vehicle make
        model: The vehicle model
        signal_prefix: Optional prefix to replace vehicle-specific signal prefixes

    Returns:
        A merged signalset dictionary containing all commands and signals
    """
    merged_signalset = {
        "commands": []
    }

    # Track commands by their unique identifier (combination of hdr/eax/pid)
    command_map = {}

    # Track signals by their ID to detect conflicts
    signal_registry = {}  # Maps signal ID to its definition
    signal_origins = {}   # Track where each signal came from

    # Track which commands a signal appears in to avoid dropping duplicates used in different commands
    signal_command_usage = {}  # Maps signal ID to set of command IDs it appears in

    for signalset_data, filename in loaded_signalsets:
        # Track source file
        source_info = {
            "file": filename,
            "make": make,
            "model": model,
            "repo": f"{make}-{model}"
        }

        # Extract year range from filename if available
        years = extract_year_range_from_filename(filename)
        if years:
            source_info["yearRange"] = {"start": years[0], "end": years[1]}

        # Process commands
        for cmd in signalset_data.get('commands', []):
            # Create a unique identifier for this command
            cmd_id = get_command_id(cmd)
            if cmd_id is None:
                continue  # Only aggregate service 21/22 commands; all other services are standardized.

            # Ensure debug flag exists
            if 'dbg' not in cmd:
                cmd['dbg'] = True

            # Delete filters
            if 'dbgfilter' in cmd:
                del cmd['dbgfilter']

            # Process signals and replace their prefix if needed
            if 'signals' in cmd:
                new_signals = []
                for signal in cmd['signals']:
                    original_id = signal.get('id', '')

                    if original_id:
                        # Replace the prefix in the signal ID if needed
                        base_id = original_id
                        if signal_prefix:
                            base_id = replace_signal_prefix(original_id, signal_prefix)
                        signal['id'] = base_id

                        # Initialize signal command usage tracking if needed
                        if base_id not in signal_command_usage:
                            signal_command_usage[base_id] = set()

                        # Check if this signal is already used in this command
                        signal_already_in_command = cmd_id in signal_command_usage[base_id]

                        # Check for signal conflicts
                        if base_id in signal_registry:
                            # Check if the existing signal has the same definition
                            if are_signals_equal(signal, signal_registry[base_id]):
                                # Keep track that this signal is used in this command
                                signal_command_usage[base_id].add(cmd_id)

                                # Record this repo as a source for the signal
                                if base_id in signal_origins:
                                    if source_info["repo"] not in [src["repo"] for src in signal_origins[base_id]]:
                                        signal_origins[base_id].append(source_info)

                                if not signal_already_in_command:
                                    new_signals.append(signal)
                                continue
                            else:
                                # Register the new versioned signal
                                signal_registry[base_id] = signal

                                # Initialize command usage tracking for the versioned ID
                                if base_id not in signal_command_usage:
                                    signal_command_usage[base_id] = set()
                                signal_command_usage[base_id].add(cmd_id)

                                # Record origin of this versioned signal
                                signal_origins[base_id] = [source_info]
                        else:
                            # Register the signal if it's new
                            if base_id not in signal_registry:
                                signal_registry[base_id] = signal
                                signal_origins[base_id] = [source_info]

                            # Track this command using the signal
                            signal_command_usage[base_id].add(cmd_id)

                    # Add this signal to our new signals list
                    new_signals.append(signal)

                # Replace the signals array with our processed version
                cmd['signals'] = new_signals

            if cmd_id in command_map:
                # Merge signals if command already exists
                existing_cmd = command_map[cmd_id]
                existing_signals = {s.get('id'): s for s in existing_cmd.get('signals', [])}

                for signal in cmd.get('signals', []):
                    signal_id = signal.get('id')
                    if signal_id not in existing_signals:
                        existing_cmd.setdefault('signals', []).append(signal)
            else:
                # Add new command
                command_map[cmd_id] = cmd
                merged_signalset["commands"].append(cmd)

    # Add signal origins to the result
    merged_signalset["_signal_origins"] = signal_origins

    return merged_signalset

def merge_signalsets(signalset_files, make, model, signal_prefix=None):
    """
    Merge multiple signalset files into a single unified signalset structure.
    Combines commands and signals from all input files.

    Args:
        signalset_files: List of Path objects to signalset JSON files
        make: The vehicle make
        model: The vehicle model
        signal_prefix: Optional prefix to replace vehicle-specific signal prefixes

    Returns:
        A merged signalset dictionary containing all commands and signals
    """
    # Load all the signalset files first
    loaded_signalsets = []
    for signalset_path in signalset_files:
        try:
            with open(signalset_path) as f:
                data = json.load(f)
                loaded_signalsets.append((data, signalset_path.name))
        except Exception as e:
            print(f"Error loading signalset file {signalset_path}: {e}")
            continue

    # Process the loaded signalsets
    return process_signalsets(loaded_signalsets, make, model, signal_prefix)

def ensure_unique_signal_ids(merged_signalset):
    """
    Ensure all signal IDs in the merged signalset are globally unique by adding version suffixes.

    For duplicate signal IDs that have different definitions, this function adds
    version suffixes (_V2, _V3, etc.) to ensure uniqueness.

    Args:
        merged_signalset: Dictionary containing commands and signals

    Returns:
        Dictionary with updated signal IDs ensuring global uniqueness
    """
    # Track all signal IDs and their definitions encountered so far
    signal_registry = {}  # Maps original ID to list of (versioned_id, definition) tuples

    # Process each command
    for cmd in merged_signalset.get("commands", []):
        if "signals" not in cmd:
            continue

        new_signals = []
        for signal in cmd["signals"]:
            if "id" not in signal:
                # Keep signals without IDs unchanged
                new_signals.append(signal)
                continue

            original_id = signal["id"]
            signal_def = signal.copy()

            # Remove ID field for comparison purposes
            comparison_def = signal_def.copy()
            if "id" in comparison_def:
                del comparison_def["id"]

            # Check if we've seen this signal ID before
            if original_id in signal_registry:
                # Always create a new versioned ID for duplicate signal IDs across different commands
                # regardless of whether the definition is identical
                version = len(signal_registry[original_id]) + 1
                versioned_id = f"{original_id}_V{version}"
                signal["id"] = versioned_id

                # Store this new version
                signal_registry[original_id].append((versioned_id, comparison_def))
                new_signals.append(signal)
            else:
                # First time seeing this ID
                signal_registry[original_id] = [(original_id, comparison_def)]
                new_signals.append(signal)

        # Replace the command's signals with our processed list
        cmd["signals"] = new_signals

    # Update signal origins if present
    if "_signal_origins" in merged_signalset:
        new_origins = {}
        for original_id, versions in signal_registry.items():
            # Copy the origin info to each versioned ID
            if original_id in merged_signalset["_signal_origins"]:
                for versioned_id, _ in versions:
                    new_origins[versioned_id] = merged_signalset["_signal_origins"][original_id]

        # Replace the original origins with our expanded version
        merged_signalset["_signal_origins"] = new_origins

    return merged_signalset