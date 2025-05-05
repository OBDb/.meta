#!/usr/bin/env python3
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add parent directory to path to import the module being tested
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.utils import (
    calculate_hash,
    extract_year_range_from_filename,
    replace_signal_prefix,
    are_signals_equal
)


class TestSignalsetsUtils(unittest.TestCase):

    def test_extract_year_range_from_filename(self):
        # Test valid filename format
        result = extract_year_range_from_filename('2016-2020.json')
        self.assertEqual(result, (2016, 2020))

        # Test another valid filename
        result = extract_year_range_from_filename('1998-2005.json')
        self.assertEqual(result, (1998, 2005))

        # Test invalid filename format
        result = extract_year_range_from_filename('default.json')
        self.assertIsNone(result)

        result = extract_year_range_from_filename('2020.json')
        self.assertIsNone(result)

        result = extract_year_range_from_filename('2016-202a.json')
        self.assertIsNone(result)

    def test_replace_signal_prefix(self):
        # Test with underscore in signal_id
        result = replace_signal_prefix('RAV4_VSS', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_VSS')

        # Test with multiple underscores
        result = replace_signal_prefix('CAMRY_ENGINE_RPM', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_ENGINE_RPM')

        # Test with no underscore
        result = replace_signal_prefix('SPEED', 'TOYOTA')
        self.assertEqual(result, 'TOYOTA_SPEED')

        # Test with empty signal_id
        result = replace_signal_prefix('', 'TOYOTA')
        self.assertEqual(result, '')

        # Test with None signal_id
        result = replace_signal_prefix(None, 'TOYOTA')
        self.assertIsNone(result)

        # Test with None prefix
        result = replace_signal_prefix('RAV4_VSS', None)
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
        self.assertTrue(are_signals_equal(signal1, signal2))

        # Test different ID but same core attributes
        signal2['id'] = 'HONDA_VSS'
        self.assertTrue(are_signals_equal(signal1, signal2))

        # Test different names but same core attributes
        signal2['name'] = 'Different Name'
        self.assertTrue(are_signals_equal(signal1, signal2))

        # Test different description but same core attributes
        signal2['description'] = 'Different description'
        self.assertTrue(are_signals_equal(signal1, signal2))

        # Test different core attribute
        signal2['type'] = 'UINT16'
        self.assertFalse(are_signals_equal(signal1, signal2))

        # Test different unit
        signal2 = signal1.copy()
        signal2['unit'] = 'mph'
        self.assertFalse(are_signals_equal(signal1, signal2))

    def test_calculate_hash(self):
        # Test hash calculation for different data
        data1 = {'key': 'value'}
        data2 = {'key': 'value'}
        data3 = {'key': 'different'}

        # Same data should produce same hash
        hash1 = calculate_hash(data1)
        hash2 = calculate_hash(data2)
        self.assertEqual(hash1, hash2)

        # Different data should produce different hash
        hash3 = calculate_hash(data3)
        self.assertNotEqual(hash1, hash3)

        # Order shouldn't matter
        data4 = {'b': 2, 'a': 1}
        data5 = {'a': 1, 'b': 2}
        hash4 = calculate_hash(data4)
        hash5 = calculate_hash(data5)
        self.assertEqual(hash4, hash5)


if __name__ == '__main__':
    unittest.main()