"""Static checks on the data-pipeline workflows (no network, no GitHub)."""
import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:      # pragma: no cover
    yaml = None

WF = Path(__file__).parents[1] / ".github" / "workflows"


def load(name):
    return yaml.safe_load((WF / name).read_text())


def steps(wf):
    return wf["jobs"]["fetch"]["steps"]


@unittest.skipIf(yaml is None, "PyYAML not installed")
class WorkflowTests(unittest.TestCase):
    CAMPUS, FETCH = "bmo-campus-energy.yml", "bmo-fetch.yml"

    def triggers(self, wf):
        return wf.get("on") or wf.get(True)    # YAML 1.1 parses bare `on` as True

    def test_parse_and_triggers_kept(self):
        for name, cron in ((self.CAMPUS, "*/15 * * * *"), (self.FETCH, "7,22,37,52 * * * *")):
            t = self.triggers(load(name))
            self.assertEqual(t["schedule"][0]["cron"], cron)
            self.assertIn("workflow_dispatch", t)

    def test_python_312_everywhere(self):
        for name in (self.CAMPUS, self.FETCH):
            versions = [s["with"]["python-version"] for s in steps(load(name))
                        if str(s.get("uses", "")).startswith("actions/setup-python")]
            self.assertEqual([str(v) for v in versions], ["3.12"])

    def test_pip_dependencies_are_pinned(self):
        for name in (self.CAMPUS, self.FETCH):
            for s in steps(load(name)):
                run = s.get("run", "")
                if "pip install" in run:
                    pkgs = [p for p in run.split("pip install")[1].split() if not p.startswith("-")]
                    self.assertTrue(pkgs)
                    for p in pkgs:
                        self.assertRegex(p, r"^[A-Za-z0-9_.-]+==\d+(\.\d+)+$", p)

    def test_no_silent_or_true_swallowing(self):
        for name in (self.CAMPUS, self.FETCH):
            for s in steps(load(name)):
                self.assertNotRegex(s.get("run", ""), r"\|\|\s*true", s.get("name"))

    def test_postprocessing_failures_are_visible_not_fatal(self):
        wf = load(self.CAMPUS)
        post = [s for s in steps(wf)
                if re.search(r"scripts/(build_baseline|towt_baseline|build_mv)\.py|generate_weekly_report", s.get("run", ""))]
        self.assertEqual(len(post), 4)
        for s in post:
            self.assertIs(s.get("continue-on-error"), True, s["name"])
            self.assertTrue(s.get("id"), s["name"])
        text = (WF / self.CAMPUS).read_text()
        self.assertIn("::warning", text)
        self.assertIn("GITHUB_STEP_SUMMARY", text)

    def test_fetch_failure_blocks_commit(self):
        for name, script in ((self.CAMPUS, "bmo_fetch_campus.py"), (self.FETCH, "bmo_fetch.py")):
            ss = steps(load(name))
            fetch = next(s for s in ss if script in s.get("run", ""))
            self.assertNotIn("continue-on-error", fetch)
            commit = next(s for s in ss if "git push" in s.get("run", ""))
            self.assertNotIn("always()", str(commit.get("if", "")))
            self.assertNotIn("failure()", str(commit.get("if", "")))

    def test_push_retry_loop_fails_loudly(self):
        for name in (self.CAMPUS, self.FETCH):
            run = next(s["run"] for s in steps(load(name)) if "git push" in s.get("run", ""))
            self.assertIn("exit 1", run)


if __name__ == "__main__":
    unittest.main()
