"""Real pinned components in temporary prefixes. SPDX-License-Identifier: Apache-2.0."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="openrepokit-tests-")
        cls.root = Path(cls.temp.name)
        cls.prefix = cls.root / "prefix with spaces"
        cls.home = cls.root / "isolated-home"
        cls.home.mkdir()
        cls.env = dict(os.environ, HOME=str(cls.home),
                       CLAUDE_USER_DIR=str(cls.home / ".claude"),
                       CLAUDE_PROFILES_HOME=str(cls.home / ".claude-profiles"))
        blocked = cls.root / "blocked-network"
        blocked.mkdir()
        for name in ("gh", "curl"):
            path = blocked / name
            path.write_text("#!/bin/sh\necho 'network forbidden in Kit tests' >&2\nexit 97\n")
            path.chmod(0o755)
        cls.env["PATH"] = str(blocked) + os.pathsep + cls.env["PATH"]
        result = cls.call(sys.executable, CODE / "openRepoKit", "install", "--prefix", cls.prefix)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def call(cls, *args, env=None):
        return subprocess.run([str(a) for a in args], text=True, capture_output=True,
                              env=env or cls.env, cwd=cls.root)

    def test_versions_override_inherited_refs(self):
        rows = json.loads((CODE.parent / "spec/contracts/components.json").read_text())["components"]
        env = dict(self.env, OPENREPOSHAPE_REF="main", OPENREPOTOOLS_REF="main",
                   OPENREPOSHAPE_SETUP_SH="/missing", OPENREPOSHAPE_REPO="wrong/repo")
        for row in rows[:2]:
            result = self.call(self.prefix / "bin" / row["name"], "--version", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(row["commit"], result.stdout)

    def test_project_routing_and_shape_doctor(self):
        result = self.call(self.prefix / "bin/project", "new", "KitFixture", "--shape",
                           "--org", "example", "--visibility", "private", "--dry-run",
                           "--into", self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("openRepoShape KitFixture", result.stdout)
        result = self.call(self.prefix / "bin/openRepoShape", "--doctor", CODE.parent)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        self.assertNotIn("network forbidden", result.stderr)
        self.assertIn("manifest", result.stdout.lower())

    def test_project_discovers_openbenches_through_installed_launcher(self):
        home = self.root / "openbenches-home"
        checkout = home / "projects/openBenches"
        (checkout / "config").mkdir(parents=True)
        (checkout / "config/bench-config.json").write_text('{"benches": {}}\n')
        env = dict(self.env, HOME=str(home))
        env.pop("WORKBENCHES_ROOT", None)
        env.pop("PROJECTS_DIR", None)
        result = self.call(self.prefix / "bin/project", "benches", "--json", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_shape_preflight_uses_bundled_setup(self):
        result = self.call(self.prefix / "bin/openRepoShape", "--preflight")
        self.assertNotIn("network forbidden", result.stderr)
        self.assertNotIn("could not fetch", result.stderr)

    def test_component_self_install_refused(self):
        for name in ("openRepoShape", "openRepoTools"):
            result = self.call(self.prefix / "bin" / name, "--install")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Kit owns", result.stderr)

    def test_missing_recursive_dependency_refused(self):
        checkout = self.root / "incomplete-code"
        result = self.call("git", "clone", "--quiet", "--no-hardlinks", CODE, checkout)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in json.loads((CODE.parent / "spec/contracts/components.json").read_text())["components"]:
            result = self.call("git", "clone", "--quiet", CODE / row["path"], checkout / row["path"])
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.call(sys.executable, checkout / "openRepoKit", "--manifest",
                           CODE.parent / "spec/contracts/components.json", "verify")
        self.assertEqual(result.returncode, 2)
        self.assertIn("recursive dependency", result.stderr)

    def test_installed_source_drift_refused(self):
        release = (self.prefix / "bin/project").resolve().parent
        source = release / "components/openRepoShape/openRepoShape"
        original = source.read_bytes()
        try:
            source.write_bytes(original + b"\n# test drift\n")
            result = self.call(sys.executable, CODE / "openRepoKit", "install", "--prefix", self.prefix)
            self.assertEqual(result.returncode, 2)
            self.assertIn("release was modified", result.stderr)
        finally:
            source.write_bytes(original)

    def test_default_install_preserves_user_claude(self):
        self.assertFalse((self.home / ".claude").exists())
        self.assertFalse((self.home / ".claude-profiles").exists())
        result = self.call(self.prefix / "bin/openRepoKit", "status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("openRepoProject", result.stdout)

    def test_repeat_install_and_collision(self):
        result = self.call(sys.executable, CODE / "openRepoKit", "install", "--prefix", self.prefix)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Already installed", result.stdout)
        prefix = self.root / "collision"
        (prefix / "bin").mkdir(parents=True)
        existing = prefix / "bin/project"
        existing.write_text("belongs to another installer\n")
        result = self.call(sys.executable, CODE / "openRepoKit", "install", "--prefix", prefix)
        self.assertEqual(result.returncode, 2)
        self.assertIn("collision", result.stderr)
        self.assertEqual(existing.read_text(), "belongs to another installer\n")
        self.assertFalse((prefix / "releases").exists())

    def test_contract_drift_refuses_before_install(self):
        manifest = self.root / "bad-contract.json"
        data = json.loads((CODE.parent / "spec/contracts/components.json").read_text())
        data["components"][0]["commit"] = "0" * 40
        manifest.write_text(json.dumps(data))
        prefix = self.root / "must-not-exist"
        result = self.call(sys.executable, CODE / "openRepoKit", "--manifest", manifest,
                           "install", "--prefix", prefix)
        self.assertEqual(result.returncode, 2)
        self.assertIn("gitlink differs", result.stderr)
        self.assertFalse(prefix.exists())


if __name__ == "__main__":
    unittest.main()
