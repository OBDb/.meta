#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.ecu import merge_ecu_entries
from signalsets.processor import process_signalsets


class TestMergeEcuEntries(unittest.TestCase):

    def test_an_address_every_mapping_model_agrees_on_carries_over(self):
        agreed, dropped = merge_ecu_entries({
            "Ford-Escape": [{"hdr": "7E0", "type": "engine"}],
            "Ford-F-150": [{"hdr": "7E0", "type": "engine"}],
        })
        self.assertEqual(agreed, [{"hdr": "7E0", "type": "engine"}])
        self.assertEqual(dropped, [])

    def test_models_without_a_mapping_abstain(self):
        agreed, _ = merge_ecu_entries({
            "Ford-Escape": [{"hdr": "7E4", "type": "battery"}],
            "Ford-F-150": [],
        })
        self.assertEqual(agreed, [{"hdr": "7E4", "type": "battery"}])

    def test_models_that_disagree_drop_the_address(self):
        agreed, dropped = merge_ecu_entries({
            "Honda-Civic": [{"hdr": "DA10", "type": "engine"}],
            "Honda-Pilot": [{"hdr": "DA10", "type": "transmission"}],
        })
        self.assertEqual(agreed, [])
        self.assertEqual(dropped, [{
            "hdr": "DA10",
            "types": {"Honda-Civic": ["engine"], "Honda-Pilot": ["transmission"]},
        }])

    def test_one_model_splitting_an_address_by_year_drops_it(self):
        agreed, dropped = merge_ecu_entries({
            "Ford-Focus": [
                {"hdr": "7E4", "filter": {"to": 2018}, "type": "battery"},
                {"hdr": "7E4", "filter": {"from": 2019}, "type": "charger"},
            ],
        })
        self.assertEqual(agreed, [])
        self.assertEqual(len(dropped), 1)

    def test_filters_are_dropped_when_every_year_agrees(self):
        agreed, _ = merge_ecu_entries({
            "Ford-Focus-Electric": [{"hdr": "7E4", "filter": {"from": 2012, "to": 2018}, "type": "battery"}],
        })
        self.assertEqual(agreed, [{"hdr": "7E4", "type": "battery"}])

    def test_addresses_differ_by_extended_and_receive_address(self):
        agreed, _ = merge_ecu_entries({
            "BMW-X5": [
                {"hdr": "6F1", "eax": "12", "type": "engine"},
                {"hdr": "6F1", "eax": "18", "type": "transmission"},
            ],
            "Volkswagen-Golf": [{"hdr": "FC00", "rax": "FE0076", "type": "engine"}],
        })
        self.assertEqual(agreed, [
            {"hdr": "6F1", "eax": "12", "type": "engine"},
            {"hdr": "6F1", "eax": "18", "type": "transmission"},
            {"hdr": "FC00", "rax": "FE0076", "type": "engine"},
        ])

    def test_no_entries_give_nothing(self):
        self.assertEqual(merge_ecu_entries({"Ford-Escape": []}), ([], []))


class TestProcessSignalsetsEcu(unittest.TestCase):

    def test_ecu_entries_from_every_file_are_collected(self):
        result = process_signalsets([
            ({"ecu": [{"hdr": "7E0", "type": "engine"}], "commands": []}, "default.json"),
            ({"ecu": [{"hdr": "7E1", "type": "transmission"}], "commands": []}, "2019-2023.json"),
        ], "Ford", "Escape")
        self.assertEqual(result["ecu"], [
            {"hdr": "7E0", "type": "engine"},
            {"hdr": "7E1", "type": "transmission"},
        ])

    def test_a_repo_without_ecu_adds_no_key(self):
        result = process_signalsets([({"commands": []}, "default.json")], "Ford", "Escape")
        self.assertNotIn("ecu", result)


if __name__ == "__main__":
    unittest.main()
