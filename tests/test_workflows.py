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

    def test_a_release_works_by_hand_from_a_pushed_tag_or_a_release_published_on_github(self):
        release = yaml.safe_load(WORKFLOWS[0].read_text())
        triggers = release.get("on") or release.get(True)
        self.assertEqual(triggers["workflow_dispatch"]["inputs"]["version"]["required"], True)
        self.assertEqual(triggers["push"]["tags"], ["v[0-9]+.[0-9]+.[0-9]+"])
        self.assertEqual(triggers["release"]["types"], ["published"])
        job = release["jobs"]["release"]
        self.assertEqual(job["env"]["TAG"], "${{ inputs.version || github.ref_name }}")
        steps = {s.get("name"): s for s in job["steps"]}
        publish = steps["Publish the release, with KEYS.md"]["run"]
        # A release published on GitHub fires both events: creating it again would fail the run.
        self.assertIn('gh release view "$TAG"', publish)

    def test_a_manual_release_runs_on_main_and_tags_main_through_the_api(self):
        release = yaml.safe_load(WORKFLOWS[0].read_text())
        steps = {s.get("name"): s for s in release["jobs"]["release"]["steps"]}
        on_main = steps["A manual release runs on main"]
        self.assertEqual(on_main["if"], "github.event_name == 'workflow_dispatch'")
        self.assertIn("refs/heads/main", on_main["run"])
        tag = steps["Create the tag on main's head"]
        self.assertEqual(tag["if"], "github.event_name == 'workflow_dispatch'")
        self.assertIn('git/refs" -f ref="refs/tags/$TAG" -f sha="$GITHUB_SHA"', tag["run"])
        # An existing tag is refused, never moved.
        self.assertIn("already exists", tag["run"])
        names = list(steps)
        for check in ("The tag is a version, vX.Y.Z", "The tag matches the CLI's version", "KEYS.md is here to attach"):
            self.assertLess(names.index(check), names.index("Create the tag on main's head"), check)

    def test_the_version_input_never_reaches_a_script_directly(self):
        # Only through the TAG variable: an input pasted into `run:` is a script injection.
        text = WORKFLOWS[0].read_text()
        for line in text.splitlines():
            if "inputs.version" in line:
                self.assertTrue(line.strip().startswith(("TAG:", "group:")), line)

    def test_keys_md_is_attached_as_the_release_is_created_and_never_replaced(self):
        # Releases are immutable (owner, 22 Oct night): no upload to, and no
        # --clobber of, an existing release; and every release is checked for it.
        text = WORKFLOWS[0].read_text()
        self.assertIn('gh release create "$TAG" KEYS.md', text)
        self.assertIn("grep -qx KEYS.md", text)
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
