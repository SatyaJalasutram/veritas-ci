# SPDX-License-Identifier: Apache-2.0
"""action.yml's shell steps, run with bash and a stand-in `gh` on PATH:
the gate's exit code, and the pull request comment created once, then updated."""

import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

import yaml

ACTION = yaml.safe_load(pathlib.Path(__file__).resolve().parents[1].joinpath("action.yml").read_text())
STEPS = ACTION["runs"]["steps"]
AGENT = "3f0c2a4e-0000-4000-8000-000000000001"

FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
if [ "$2" = "--paginate" ]; then cat "$GH_COMMENTS"; exit 0; fi
[ -n "$GH_FAIL" ] && exit 1
exit 0
"""


class ActionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.dir.name)
        (d / "bin").mkdir()
        gh = d / "bin" / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.d = d
        self.env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(d),
                    "GH_LOG": str(d / "gh.log"), "GH_COMMENTS": str(d / "comments"), "GITHUB_OUTPUT": str(d / "out"),
                    "GH_TOKEN": "t", "REPO": "acme/agent", "PR": "7", "AGENT_ID": AGENT.upper()}
        (d / "comments").write_text("")

    def tearDown(self):
        self.dir.cleanup()

    def step(self, name_or_id, **env):
        step = next(s for s in STEPS if name_or_id in (s.get("id"), s.get("name")))
        return subprocess.run(["bash", "-e", "-c", step["run"]], env={**self.env, **env},
                              capture_output=True, text=True)

    def log(self):
        p = self.d / "gh.log"
        return p.read_text().splitlines() if p.exists() else []

    def test_the_gate_step_exits_with_the_verdicts_code(self):
        for code in ("0", "1", "2", ""):
            self.assertEqual(self.step("Gate", CODE=code).returncode, int(code or 2))

    def test_the_comment_is_created_then_updated(self):
        (self.d / "veritas-summary.md").write_text(f"<!-- veritas-ci:{AGENT} -->\nresult\n")
        self.assertEqual(self.step("Comment on the pull request").returncode, 0)
        self.assertTrue(self.log()[-1].startswith("api -X POST repos/acme/agent/issues/7/comments"))
        # Next push: the comment carrying this agent's marker is found and edited.
        (self.d / "comments").write_text("991\n")
        self.assertEqual(self.step("Comment on the pull request").returncode, 0)
        self.assertTrue(self.log()[-1].startswith("api -X PATCH repos/acme/agent/issues/comments/991"))
        # Found by this agent's marker, whatever case the agent-id input was given in.
        self.assertIn(f'startswith("<!-- veritas-ci:{AGENT} -->")', self.log()[-2])

    def test_a_token_that_cannot_comment_warns_and_never_fails_the_job(self):
        (self.d / "veritas-summary.md").write_text("x")
        r = self.step("Comment on the pull request", GH_FAIL="1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("::warning::", r.stdout)

    def test_nothing_is_posted_when_the_run_never_started(self):
        self.assertEqual(self.step("Comment on the pull request").returncode, 0)
        self.assertEqual(self.log(), [])

    def test_a_malformed_agent_id_is_never_put_into_the_query(self):
        (self.d / "veritas-summary.md").write_text("x")
        r = self.step("Comment on the pull request", AGENT_ID='x") | .id, ("')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.log(), [])


if __name__ == "__main__":
    unittest.main()
