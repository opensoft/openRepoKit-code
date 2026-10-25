#!/usr/bin/env python3
"""Dispatch existing commands to one immutable Kit release. SPDX-License-Identifier: Apache-2.0."""
import json
import os
from pathlib import Path
import sys


def projects_dirs(env):
    if env.get("PROJECTS_DIR"):
        return [Path(env["PROJECTS_DIR"]).expanduser().resolve()]
    return [Path.home() / "projects", Path.home() / "Projects"]


def discover_workbenches(release, env):
    if (release / ".workbenches-path").is_file():
        return None
    directories = projects_dirs(env)
    for basename in ("openBenches", "workBenches"):
        for directory in directories:
            candidate = directory / basename
            if (candidate / "config/bench-config.json").is_file():
                return candidate.resolve()
    return None


release = Path(__file__).resolve().parent
data = json.loads((release / "manifest.json").read_text())
name = Path(sys.argv[0]).name
rows = {row["name"]: row for row in data["components"]}
env = dict(os.environ)
env.update(OPENREPOSHAPE_REPO=rows["openRepoShape"]["repository"],
           OPENREPOSHAPE_REF=rows["openRepoShape"]["commit"],
           OPENREPOSHAPE_SETUP_SH=str(release / "components/openRepoShape/setup.sh"),
           OPENREPOTOOLS_REPO=rows["openRepoTools"]["repository"],
           OPENREPOTOOLS_REF=rows["openRepoTools"]["commit"])
# Put this release first, even when a newer Kit or either bench checkout is on PATH.
env["PATH"] = str(release / "bin") + os.pathsep + env.get("PATH", "")
if "WORKBENCHES_ROOT" not in env:
    if data.get("workbenches"):
        env["WORKBENCHES_ROOT"] = data["workbenches"]
    else:
        discovered = discover_workbenches(release, env)
        if discovered is not None:
            env["WORKBENCHES_ROOT"] = str(discovered)
args = sys.argv[1:]
if name == "openRepoKit":
    if args in (["--version"], ["status"]):
        print(f"openRepoKit code={data['code_commit']} spec={data['spec_commit']}")
        for row in data["components"]:
            print(f"{row['name']}: {row['commit']}")
        sys.exit(0)
    print("openRepoKit status | --version\nInstall or update from the assembly checkout: python3 code/openRepoKit install")
    sys.exit(0 if args in ([], ["--help"]) else 2)
if name in ("openRepoShape", "openRepoTools") and "--install" in args:
    print("REFUSED: Kit owns this installation; run python3 code/openRepoKit install from the assembly checkout.", file=sys.stderr)
    sys.exit(2)
if name == "openRepoShape" and any(arg == "--shape-ref" or arg.startswith("--shape-ref=") for arg in args):
    print("REFUSED: Kit owns the Shape revision; update the component contract instead.", file=sys.stderr)
    sys.exit(2)
if name == "project":
    command = [sys.executable, str(release / "components/openRepoProject/project")]
elif name == "openRepoShape":
    command = ["bash", str(release / "components/openRepoShape/openRepoShape")]
else:
    command = [str(release / "components/openRepoTools" / name)]
os.execvpe(command[0], command + args, env)
