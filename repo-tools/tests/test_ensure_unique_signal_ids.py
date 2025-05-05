#!/usr/bin/env python3
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add parent directory to path to import the module being tested
sys.path.insert(0, str(Path(__file__).parent.parent))

import extract_signalsets

class TestExtractSignalsets(unittest.TestCase):

    def test_ensure_unique_signal_ids_no_duplicates(self):
        """Test that signals with unique IDs remain unchanged."""
        # Create a signalset with unique signal IDs
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}},
                        {"id": "SIGNAL_2", "name": "Signal 2", "fmt": {"type": "UINT16"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_3", "name": "Signal 3", "fmt": {"type": "UINT32"}}
                    ]
                }
            ]
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        # Check that signal IDs remain unchanged
        self.assertDictContainsSubset(result, signalset)

    def test_ensure_unique_signal_ids_with_duplicates(self):
        """Test that duplicate signal IDs with different definitions get versioned."""
        # Create a signalset with duplicate signal IDs but different definitions
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        # Same ID but different definition
                        {"id": "SIGNAL_1", "name": "Signal 1 Different", "fmt": {"type": "UINT16"}}
                    ]
                }
            ]
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        # Check that the second signal got versioned
        self.assertDictEqual(result, {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1_V2", "name": "Signal 1 Different", "fmt": {"type": "UINT16"}}
                    ]
                }
            ]
        })

    def test_ensure_unique_signal_ids_with_identical_duplicates(self):
        """Test that identical duplicate signals keep the same ID."""
        # Create a signalset with duplicate signal IDs that have identical definitions
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        # Same ID and identical definition
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                }
            ]
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        self.assertDictEqual(result, {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1_V2", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                }
            ]
        })

    def test_ensure_unique_signal_ids_multiple_versions(self):
        """Test that multiple versions of the same signal ID get properly versioned."""
        # Create a signalset with multiple different definitions for the same signal ID
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1 V2", "fmt": {"type": "UINT16"}}
                    ]
                },
                {
                    "hdr": "7E2",
                    "cmd": {"22": "0130"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1 V3", "fmt": {"type": "UINT32"}}
                    ]
                }
            ]
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        self.assertDictEqual(result, {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1_V2", "name": "Signal 1 V2", "fmt": {"type": "UINT16"}}
                    ]
                },
                {
                    "hdr": "7E2",
                    "cmd": {"22": "0130"},
                    "signals": [
                        {"id": "SIGNAL_1_V3", "name": "Signal 1 V3", "fmt": {"type": "UINT32"}}
                    ]
                }
            ]
        })

    def test_ensure_unique_signal_ids_with_signal_origins(self):
        """Test that signal origins are updated correctly when signal IDs are versioned."""
        # Create a signalset with duplicate signal IDs and _signal_origins metadata
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1 Different", "fmt": {"type": "UINT16"}}
                    ]
                }
            ],
            "_signal_origins": {
                "SIGNAL_1": [{"repo": "Test-Repo", "make": "Test", "model": "Model"}]
            }
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        self.maxDiff = None
        self.assertDictEqual(result, {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}}
                    ]
                },
                {
                    "hdr": "7E1",
                    "cmd": {"22": "0120"},
                    "signals": [
                        {"id": "SIGNAL_1_V2", "name": "Signal 1 Different", "fmt": {"type": "UINT16"}}
                    ]
                }
            ],
            "_signal_origins": {
                "SIGNAL_1": [{"repo": "Test-Repo", "make": "Test", "model": "Model"}],
                "SIGNAL_1_V2": [{"repo": "Test-Repo", "make": "Test", "model": "Model"}],
            }
        })

    def test_ensure_unique_signal_ids_with_signals_without_ids(self):
        """Test that signals without IDs are handled correctly."""
        # Create a signalset with some signals missing IDs
        signalset = {
            "commands": [
                {
                    "hdr": "7E0",
                    "cmd": {"22": "0110"},
                    "signals": [
                        {"id": "SIGNAL_1", "name": "Signal 1", "fmt": {"type": "UINT8"}},
                        {"name": "Signal without ID", "fmt": {"type": "UINT16"}}  # No ID
                    ]
                }
            ]
        }

        # Process the signalset
        result = extract_signalsets.ensure_unique_signal_ids(signalset)

        # Check that the signal without ID was preserved as-is
        self.assertEqual(result["commands"][0]["signals"][0]["id"], "SIGNAL_1")
        self.assertNotIn("id", result["commands"][0]["signals"][1])
        self.assertEqual(result["commands"][0]["signals"][1]["name"], "Signal without ID")

if __name__ == '__main__':
    unittest.main()