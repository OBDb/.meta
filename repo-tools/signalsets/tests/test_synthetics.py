#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.extractor import extract_data

POSITION_MAP = {
    "1": {"description": "Front left", "value": "FL"},
    "2": {"description": "Front right", "value": "FR"},
}


def slot_map(prefix):
    return {
        "hdr": "750", "eax": "2A", "cmd": {"22": "2021"}, "freq": 86400,
        "signals": [
            {"id": f"{prefix}_TID_1", "path": "Tires", "name": "Tire 1 position", "fmt": {"len": 8, "map": POSITION_MAP}},
            {"id": f"{prefix}_TID_2", "path": "Tires", "name": "Tire 2 position", "fmt": {"bix": 8, "len": 8, "map": POSITION_MAP}},
        ],
    }


def pressures(prefix, first_bix=8):
    return {
        "hdr": "750", "rax": "758", "eax": "2A", "cmd": {"22": "1005"}, "freq": 15,
        "signals": [
            {"id": f"{prefix}_TP_1", "path": "Tires", "name": "Tire sensor 1 pressure",
             "fmt": {"bix": first_bix, "len": 8, "max": 56.12, "div": 4.125, "unit": "psi"}},
            {"id": f"{prefix}_TP_2", "path": "Tires", "name": "Tire sensor 2 pressure",
             "fmt": {"bix": 24, "len": 8, "max": 56.12, "div": 4.125, "unit": "psi"}},
        ],
    }


def front_left(prefix, **overrides):
    synthetic = {
        "id": f"{prefix}_TP_FL_SLOT", "name": "Front left tire pressure", "path": "Tires",
        "min": 0, "max": 56.12, "unit": "psi", "suggestedMetric": "frontLeftTirePressure",
        "formula": {"op": "select", "match": "FL",
                    "cases": {f"{prefix}_TID_1": f"{prefix}_TP_1", f"{prefix}_TID_2": f"{prefix}_TP_2"}},
    }
    synthetic.update(overrides)
    return synthetic


class TestCarrySynthetics(unittest.TestCase):

    def extract(self, repos):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            for name, signalset in repos.items():
                signalsets = workspace / name / "signalsets" / "v3"
                signalsets.mkdir(parents=True)
                (signalsets / "default.json").write_text(json.dumps(signalset))
            output = Path(root) / "build"
            extract_data(workspace, output, force=True, filter_prefixes=["Lexus-"], signal_prefix="LEXUS")
            return json.loads((output / "merged_signalset.json").read_text())

    def test_carries_a_synthetic_under_the_make_prefix(self):
        merged = self.extract({
            "Lexus-IS": {"commands": [slot_map("IS"), pressures("IS")], "synthetics": [front_left("IS")]},
        })
        self.assertEqual(merged["synthetics"], [front_left("LEXUS")])

    def test_keeps_one_copy_of_a_synthetic_two_models_share(self):
        merged = self.extract({
            "Lexus-ES": {"commands": [slot_map("ES"), pressures("ES")], "synthetics": [front_left("ES")]},
            "Lexus-IS": {"commands": [slot_map("IS"), pressures("IS")], "synthetics": [front_left("IS")]},
        })
        self.assertEqual(merged["synthetics"], [front_left("LEXUS")])

    def test_follows_the_signal_the_make_keeps_for_a_conflicting_one(self):
        # The IS reads slot 1 at another bit. The make keeps the first model's
        # TP_1 for the command, so the IS's synthetic reads that one, and the
        # two synthetics are then the same.
        merged = self.extract({
            "Lexus-ES": {"commands": [slot_map("ES"), pressures("ES")], "synthetics": [front_left("ES")]},
            "Lexus-IS": {"commands": [slot_map("IS"), pressures("IS", first_bix=0)], "synthetics": [front_left("IS")]},
        })
        signals = {s["id"]: s for c in merged["commands"] for s in c["signals"]}
        self.assertEqual(signals["LEXUS_TP_1"]["fmt"]["bix"], 8)
        self.assertEqual(merged["synthetics"], [front_left("LEXUS")])

    def test_versions_a_synthetic_that_differs_under_the_same_id(self):
        merged = self.extract({
            "Lexus-ES": {"commands": [slot_map("ES"), pressures("ES")], "synthetics": [front_left("ES")]},
            "Lexus-IS": {"commands": [slot_map("IS"), pressures("IS")], "synthetics": [front_left("IS", max=50)]},
        })
        self.assertEqual(merged["synthetics"], [
            front_left("LEXUS"),
            front_left("LEXUS", id="LEXUS_TP_FL_SLOT_V2", max=50),
        ])

    def test_rewrites_a_ratio(self):
        ratio = {"id": "IS_TP_RATIO", "name": "Pressure ratio", "path": "Tires", "max": 2, "unit": "scalar",
                 "formula": {"op": "ratio", "a": "IS_TP_1", "b": "IS_TP_2"}}
        merged = self.extract({"Lexus-IS": {"commands": [pressures("IS")], "synthetics": [ratio]}})
        self.assertEqual(merged["synthetics"][0]["id"], "LEXUS_TP_RATIO")
        self.assertEqual(merged["synthetics"][0]["formula"], {"op": "ratio", "a": "LEXUS_TP_1", "b": "LEXUS_TP_2"})

    def test_leaves_out_a_synthetic_whose_signals_are_missing(self):
        # Without the slot map command, the select has nothing to read.
        merged = self.extract({
            "Lexus-IS": {"commands": [pressures("IS")], "synthetics": [front_left("IS")]},
        })
        self.assertNotIn("synthetics", merged)

    def test_leaves_out_an_unknown_op(self):
        unknown = {"id": "IS_X", "name": "X", "path": "Tires", "max": 1, "unit": "scalar",
                   "formula": {"op": "future", "a": "IS_TP_1"}}
        merged = self.extract({"Lexus-IS": {"commands": [pressures("IS")], "synthetics": [unknown]}})
        self.assertNotIn("synthetics", merged)


if __name__ == "__main__":
    unittest.main()
