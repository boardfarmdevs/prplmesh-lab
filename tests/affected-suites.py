#!/usr/bin/env python3
"""What a change needs: the lab VM's step and the suite sections that can see it.

    tests/affected-suites.py BASE [HEAD] [--json]

BASE and HEAD are commits of this lab (HEAD defaults to HEAD). A changed submodule (medium,
optimizer) is followed into its own history when both of its commits are present, and
counts as wholly changed when not.

The lab VM's step is the least that brings an accepted lab to HEAD: nothing (documents
only), `build.sh update` (the checkout and its submodules in place, and what a build
installs from them: the medium's daemon, console and radio module, the guest's services,
the controller UI, the scripts the containers run, with a VM restart), `build.sh build`
(the VM's other steps, the container images' setup), or the native archives first
(deploy/lxd-vm/build-artifacts.sh: what they are built from). The sections are those of
tests/run-prplmesh-suite.py that the changed paths can affect; the static section runs for
any change that is not only documents, and an unknown path runs every section. The soak is
never chosen for one change: it belongs to release points (tests/README.md).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ["static", "webui", "browser", "rf", "rf-actions", "rooms", "live"]
STEPS = ["none", "update", "build", "artifacts"]
SUBMODULES = ("medium", "optimizer")
ALL = tuple(SECTIONS)

# (pattern, step, sections): the first pattern that matches a path decides it. Patterns
# match the path from the repository's root (fnmatch: * also crosses "/").
RULES: list[tuple[str, str, tuple[str, ...]]] = [
    # documents, the site and CI: nothing to run in the lab
    ("docs/*", "none", ()),
    ("pages/*", "none", ()),
    ("explorer/*", "none", ()),
    (".github/*", "none", ()),
    ("*.md", "none", ()),
    ("medium/docs/*", "none", ()),
    ("optimizer/docs/*", "none", ()),
    # what the native archives are built from: new archives, then everything
    ("patches/*", "artifacts", ALL),
    ("manifests/lab.env", "artifacts", ALL),
    ("scripts/build-prplmesh.sh", "artifacts", ALL),
    ("scripts/create-build-container.sh", "artifacts", ALL),
    ("scripts/package-build-artifacts.sh", "artifacts", ALL),
    ("scripts/build-client-artifact.sh", "artifacts", ALL),
    ("scripts/container/build-*inside.sh", "artifacts", ALL),
    ("scripts/container/package-artifacts-inside.sh", "artifacts", ALL),
    ("deploy/lxd-vm/build-artifacts.sh", "artifacts", ALL),
    ("deploy/lxd-vm/native-inputs.sh", "artifacts", ALL),
    ("tests/amxp-signal-burst.*", "artifacts", ALL),
    # the container images and the VM's own steps: a build
    ("scripts/container/setup-*-base.sh", "build", ("static", "live", "rooms", "rf")),
    ("scripts/build-runtime-image.sh", "build", ("static", "live", "rooms", "rf")),
    ("scripts/install-from-artifacts.sh", "build", ("static", "live", "rooms", "rf")),
    ("scripts/generate-wmediumd-config.py", "build", ("static", "live", "rf")),
    ("deploy/lxd-vm/*", "build", ("static", "live")),
    # the medium: an update makes its daemon, console and radio module and restarts the VM
    ("medium/hwsim/*", "update", ("static", "rf", "rf-actions", "rooms", "live")),
    ("medium/wmediumd/*", "update", ("static", "rf", "rf-actions", "rooms", "live")),
    ("medium/observer/*", "update", ("static", "browser", "rf", "live")),
    ("medium/topology-ui/*", "update", ("static", "webui", "browser", "rooms", "rf")),
    ("medium/configurator/worlds/viewer/*", "update", ("static", "webui", "browser", "rooms", "rf")),
    ("medium/configurator/*", "update", ("static", "rf", "rf-actions", "rooms")),
    ("medium/*", "update", ("static", "rf")),
    # the optimizer and the rooms
    ("optimizer/acceptance/*", "update", ("static", "rf-actions", "rooms")),
    ("optimizer/*", "update", ("static", "rf", "rf-actions", "rooms", "live")),
    ("rooms/*", "update", ("static", "rf", "rooms")),
    # the guest's services, the controller UI and what the containers run
    ("deploy/guest/*", "update", ("static", "rooms", "live")),
    ("controller-ui/*", "update", ("static", "webui", "browser")),
    ("topology-adapter/*", "update", ("static", "webui", "live")),
    ("scripts/container/*", "update", ("static", "rf", "rf-actions", "rooms", "live")),
    ("scripts/radio-lab.sh", "update", ("static", "rf", "rooms", "live")),
    ("scripts/lib/*", "update", ("static", "rf-actions", "rooms", "live")),
    ("scripts/*", "update", ("static", "live")),
    ("manifests/*", "update", ("static", "rooms", "live")),
    # the lab's tests, run from its checkout
    ("tests/*browser*", "update", ("static", "browser")),
    ("tests/*", "update", ("static",)),
]


def classify(path: str) -> tuple[str, tuple[str, ...]]:
    for pattern, step, sections in RULES:
        if fnmatch.fnmatch(path, pattern):
            return step, sections
    return "build", ALL                    # unknown: everything


def plan(paths: list[str]) -> dict:
    """The step and sections for a list of changed paths."""
    step = "none"
    sections: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for path in paths:
        path_step, path_sections = classify(path)
        if STEPS.index(path_step) > STEPS.index(step):
            step = path_step
        sections.update(path_sections)
        for section in path_sections:
            reasons.setdefault(section, []).append(path)
    if any(classify(p)[0] != "none" for p in paths):
        sections.add("static")
    ordered = [s for s in SECTIONS if s in sections]
    return {"step": step, "sections": ordered, "paths": len(paths),
            "because": {s: sorted(reasons.get(s, []))[:5] for s in ordered}}


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout


def changed_paths(base: str, head: str) -> list[str]:
    paths = []
    for line in git("diff", "--name-only", base, head).splitlines():
        if line in SUBMODULES:
            paths += submodule_paths(line, base, head)
        else:
            paths.append(line)
    return paths


def submodule_paths(submodule: str, base: str, head: str) -> list[str]:
    def pinned(commit: str) -> str | None:
        try:
            return git("rev-parse", f"{commit}:{submodule}").strip()
        except subprocess.CalledProcessError:
            return None
    old, new = pinned(base), pinned(head)
    repository = ROOT / submodule
    if old and new and (repository / ".git").exists():
        try:
            return [f"{submodule}/{p}" for p in
                    git("diff", "--name-only", old, new, cwd=repository).splitlines()]
        except subprocess.CalledProcessError:
            pass
    return [f"{submodule}/<unknown>"]      # not comparable here: wholly changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base")
    parser.add_argument("head", nargs="?", default="HEAD")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = plan(changed_paths(args.base, args.head))
    result["range"] = f"{args.base}..{args.head}"
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    step = {"none": "nothing (documents only)", "update": "deploy/lxd-vm/build.sh update",
            "build": "deploy/lxd-vm/build.sh build", "artifacts":
            "deploy/lxd-vm/build-artifacts.sh, then deploy/lxd-vm/build.sh build"}[result["step"]]
    print(f"{result['range']}: {result['paths']} changed path(s)")
    print(f"lab VM: {step}")
    if result["sections"]:
        acting = " --yes-act" if set(result["sections"]) & {"live", "rooms", "rf", "rf-actions"} else ""
        print(f"suite:  tests/run-prplmesh-suite.py {' '.join(result['sections'])}{acting}")
        for section, paths in result["because"].items():
            print(f"  {section:<10} {', '.join(paths)}")
    else:
        print("suite:  nothing")
    print("soak:   at release points only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
