# Copyright 2026 Veritas
# SPDX-License-Identifier: Apache-2.0
"""KEYS.md stays machine-checkable: every key line is one id and one
SHA-256 fingerprint, no id twice."""

import pathlib
import re
import unittest

KEYS = pathlib.Path(__file__).resolve().parents[1] / "KEYS.md"
LINE = re.compile(r"^- `(?P<kid>(?:openbao|local)-v[1-9][0-9]*)`: `sha256:(?P<fp>[0-9a-f]{64})` \(.+\)$")


def entries():
    section = KEYS.read_text().split("## Keys", 1)[1]
    return [line for line in section.splitlines() if line.startswith("- ")]


class KeysFileTest(unittest.TestCase):
    def test_every_key_line_is_an_id_and_a_fingerprint(self):
        for line in entries():
            self.assertRegex(line, LINE)

    def test_no_key_id_is_listed_twice(self):
        ids = [LINE.match(line)["kid"] for line in entries() if LINE.match(line)]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
