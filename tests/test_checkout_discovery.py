"""Launcher checkout discovery in synthetic releases. SPDX-License-Identifier: Apache-2.0."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1]
COMPONENT_NAMES = ("openRepoShape", "openRepoTools", "openRepoProject")


class CheckoutDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openrepokit-discovery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.release = self.root / "release"
        self.release.mkdir()
        shutil.copy2(CODE / "launcher.py", self.release / "launcher.py")
        project = self.release / "components/openRepoProject/project"
        project.parent.mkdir(parents=True)
        project.write_text(
            "import json, os, sys\n"
            "print(json.dumps({\n"
            "    'root': os.environ.get('WORKBENCHES_ROOT'),\n"
            "    'has_openbenches_root': 'OPENBENCHES_ROOT' in os.environ,\n"
            "    'argv': sys.argv[1:],\n"
            "}))\n"
        )
        self.command = self.root / "bin/project"
        self.command.parent.mkdir()
        self.command.symlink_to(self.release / "launcher.py")
        self.env = dict(os.environ, HOME=str(self.home))
        for name in ("WORKBENCHES_ROOT", "OPENBENCHES_ROOT", "PROJECTS_DIR"):
            self.env.pop(name, None)
        self.write_manifest()

    def write_manifest(self, saved=None):
        rows = [{"name": name, "repository": f"opensoft/{name}", "commit": "0" * 40}
                for name in COMPONENT_NAMES]
        data = {"components": rows, "code_commit": "0" * 40,
                "spec_commit": "0" * 40, "workbenches": saved}
        (self.release / "manifest.json").write_text(json.dumps(data))

    def checkout(self, parent, basename, valid=True):
        path = parent / basename
        if valid:
            (path / "config").mkdir(parents=True)
            (path / "config/bench-config.json").write_text('{"benches": {}}\n')
        else:
            path.mkdir(parents=True)
        return path.resolve()

    def discover(self, env=None):
        environment = dict(self.env, **(env or {}))
        result = subprocess.run(
            [sys.executable, str(self.command), "benches", "--json"],
            cwd=self.root, env=environment, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["argv"], ["benches", "--json"])
        self.assertFalse(payload["has_openbenches_root"])
        return payload["root"]

    def test_old_only_in_both_projects_conventions(self):
        old = self.checkout(self.home / "projects", "workBenches")
        self.assertEqual(self.discover(), str(old))
        shutil.rmtree(old)
        old = self.checkout(self.home / "Projects", "workBenches")
        self.assertEqual(self.discover(), str(old))

    def test_new_only_in_both_projects_conventions(self):
        new = self.checkout(self.home / "projects", "openBenches")
        self.assertEqual(self.discover(), str(new))
        shutil.rmtree(new)
        new = self.checkout(self.home / "Projects", "openBenches")
        self.assertEqual(self.discover(), str(new))

    def test_both_present_prefers_new(self):
        old = self.checkout(self.home / "projects", "workBenches")
        new = self.checkout(self.home / "Projects", "openBenches")
        self.assertEqual(self.discover(), str(new))
        shutil.rmtree(new)
        new = self.checkout(self.home / "projects", "openBenches")
        self.assertEqual(self.discover(), str(new))
        self.assertTrue(old.exists())

    def test_invalid_new_candidate_falls_back_to_valid_old(self):
        self.checkout(self.home / "projects", "openBenches", valid=False)
        old = self.checkout(self.home / "Projects", "workBenches")
        self.assertEqual(self.discover(), str(old))

    def test_explicit_root_overrides_saved_and_discovered_paths(self):
        explicit = self.checkout(self.root, "explicit-workBenches")
        saved = self.checkout(self.root, "saved-workBenches")
        self.checkout(self.home / "projects", "openBenches")
        self.write_manifest(str(saved))
        self.assertEqual(self.discover({"WORKBENCHES_ROOT": str(explicit)}), str(explicit))

    def test_saved_release_metadata_overrides_discovery(self):
        saved_old = self.checkout(self.root, "saved-workBenches")
        saved_new = self.checkout(self.root, "saved-openBenches")
        self.checkout(self.home / "projects", "openBenches")
        self.checkout(self.home / "projects", "workBenches")
        for saved in (saved_old, saved_new):
            with self.subTest(saved=saved):
                self.write_manifest(str(saved))
                self.assertEqual(self.discover(), str(saved))
                data = json.loads((self.release / "manifest.json").read_text())
                self.assertEqual(data["workbenches"], str(saved))
                self.assertNotIn("openbenches", data)

    def test_existing_marker_is_not_bypassed_or_renamed(self):
        marked = self.checkout(self.root, "marked-workBenches")
        self.checkout(self.home / "projects", "openBenches")
        marker = self.release / ".workbenches-path"
        marker.write_text(str(marked) + "\n")
        self.assertIsNone(self.discover())
        self.assertEqual(marker.read_text(), str(marked) + "\n")
        self.assertFalse((self.release / ".openbenches-path").exists())

    def test_projects_dir_preserves_new_first_discovery(self):
        projects = self.root / "custom-projects"
        old = self.checkout(projects, "workBenches")
        self.checkout(self.home / "projects", "openBenches")
        env = {"PROJECTS_DIR": str(projects)}
        self.assertEqual(self.discover(env), str(old))
        new = self.checkout(projects, "openBenches")
        self.assertEqual(self.discover(env), str(new))


if __name__ == "__main__":
    unittest.main()
