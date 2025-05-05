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

    def test_extract_year_range_from_filename(self):
        # Test valid filename format
        result = extract_signalsets.extract_year_range_from_filename('2016-2020.json')
        self.assertEqual(result, (2016, 2020))

        # Test another valid filename
        result = extract_signalsets.extract_year_range_from_filename('1998-2005.json')
        self.assertEqual(result, (1998, 2005))

        # Test invalid filename format
        result = extract_signalsets.extract_year_range_from_filename('default.json')
        self.assertIsNone(result)

        result = extract_signalsets.extract_year_range_from_filename('2020.json')
        self.assertIsNone(result)

        result = extract_signalsets.extract_year_range_from_filename('2016-202a.json')
        self.assertIsNone(result)

    def test_replace_signal_prefix(self):
        # Test with underscore in signal_id
        result = extract_signalsets.replace_signal_prefix('RAV4_VSS', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_VSS')

        # Test with multiple underscores
        result = extract_signalsets.replace_signal_prefix('CAMRY_ENGINE_RPM', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_ENGINE_RPM')

        # Test with no underscore
        result = extract_signalsets.replace_signal_prefix('SPEED', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_SPEED')

        # Test with empty signal_id
        result = extract_signalsets.replace_signal_prefix('', 'TOYOTA')
        self.assertEqual(result, '')

        # Test with None signal_id
        result = extract_signalsets.replace_signal_prefix(None, 'TOYOTA')
        self.assertIsNone(result)

        # Test with None prefix
        result = extract_signalsets.replace_signal_prefix('RAV4_VSS', None)
        self.assertEqual(result, 'RAV4_VSS')

    def test_are_signals_equal(self):
        # Test identical signals
        signal1 = {
            'id': 'TOYOTA_VSS',
            'name': 'Vehicle Speed',
            'description': 'Vehicle speed sensor',
            'path': 'vehicle.speed',
            'comment': 'Test comment',
            'type': 'UINT8',
            'unit': 'km/h',
            'offset': 0,
            'factor': 1
        }

        signal2 = signal1.copy()
        self.assertTrue(extract_signalsets.are_signals_equal(signal1, signal2))

        # Test different ID but same core attributes
        signal2['id'] = 'HONDA_VSS'
        self.assertTrue(extract_signalsets.are_signals_equal(signal1, signal2))

        # Test different names but same core attributes
        signal2['name'] = 'Different Name'
        self.assertTrue(extract_signalsets.are_signals_equal(signal1, signal2))

        # Test different description but same core attributes
        signal2['description'] = 'Different description'
        self.assertTrue(extract_signalsets.are_signals_equal(signal1, signal2))

        # Test different core attribute
        signal2['type'] = 'UINT16'
        self.assertFalse(extract_signalsets.are_signals_equal(signal1, signal2))

        # Test different unit
        signal2 = signal1.copy()
        signal2['unit'] = 'mph'
        self.assertFalse(extract_signalsets.are_signals_equal(signal1, signal2))

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
        result = extract_signalsets.merge_signalsets([mock_path], 'Toyota', 'Camry')

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
        result = extract_signalsets.merge_signalsets([mock_path], 'Toyota', 'Camry', signal_prefix='TOYOTA')

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
        result = extract_signalsets.process_signalsets(loaded_signalsets, 'Toyota', 'Camry', signal_prefix='TOYOTA')

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

    @patch('extract_signalsets.extract_year_range_from_filename')
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
        result = extract_signalsets.merge_signalsets([path], 'Toyota', 'Camry')

        # Check that the year range info is in the signal origins
        self.assertIn('yearRange', result['_signal_origins']['VSS'][0])
        self.assertEqual(result['_signal_origins']['VSS'][0]['yearRange']['start'], 2016)
        self.assertEqual(result['_signal_origins']['VSS'][0]['yearRange']['end'], 2020)

    def test_calculate_hash(self):
        # Test hash calculation for different data
        data1 = {'key': 'value'}
        data2 = {'key': 'value'}
        data3 = {'key': 'different'}

        # Same data should produce same hash
        hash1 = extract_signalsets.calculate_hash(data1)
        hash2 = extract_signalsets.calculate_hash(data2)
        self.assertEqual(hash1, hash2)

        # Different data should produce different hash
        hash3 = extract_signalsets.calculate_hash(data3)
        self.assertNotEqual(hash1, hash3)

        # Order shouldn't matter
        data4 = {'b': 2, 'a': 1}
        data5 = {'a': 1, 'b': 2}
        hash4 = extract_signalsets.calculate_hash(data4)
        hash5 = extract_signalsets.calculate_hash(data5)
        self.assertEqual(hash4, hash5)


if __name__ == '__main__':
    unittest.main()