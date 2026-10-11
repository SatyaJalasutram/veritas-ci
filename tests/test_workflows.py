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


if __name__ == "__main__":
    unittest.main()
