#!/usr/bin/env python3
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add parent directory to path to import the module being tested
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.model_years import (
    load_model_year_data,
    save_model_year_data,
    CompactJSONEncoder
)


class TestModelYears(unittest.TestCase):

    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    def test_load_model_year_data(self, mock_exists, mock_file):
        # Mock the path exists check
        mock_exists.return_value = True

        # Mock file contents for model year data
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps({
            "2016": {
                "ecus": [
                    {
                        "name": "Engine Control Module",
                        "pids": ["01", "03", "04", "05"]
                    }
                ]
            },
            "2017": {
                "ecus": [
                    {
                        "name": "Engine Control Module",
                        "pids": ["01", "03", "04", "05", "06"]
                    }
                ]
            }
        })

        # Create a mock Path object for repository
        repo_dir = MagicMock()
        mock_exists.return_value = True

        # Call the function
        result = load_model_year_data(repo_dir, 'Toyota', 'Camry')

        # Check the result
        self.assertEqual(result['make'], 'Toyota')
        self.assertEqual(result['model'], 'Camry')
        self.assertIn('modelYears', result)
        self.assertIn('2016', result['modelYears'])
        self.assertIn('2017', result['modelYears'])

    @patch('builtins.open', new_callable=mock_open)
    @patch('pathlib.Path.exists')
    def test_load_model_year_data_not_found(self, mock_exists, mock_file):
        # Mock the path exists check
        mock_exists.return_value = False

        # Create a mock Path object for repository
        repo_dir = MagicMock()

        # Call the function
        result = load_model_year_data(repo_dir, 'Toyota', 'Camry')

        # Check that None is returned when file doesn't exist
        self.assertIsNone(result)

    @patch('builtins.open', new_callable=mock_open)
    def test_save_model_year_data(self, mock_file):
        # Test data
        model_year_data = [
            {
                'make': 'Toyota',
                'model': 'Camry',
                'modelYears': {
                    '2016': {
                        'ecus': [
                            {
                                'name': 'Engine Control Module',
                                'pids': ['01', '03', '04', '05']
                            }
                        ]
                    }
                }
            },
            {
                'make': 'Honda',
                'model': 'Accord',
                'modelYears': {
                    '2018': {
                        'ecus': [
                            {
                                'name': 'Engine Control Module',
                                'pids': ['01', '03', '07']
                            }
                        ]
                    }
                }
            }
        ]

        # Mock the output path
        output_path = MagicMock()

        # Call the function
        result = save_model_year_data(model_year_data, output_path)

        # Check that the function returned True
        self.assertTrue(result)

        # Check that the file was written with the expected content
        mock_file.assert_called_once_with(output_path, 'w')
        handle = mock_file()
        handle.write.assert_called_once()

    def test_save_model_year_data_empty(self):
        # Test with empty data
        result = save_model_year_data([], MagicMock())
        self.assertFalse(result)

    def test_compact_json_encoder(self):
        # Test the custom JSON encoder
        encoder = CompactJSONEncoder()
        
        # Test encoding of string arrays
        string_array = ["01", "02", "03"]
        result = encoder.encode(string_array)
        self.assertEqual(result, '["01", "02", "03"]')
        
        # Test normal objects
        obj = {"key": "value"}
        result = encoder.encode(obj)
        self.assertIn("key", result)
        self.assertIn("value", result)


if __name__ == '__main__':
    unittest.main()