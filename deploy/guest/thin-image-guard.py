#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys


TEMPLATE = "prpl-thin-template"
INSTANCES = 105
GIB = 1024 ** 3
HEADROOM = 8 * GIB
PER_INSTANCE_GROWTH = 64 * 1024 ** 2
CLEAN = ("var/log", "tmp", "var/tmp", "var/crash")
REQUIRED_NATIVE = (
    "opt/prpl-install-nl80211/bin/beerocks_controller",
    "opt/prpl-install-nl80211/bin/beerocks_agent",
    "usr/local/sbin/hostapd",
    "usr/local/sbin/wpa_supplicant",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def query(endpoint):
    return json.loads(subprocess.check_output(
        [os.environ.get("PRPLMESH_LXC_BIN", "lxc"), "query", endpoint], text=True))


def pool_path(devices):
    roots = [device for device in devices.values()
             if device.get("type") == "disk" and device.get("path") == "/"]
    require(len(roots) == 1 and roots[0].get("pool"), "missing unique root storage pool")
    require(not roots[0].get("size"), "nested root quotas require a separate capacity assessment")
    pool = query("/1.0/storage-pools/" + roots[0]["pool"])
    require(pool["driver"] == "dir", "thin capacity guard requires nested dir storage")
    source = Path(pool["config"].get("source", ""))
    require(source.is_absolute() and source.is_dir(), "missing absolute dir pool source")
    require(source == source.resolve(), "refusing symlinked pool source")
    return source


def stopped_root(name):
    require(re.fullmatch(r"prpl-(controller|thin-template|agent-0[1-4]|client-(0[1-9]|[1-9][0-9]|100))", name),
            "unexpected nested instance name")
    instance = query("/1.0/instances/" + name)
    require(instance.get("type") == "container" and instance.get("status", "").upper() == "STOPPED",
            f"{name} must be a stopped container")
    pool = pool_path(instance["expanded_devices"])
    root = pool / "containers" / name / "rootfs"
    validate_root(root)
    require(root.stat().st_dev == pool.stat().st_dev, "rootfs must be on the dir pool filesystem")
    return root, pool


def validate_root(root):
    require(root.is_absolute() and root.is_dir() and root == root.resolve(),
            "refusing missing/symlinked rootfs")
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        mount = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), line.split()[4]))
        require(mount != root and root not in mount.parents, f"refusing mounted rootfs content: {mount}")
    for relative in CLEAN:
        current = root
        for component in Path(relative).parts:
            current = current / component
            require(not current.is_symlink(), f"refusing symlinked cleanup path: {current}")
        require(not current.exists() or current.is_dir(), f"cleanup path is not a directory: {current}")


def entries(root):
    yield root
    device = root.stat().st_dev
    for directory, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(directories + files):
            path = Path(directory) / name
            require(path.lstat().st_dev == device, f"refusing filesystem crossing: {path}")
            yield path


def footprint(root):
    total = 0
    count = 0
    for path in entries(root):
        info = path.lstat()
        total += max(info.st_blocks * 512, ((info.st_size + 4095) // 4096) * 4096, 4096)
        count += 1
    return {"expanded_bytes": total, "entries": count}


def protected_snapshot(root):
    records = {}
    for path in entries(root):
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(clean + "/") for clean in CLEAN):
            continue
        info = path.lstat()
        record = {"mode": info.st_mode, "uid": info.st_uid, "gid": info.st_gid,
                  "xattrs": {name: os.getxattr(path, name, follow_symlinks=False).hex()
                             for name in os.listxattr(path, follow_symlinks=False)}}
        if stat.S_ISREG(info.st_mode):
            record["sha256"] = digest(path)
        elif stat.S_ISLNK(info.st_mode):
            record["target"] = os.readlink(path)
        elif stat.S_ISCHR(info.st_mode) or stat.S_ISBLK(info.st_mode):
            record["rdev"] = info.st_rdev
        records[relative] = record
    for relative in REQUIRED_NATIVE:
        require("sha256" in records.get(relative, {}), f"missing native regular file: {relative}")
    return records


def sanitize(root, output, reference=None):
    validate_root(root)
    require(root not in output.resolve().parents, "sanitation evidence must be outside the template")
    output.mkdir(parents=True, exist_ok=False)
    before = protected_snapshot(root)
    write_json(output / "protected-before.json", before)
    if reference is not None:
        original = protected_snapshot(reference)
        native = lambda records: {name: value for name, value in records.items()
                                  if name.startswith(("opt/", "usr/"))}
        require(native(original) == native(before), "source/copy native or installed asset mismatch")
    original_size = footprint(root)
    for relative in CLEAN:
        directory = root / relative
        if not directory.exists():
            continue
        for child in directory.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    after = protected_snapshot(root)
    write_json(output / "protected-after.json", after)
    require(before == after, "protected files/native hashes or metadata changed during sanitation")
    result = {"schema_version": 1, "status": "PASS", "cleaned_paths": list(CLEAN),
              "before": original_size, "after": footprint(root),
              "protected_before_sha256": digest(output / "protected-before.json"),
              "protected_after_sha256": digest(output / "protected-after.json")}
    write_json(output / "sanitation.json", result)
    return result


def available(path):
    usage = os.statvfs(path)
    return {"bytes": usage.f_bavail * usage.f_frsize, "inodes": usage.f_favail}


def capacity(measured, free, remaining=INSTANCES):
    require(type(remaining) is int and 0 <= remaining <= INSTANCES, "invalid remaining roster")
    for key in ("expanded_bytes", "entries"):
        require(type(measured.get(key)) is int and measured[key] > 0, f"invalid measured {key}")
    per_instance = (measured["expanded_bytes"] * 105 + 99) // 100 + PER_INSTANCE_GROWTH
    required = remaining * per_instance + HEADROOM
    required_inodes = (remaining * measured["entries"] * 105 + 99) // 100 + 8192
    return {"status": "PASS" if free["bytes"] >= required and free["inodes"] >= required_inodes else "FAIL",
            "expected_instances": INSTANCES, "remaining_instances": remaining,
            "expanded_bytes_per_instance": measured["expanded_bytes"],
            "budget_bytes_per_instance": per_instance, "headroom_bytes": HEADROOM,
            "required_bytes": required, "available_bytes": free["bytes"],
            "required_inodes": required_inodes, "available_inodes": free["inodes"]}


def checked_capacity(result):
    print(json.dumps(result, sort_keys=True), flush=True)
    require(result["status"] == "PASS",
            "insufficient guest capacity for 105 instances plus headroom; no provisioning permitted")


def image_fingerprint(alias):
    require(re.fullmatch(r"[a-zA-Z0-9_.-]+", alias), "invalid runtime image alias")
    fingerprint = query("/1.0/images/aliases/" + alias)["target"]
    require(re.fullmatch(r"[0-9a-f]{64}", fingerprint), "invalid image fingerprint")
    require(query("/1.0/images/" + fingerprint)["type"] == "container", "runtime image is not a container")
    return fingerprint


def main():
    parser = argparse.ArgumentParser(description="Stopped-template sanitation and 105-instance guest capacity guards")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("copy-check")
    clean = subparsers.add_parser("sanitize")
    clean.add_argument("--output", type=Path, required=True)
    clean.add_argument("--compare-controller", action="store_true")
    prepare = subparsers.add_parser("prepare-check")
    prepare.add_argument("--sanitation", type=Path, required=True)
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--state", type=Path, required=True)
    prepare.add_argument("--reclaim", nargs="+", required=True)
    firstboot = subparsers.add_parser("firstboot-check")
    firstboot.add_argument("--image", required=True)
    firstboot.add_argument("--state", type=Path, required=True)
    firstboot.add_argument("--existing", type=int, required=True)
    firstboot.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    if args.action == "copy-check":
        root, pool = stopped_root("prpl-controller")
        measured = footprint(root)
        required = 2 * measured["expanded_bytes"] + 2 * GIB
        free = available(pool)
        require(free["bytes"] >= required and free["inodes"] >= 2 * measured["entries"] + 8192,
                "insufficient guest workspace for template copy/publication")
    elif args.action == "sanitize":
        root, unused_pool = stopped_root(TEMPLATE)
        reference = stopped_root("prpl-controller")[0] if args.compare_controller else None
        print(json.dumps(sanitize(root, args.output, reference), sort_keys=True))
    elif args.action == "prepare-check":
        root, pool = stopped_root(TEMPLATE)
        sanitation = json.loads(args.sanitation.read_text())
        require(sanitation["status"] == "PASS" and sanitation["schema_version"] == 1,
                "missing successful sanitation")
        require(sanitation["protected_before_sha256"] == sanitation["protected_after_sha256"],
                "sanitation preservation proof mismatch")
        require(sanitation["cleaned_paths"] == list(CLEAN), "unexpected sanitation scope")
        require(digest(args.sanitation.parent / "protected-before.json") == sanitation["protected_before_sha256"],
                "sanitation source snapshot digest mismatch")
        require(digest(args.sanitation.parent / "protected-after.json") == sanitation["protected_after_sha256"],
                "sanitation snapshot digest mismatch")
        require(protected_snapshot(root) == json.loads((args.sanitation.parent / "protected-after.json").read_text()),
                "template changed after sanitation")
        measured = footprint(root)
        require(measured == sanitation["after"], "template footprint changed after sanitation")
        require(TEMPLATE in args.reclaim and len(set(args.reclaim)) == len(args.reclaim), "invalid reclaim roster")
        roots = []
        for name in args.reclaim:
            reclaim_root, reclaim_pool = stopped_root(name)
            require(reclaim_pool == pool, "reclaimed roster must share template pool")
            roots.append(str(reclaim_root.parent))
        reclaim_bytes = sum(int(line.split()[0]) for line in subprocess.check_output(
            ["du", "-s", "-x", "-B1", "--", *roots], text=True).splitlines())
        free = available(pool)
        free["bytes"] += reclaim_bytes
        result = capacity(measured, free)
        result["reclaim_bytes"] = reclaim_bytes
        result["reclaim_instances"] = args.reclaim
        result["image_fingerprint"] = image_fingerprint(args.image)
        checked_capacity(result)
        write_json(args.state, {"schema_version": 1, "image_fingerprint": result["image_fingerprint"],
                                "expected_instances": INSTANCES, "measured": measured,
                                "sanitation": sanitation, "preparation_capacity": result})
    else:
        manifest = json.loads(args.state.read_text())
        require(manifest["schema_version"] == 1 and manifest["expected_instances"] == args.expected == INSTANCES,
                "missing fixed 105-instance capacity manifest")
        require(manifest["image_fingerprint"] == image_fingerprint(args.image), "capacity/image fingerprint mismatch")
        require(manifest["sanitation"]["status"] == "PASS" and manifest["measured"] == manifest["sanitation"]["after"],
                "invalid sanitized-image measurement")
        require(manifest["sanitation"]["cleaned_paths"] == list(CLEAN)
                and manifest["sanitation"]["protected_before_sha256"] == manifest["sanitation"]["protected_after_sha256"]
                and re.fullmatch(r"[0-9a-f]{64}", manifest["sanitation"]["protected_after_sha256"]),
                "invalid sanitation preservation binding")
        pool = pool_path(query("/1.0/profiles/default")["devices"])
        result = capacity(manifest["measured"], available(pool), INSTANCES - args.existing)
        result["image_fingerprint"] = manifest["image_fingerprint"]
        checked_capacity(result)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"thin image guard: {error}")
