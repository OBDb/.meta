#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from signalsets.extractor import extract_data

COMMAND = {"hdr": "7E0", "cmd": {"22": "0101"}, "freq": 1,
           "signals": [{"id": "X_A", "name": "A", "fmt": {"len": 8}}]}


class TestNotice(unittest.TestCase):

    def extract(self, notices):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            for repo, notice in notices.items():
                directory = workspace / repo / "signalsets" / "v3"
                directory.mkdir(parents=True)
                signalset = {"commands": [COMMAND]}
                if notice:
                    signalset["notice"] = notice
                (directory / "default.json").write_text(json.dumps(signalset))
            return extract_data(str(workspace), str(Path(root) / "build"), force=True,
                                filter_prefixes=["Kia-"])

    def test_the_models_notice_reaches_the_make(self):
        merged = self.extract({"Kia-EV6": "Email us.", "Kia-Niro": "Email us.", "Kia-Soul": None})
        self.assertEqual(merged["notice"], "Email us.")

    def test_the_most_common_notice_wins_while_a_change_rolls_out(self):
        merged = self.extract({"Kia-EV6": "New.", "Kia-Niro": "Old.", "Kia-Soul": "New."})
        self.assertEqual(merged["notice"], "New.")

    def test_no_model_notice_means_no_make_notice(self):
        self.assertNotIn("notice", self.extract({"Kia-EV6": None}))


if __name__ == "__main__":
    unittest.main()
