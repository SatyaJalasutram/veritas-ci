# SPDX-License-Identifier: Apache-2.0
"""This repository's own workflow files parse, and each says when it runs and
what it does. GitHub rejects an invalid file only once it is pushed (a run
with no jobs, marked failed), as staging-check.yml was on its first push: an
unquoted ": " inside a `run:` value is not YAML."""

import pathlib
import unittest

import yaml

WORKFLOWS = sorted(pathlib.Path(__file__).resolve().parents[1].joinpath(".github", "workflows").glob("*.yml"))


class WorkflowFilesTest(unittest.TestCase):
    def test_there_are_workflows_to_check(self):
        self.assertEqual({w.name for w in WORKFLOWS}, {"release.yml", "staging-check.yml", "test.yml"})

    def test_every_workflow_parses_with_triggers_and_jobs(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                doc = yaml.safe_load(workflow.read_text())
                # PyYAML reads the bare key `on` as the boolean True (YAML 1.1).
                self.assertTrue(doc.get("on") or doc.get(True), "no trigger")
                self.assertTrue(doc.get("jobs"), "no jobs")
                for job in doc["jobs"].values():
                    for step in job.get("steps", []):
                        self.assertIsInstance(step.get("run", ""), str)

    def test_a_release_works_from_a_pushed_tag_or_a_release_published_on_github(self):
        release = yaml.safe_load(WORKFLOWS[0].read_text())
        triggers = release.get("on") or release.get(True)
        self.assertEqual(triggers["push"]["tags"], ["v[0-9]+.[0-9]+.[0-9]+"])
        self.assertEqual(triggers["release"]["types"], ["published"])
        publish = next(s["run"] for s in release["jobs"]["release"]["steps"]
                       if s.get("name") == "Publish the release, with KEYS.md")
        # A release published on GitHub fires both events: creating it again would fail the run.
        self.assertIn('gh release view "$GITHUB_REF_NAME"', publish)

    def test_keys_md_is_attached_as_the_release_is_created_and_never_replaced(self):
        # Releases are immutable (owner, 22 Oct night): no upload to, and no
        # --clobber of, an existing release.
        text = WORKFLOWS[0].read_text()
        self.assertIn('gh release create "$GITHUB_REF_NAME" KEYS.md', text)
        self.assertNotIn("--clobber", text)
        self.assertNotIn("gh release upload", text)

    def test_every_action_is_pinned_by_commit_sha(self):
        for workflow in WORKFLOWS:
            for line in workflow.read_text().splitlines():
                if "uses:" in line and "uses: ./" not in line:
                    with self.subTest(workflow=workflow.name, line=line.strip()):
                        self.assertRegex(line, r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
