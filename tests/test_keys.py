# Copyright 2026 Veritas
# SPDX-License-Identifier: Apache-2.0
"""KEYS.md stays machine-checkable: every key line is one id naming its
deployment (production-vN or staging-vN) and one SHA-256 fingerprint, no id
twice, and every staging line says it never signs customer evidence."""

import pathlib
import re
import unittest

KEYS = pathlib.Path(__file__).resolve().parents[1] / "KEYS.md"
LINE = re.compile(r"^- `(?P<kid>(?P<deployment>production|staging)-v[1-9][0-9]*)`: `sha256:(?P<fp>[0-9a-f]{64})` \(.+\)$")
STAGING_MARK = "staging: never used for customer evidence"


def entries():
    section = KEYS.read_text().split("## Keys", 1)[1]
    return [line for line in section.splitlines() if line.startswith("- ")]


class KeysFileTest(unittest.TestCase):
    def test_every_key_line_is_an_id_and_a_fingerprint(self):
        for line in entries():
            self.assertRegex(line, LINE)

    def test_the_keys_section_lists_at_least_one_key_once_staging_has_one(self):
        # entries() only counts lines starting with the exact two characters
        # "- " (so does backend/app/execute/keytrust.py's own parser): a key
        # line indented by even one space is silently excluded from both,
        # not flagged. Every test above iterates `entries()` and passes
        # vacuously on an empty list, so a mis-indented line was invisible
        # here too (found 29 Oct: KEYS.md's first staging-v1 line had 3
        # leading spaces from a GitHub web edit; `keypins sync` kept
        # printing "pins: none" with no error, through two releases, until
        # caught by hand against the real deploy). Once this file has ever
        # listed a key (the one-line marker below is gone), entries() must
        # be non-empty, or a line like it is sitting there unindexed.
        if "No key is listed yet" not in KEYS.read_text():
            self.assertTrue(entries(), "KEYS.md has a '## Keys' section with no placeholder line, "
                             "but entries() found none — a key line is likely mis-indented")

    def test_every_staging_key_is_marked_as_never_signing_customer_evidence(self):
        for line in entries():
            match = LINE.match(line)
            if match and match["deployment"] == "staging":
                self.assertIn(STAGING_MARK, line)

    def test_the_line_format_accepts_both_deployments_and_nothing_else(self):
        fp = "a" * 64
        self.assertRegex(f"- `production-v1`: `sha256:{fp}` (production, since 2026-11-01)", LINE)
        self.assertRegex(f"- `staging-v2`: `sha256:{fp}` (staging, since 2026-10-30; {STAGING_MARK})", LINE)
        for bad in (f"- `openbao-v1`: `sha256:{fp}` (x)", f"- `local-v1`: `sha256:{fp}` (x)",
                    f"- `production-v0`: `sha256:{fp}` (x)"):
            self.assertNotRegex(bad, LINE)

    def test_no_key_id_is_listed_twice(self):
        ids = [LINE.match(line)["kid"] for line in entries() if LINE.match(line)]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
