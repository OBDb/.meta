#!/usr/bin/env python3
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add parent directory to path to import the module being tested
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.processor import (
    merge_signalsets,
    process_signalsets,
    ensure_unique_signal_ids
)


class TestSignalsetsProcessor(unittest.TestCase):

    @patch('builtins.open', new_callable=mock_open)
    def test_merge_signalsets_basic(self, mock_file):
        # Mock file contents for a basic signalset
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps({
            'commands': [
                {
                    'hdr': '7E0',
                    'eax': '00',
                    'cmd': {'22': '0110'},
                    'description': 'Vehicle Speed',
                    'signals': [
                        {
                            'id': 'TOYOTA_VSS',
                            'name': 'Vehicle Speed',
                            'type': 'UINT8',
                            'unit': 'km/h'
                        }
                    ]
                }
            ]
        })

        # Create a mock Path object for signalset files
        mock_path = MagicMock()
        mock_path.name = 'default.json'

        # Call the function
        result = merge_signalsets([mock_path], 'Toyota', 'Camry')

        # Check the result
        self.assertEqual(len(result['commands']), 1)
        self.assertEqual(result['commands'][0]['hdr'], '7E0')
        self.assertEqual(len(result['commands'][0]['signals']), 1)
        self.assertEqual(result['commands'][0]['signals'][0]['id'], 'TOYOTA_VSS')

        # Check origins tracking
        self.assertIn('_signal_origins', result)
        self.assertIn('TOYOTA_VSS', result['_signal_origins'])
        self.assertEqual(len(result['_signal_origins']['TOYOTA_VSS']), 1)
        self.assertEqual(result['_signal_origins']['TOYOTA_VSS'][0]['make'], 'Toyota')
        self.assertEqual(result['_signal_origins']['TOYOTA_VSS'][0]['model'], 'Camry')

    @patch('builtins.open', new_callable=mock_open)
    def test_merge_signalsets_with_signal_prefix(self, mock_file):
        # Mock file with a signal that has a model-specific prefix
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps({
            'commands': [
                {
                    'hdr': '7E0',
                    'eax': '00',
                    'cmd': {'22': '0110'},
                    'description': 'Vehicle Speed',
                    'signals': [
                        {
                            'id': 'CAMRY_VSS',
                            'name': 'CAMRY Vehicle Speed',
                            'type': 'UINT8',
                            'unit': 'km/h'
                        }
                    ]
                }
            ]
        })

        # Create a mock Path object for signalset files
        mock_path = MagicMock()
        mock_path.name = 'default.json'

        # Call the function with signal prefix
        result = merge_signalsets([mock_path], 'Toyota', 'Camry', signal_prefix='TOYOTA')

        # Check the result - signal ID and name should have the prefix replaced
        self.assertEqual(result['commands'][0]['signals'][0]['id'], 'TOYOTA_VSS')

        # Check origins tracking
        self.assertIn('TOYOTA_VSS', result['_signal_origins'])

    @patch('builtins.open')
    def test_merge_signalsets_with_conflicting_signals(self, mock_open):
        # Create two mock data sets with conflicting signal definitions
        data1 = {
            'commands': [
                { "hdr": "701", "rax": "709", "dbg": True, "cmd": {"22": "0103"}, "freq": 10,
                "signals": [
                    {"id": "CAMRY_ODO", "path": "Trips", "fmt": {"bix": 8, "len": 24, "max": 16777215, "unit": "kilometers" }, "name": "Odometer", "suggestedMetric": "odometer"},
                    {"id": "CAMRY_ODO", "path": "Trips", "fmt": {"bix": 8, "len": 24, "max": 16777215, "unit": "kilometers" }, "name": "Odometer", "suggestedMetric": "odometer"}
                ]},
            ]
        }

        data2 = {
            'commands': [
                { "hdr": "747", "rax": "74F", "fcm1": True, "dbg": True, "cmd": {"22": "0103"}, "freq": 10,
                "signals": [
                    {"id": "CAMRY_ODO", "path": "Trips", "fmt": {"bix": 8, "len": 24, "max": 16777215, "unit": "kilometers" }, "name": "Odometer", "suggestedMetric": "odometer"}
                ]},
            ]
        }

        # Instead of mocking file operations, directly use the in-memory process_signalsets function
        loaded_signalsets = [
            (data1, 'file1.json'),
            (data2, 'file2.json')
        ]

        # Call the process_signalsets function directly with the in-memory data
        result = process_signalsets(loaded_signalsets, 'Toyota', 'Camry', signal_prefix='TOYOTA')

        self.maxDiff = None
        self.assertDictEqual(result, {
            '_signal_origins': {'TOYOTA_ODO': [{'file': 'file1.json',
                'make': 'Toyota',
                'model': 'Camry',
                'repo': 'Toyota-Camry'
            }]},
            'commands': [
                { "hdr": "701", "rax": "709", "dbg": True, "cmd": {"22": "0103"}, "freq": 10,
                "signals": [
                    {"id": "TOYOTA_ODO", "path": "Trips", "fmt": {"bix": 8, "len": 24, "max": 16777215, "unit": "kilometers" }, "name": "Odometer", "suggestedMetric": "odometer"}
                ]},
                { "hdr": "747", "rax": "74F", "fcm1": True, "dbg": True, "cmd": {"22": "0103"}, "freq": 10,
                "signals": [
                    {"id": "TOYOTA_ODO", "path": "Trips", "fmt": {"bix": 8, "len": 24, "max": 16777215, "unit": "kilometers" }, "name": "Odometer", "suggestedMetric": "odometer"}
                ]},
            ]
        })

    @patch('signalsets.utils.extract_year_range_from_filename')
    @patch('builtins.open')
    def test_merge_signalsets_with_year_range(self, mock_open, mock_extract_year):
        # Mock the year range extraction
        mock_extract_year.return_value = (2016, 2020)

        # Mock file data
        mock_data = {
            'commands': [
                {
                    'hdr': '7E0',
                    'eax': '00',
                    'cmd': {'22': '0110'},
                    'signals': [
                        {
                            'id': 'VSS',
                            'name': 'Vehicle Speed',
                            'type': 'UINT8',
                            'unit': 'km/h'
                        }
                    ]
                }
            ]
        }

        # Mock the open function
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_data)

        # Create a mock Path object
        path = MagicMock()
        path.name = '2016-2020.json'

        # Call the function
        result = merge_signalsets([path], 'Toyota', 'Camry')

        # Check that the year range info is in the signal origins
        self.assertIn('yearRange', result['_signal_origins']['VSS'][0])
        self.assertEqual(result['_signal_origins']['VSS'][0]['yearRange']['start'], 2016)
        self.assertEqual(result['_signal_origins']['VSS'][0]['yearRange']['end'], 2020)


class TestEnsureUniqueSignalIds(unittest.TestCase):

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
        result = ensure_unique_signal_ids(signalset)

        # Check that signal IDs remain unchanged
        self.assertEqual(signalset["commands"][0]["signals"][0]["id"], result["commands"][0]["signals"][0]["id"])
        self.assertEqual(signalset["commands"][0]["signals"][1]["id"], result["commands"][0]["signals"][1]["id"])
        self.assertEqual(signalset["commands"][1]["signals"][0]["id"], result["commands"][1]["signals"][0]["id"])

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
        result = ensure_unique_signal_ids(signalset)

        # Check that the second signal got versioned
        self.assertEqual(result["commands"][0]["signals"][0]["id"], "SIGNAL_1")
        self.assertEqual(result["commands"][1]["signals"][0]["id"], "SIGNAL_1_V2")

    def test_ensure_unique_signal_ids_with_identical_duplicates(self):
        """Test that identical duplicate signals are also versioned."""
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
        result = ensure_unique_signal_ids(signalset)

        # Check that the second signal got versioned despite identical definition
        self.assertEqual(result["commands"][0]["signals"][0]["id"], "SIGNAL_1")
        self.assertEqual(result["commands"][1]["signals"][0]["id"], "SIGNAL_1_V2")

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
        result = ensure_unique_signal_ids(signalset)

        # Check that the signals got properly versioned
        self.assertEqual(result["commands"][0]["signals"][0]["id"], "SIGNAL_1")
        self.assertEqual(result["commands"][1]["signals"][0]["id"], "SIGNAL_1_V2")
        self.assertEqual(result["commands"][2]["signals"][0]["id"], "SIGNAL_1_V3")

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
        result = ensure_unique_signal_ids(signalset)

        # Check that the signal origins were updated for the versioned ID
        self.assertIn("SIGNAL_1", result["_signal_origins"])
        self.assertIn("SIGNAL_1_V2", result["_signal_origins"])
        self.assertEqual(
            result["_signal_origins"]["SIGNAL_1"],
            result["_signal_origins"]["SIGNAL_1_V2"]
        )

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
        result = ensure_unique_signal_ids(signalset)

        # Check that the signal without ID was preserved as-is
        self.assertEqual(result["commands"][0]["signals"][0]["id"], "SIGNAL_1")
        self.assertNotIn("id", result["commands"][0]["signals"][1])
        self.assertEqual(result["commands"][0]["signals"][1]["name"], "Signal without ID")


if __name__ == '__main__':
    unittest.main()