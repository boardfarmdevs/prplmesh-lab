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
CLIENT_TEMPLATE = "prpl-client-thin-template"
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
    "usr/local/bin/wpa_cli",
)
REQUIRED_CLIENT = ("usr/local/sbin/wpa_supplicant", "usr/local/bin/wpa_cli")


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
    require(pool["driver"] in ("dir", "btrfs"), "thin capacity guard requires nested dir or btrfs storage")
    if pool["driver"] == "dir":
        source = Path(pool["config"].get("source", ""))
    else:
        require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", roots[0]["pool"]), "invalid pool name")
        source = Path("/var/snap/lxd/common/lxd/storage-pools") / roots[0]["pool"]
        backing = source.parents[1] / "disks" / (source.name + ".img")
        require(Path(pool["config"].get("source", "")) == backing and backing.is_file(),
                "thin Btrfs guard requires an LXD-managed loop-backed pool")
        filesystem = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", str(source)], text=True).strip()
        if filesystem != "btrfs":
            require(os.environ.get("PRPLMESH_THIN_MOUNT_NAMESPACE") != "1", "Btrfs pool is not mounted in LXD namespace")
            pid = query("/1.0")["environment"]["server_pid"]
            require(type(pid) is int and pid > 1, "missing LXD daemon PID")
            command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            require(Path(os.fsdecode(command[0])).name == "lxd" and b"--logfile" in command,
                    "refusing non-daemon mount namespace")
            os.environ["PRPLMESH_THIN_MOUNT_NAMESPACE"] = "1"
            os.execvp("nsenter", ["nsenter", f"--mount=/proc/{pid}/ns/mnt", "--", sys.executable, *sys.argv])
    require(source.is_absolute() and source.is_dir(), "missing absolute pool source")
    require(source == source.resolve(), "refusing symlinked pool source")
    return source


def stopped_root(name):
    require(re.fullmatch(r"prpl-(controller|thin-template|client-thin-template|agent-0[1-4]|client-(0[1-9]|[1-9][0-9]|100))", name),
            "unexpected nested instance name")
    instance = query("/1.0/instances/" + name)
    require(instance.get("type") == "container" and instance.get("status", "").upper() == "STOPPED",
            f"{name} must be a stopped container")
    pool = pool_path(instance["expanded_devices"])
    root = pool / "containers" / name / "rootfs"
    validate_root(root)
    if root.stat().st_dev != pool.stat().st_dev:
        require(filesystem_type(pool) == "btrfs", "rootfs must be on the pool filesystem")
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


def validate_measurement(measured):
    require(isinstance(measured, dict) and set(measured) == {"expanded_bytes", "entries"},
            "invalid measured footprint")
    for key in ("expanded_bytes", "entries"):
        require(type(measured[key]) is int and measured[key] > 0, f"invalid measured {key}")


def publication_budget(sanitized, published):
    validate_measurement(sanitized)
    validate_measurement(published)
    require(sanitized["entries"] == published["entries"], "template entry count changed after sanitation")
    return {"expanded_bytes": max(sanitized["expanded_bytes"], published["expanded_bytes"]),
            "entries": sanitized["entries"]}


def require_empty_clean_roots(root):
    for relative in CLEAN:
        directory = root / relative
        require(not directory.exists() or next(directory.iterdir(), None) is None,
                f"cleanup path is no longer empty: {relative}")


def protected_snapshot(root, required=REQUIRED_NATIVE):
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
    for relative in required:
        require("sha256" in records.get(relative, {}), f"missing native regular file: {relative}")
    if required == REQUIRED_CLIENT:
        require(not (root / "opt/prpl-install-nl80211").exists(), "client image contains the full mesh installation")
        require(not (root / "usr/local/sbin/hostapd").exists(), "client image contains the AP daemon")
    return records


def sanitize(root, output, reference=None, required=REQUIRED_NATIVE):
    validate_root(root)
    require(root not in output.resolve().parents, "sanitation evidence must be outside the template")
    output.mkdir(parents=True, exist_ok=False)
    before = protected_snapshot(root) if required == REQUIRED_NATIVE else protected_snapshot(root, required)
    write_json(output / "protected-before.json", before)
    if reference is not None:
        original = protected_snapshot(reference) if required == REQUIRED_NATIVE else protected_snapshot(reference, required)
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
    after = protected_snapshot(root) if required == REQUIRED_NATIVE else protected_snapshot(root, required)
    write_json(output / "protected-after.json", after)
    require(before == after, "protected files/native hashes or metadata changed during sanitation")
    result = {"schema_version": 1, "status": "PASS", "cleaned_paths": list(CLEAN),
              "before": original_size, "after": footprint(root),
              "protected_before_sha256": digest(output / "protected-before.json"),
              "protected_after_sha256": digest(output / "protected-after.json")}
    write_json(output / "sanitation.json", result)
    return result


def filesystem_type(path):
    return subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", str(path)], text=True).strip()


def available(path):
    usage = os.statvfs(path)
    free = {"bytes": usage.f_bavail * usage.f_frsize, "inodes": usage.f_favail}
    if usage.f_files == 0 and filesystem_type(path) == "btrfs":
        free["inodes"] = sys.maxsize
    if filesystem_type(path) == "btrfs":
        backing = path.parents[1] / "disks" / (path.name + ".img")
        if backing.is_file():
            host = os.statvfs(backing.parent)
            free["bytes"] = min(free["bytes"], host.f_bavail * host.f_frsize)
    return free


def capacity(measured, free, remaining=INSTANCES):
    require(type(remaining) is int and 0 <= remaining <= INSTANCES, "invalid remaining roster")
    validate_measurement(measured)
    per_instance = (measured["expanded_bytes"] * 105 + 99) // 100 + PER_INSTANCE_GROWTH
    required = remaining * per_instance + HEADROOM
    required_inodes = (remaining * measured["entries"] * 105 + 99) // 100 + 8192
    return {"status": "PASS" if free["bytes"] >= required and free["inodes"] >= required_inodes else "FAIL",
            "expected_instances": INSTANCES, "remaining_instances": remaining,
            "expanded_bytes_per_instance": measured["expanded_bytes"],
            "budget_bytes_per_instance": per_instance, "headroom_bytes": HEADROOM,
            "required_bytes": required, "available_bytes": free["bytes"],
            "required_inodes": required_inodes, "available_inodes": free["inodes"]}


def publication_measurement(manifest, legacy=False):
    sanitation = manifest["sanitation"]
    require(sanitation["status"] == "PASS" and sanitation["schema_version"] == 1,
            "invalid sanitation record")
    checksum = sanitation["protected_after_sha256"]
    require(sanitation["cleaned_paths"] == list(CLEAN)
            and sanitation["protected_before_sha256"] == checksum
            and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum),
            "invalid sanitation preservation binding")
    sanitized = sanitation["after"]
    validate_measurement(sanitized)
    measured = manifest["measured"]
    validate_measurement(measured)
    if legacy:
        require("publication" not in manifest and measured == sanitized,
                "invalid sanitized-image measurement")
    else:
        publication = manifest["publication"]
        require(publication["protected_sha256"] == checksum
                and publication["cleaned_paths_empty"] == list(CLEAN),
                "invalid published-image preservation binding")
        require(measured == publication_budget(sanitized, publication["measured"]),
                "invalid conservative published-image measurement")
    return measured


def manifest_measurement(manifest):
    version = manifest["schema_version"]
    require(type(version) is int and version in (1, 2), "unsupported capacity manifest schema")
    measured = publication_measurement(manifest, legacy=version == 1)
    if version == 2:
        preparation = manifest["preparation_capacity"]
        expected = capacity(measured, {"bytes": preparation["available_bytes"],
                                      "inodes": preparation["available_inodes"]})
        require(expected["status"] == "PASS"
                and all(preparation.get(key) == value for key, value in expected.items())
                and preparation["image_fingerprint"] == manifest["image_fingerprint"],
                "inconsistent publication capacity record")
    return measured


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


def role_capacity(images, free, mesh=5, clients=100):
    require(type(mesh) is int and 0 <= mesh <= 5 and type(clients) is int and 0 <= clients <= 100,
            "invalid remaining role counts")
    roles = {role: capacity(images[role]["measured"], free, count)
             for role, count in (("mesh", mesh), ("client", clients))}
    required_bytes = sum(row["required_bytes"] - HEADROOM for row in roles.values()) + HEADROOM
    required_inodes = sum(row["required_inodes"] - 8192 for row in roles.values()) + 8192
    return {"status": "PASS" if free["bytes"] >= required_bytes and free["inodes"] >= required_inodes else "FAIL",
            "expected_instances": INSTANCES, "remaining_instances": mesh + clients,
            "remaining_mesh": mesh, "remaining_clients": clients, "headroom_bytes": HEADROOM,
            "required_bytes": required_bytes, "available_bytes": free["bytes"],
            "required_inodes": required_inodes, "available_inodes": free["inodes"],
            "images": {role: {"image_fingerprint": images[role]["image_fingerprint"],
                              "budget_bytes_per_instance": row["budget_bytes_per_instance"]}
                       for role, row in roles.items()}}


def publication_record(root, sanitation_path, alias, required):
    sanitation = json.loads(sanitation_path.read_text())
    require(sanitation["status"] == "PASS" and sanitation["schema_version"] == 1,
            "missing successful sanitation")
    checksum = sanitation["protected_after_sha256"]
    require(sanitation["protected_before_sha256"] == checksum and sanitation["cleaned_paths"] == list(CLEAN),
            "invalid sanitation preservation binding")
    for name in ("protected-before.json", "protected-after.json"):
        require(digest(sanitation_path.parent / name) == checksum, "sanitation snapshot digest mismatch")
    require(protected_snapshot(root, required) == json.loads((sanitation_path.parent / "protected-after.json").read_text()),
            "template changed after sanitation")
    require_empty_clean_roots(root)
    published = footprint(root)
    return {"image_fingerprint": image_fingerprint(alias), "sanitation": sanitation,
            "measured": publication_budget(sanitation["after"], published),
            "publication": {"measured": published, "protected_sha256": checksum,
                            "cleaned_paths_empty": list(CLEAN)}}


def validate_role_manifest(manifest):
    require(manifest["schema_version"] == 3 and manifest["expected_instances"] == INSTANCES,
            "invalid two-image manifest")
    images = manifest["images"]
    require(set(images) == {"mesh", "client"}, "missing mesh/client image records")
    require(images["mesh"]["image_fingerprint"] != images["client"]["image_fingerprint"],
            "mesh/client images must differ")
    for record in images.values():
        require(re.fullmatch(r"[0-9a-f]{64}", record["image_fingerprint"]), "invalid image fingerprint")
        publication_measurement(record)
    preparation = manifest["preparation_capacity"]
    expected = role_capacity(images, {"bytes": preparation["available_bytes"], "inodes": preparation["available_inodes"]})
    require(expected["status"] == "PASS" and all(preparation.get(key) == value for key, value in expected.items()),
            "inconsistent two-image capacity record")
    return images


def reclaim_space(names, pool):
    require(len(set(names)) == len(names), "invalid reclaim roster")
    roots = []
    for name in names:
        root, owner = stopped_root(name)
        require(owner == pool, "reclaimed roster must share template pool")
        roots.append(str(root.parent))
    if filesystem_type(pool) == "btrfs":
        return 0
    return sum(int(line.split()[0]) for line in subprocess.check_output(
        ["du", "-s", "-x", "-B1", "--", *roots], text=True).splitlines())


def firstboot_roles(args, manifest):
    images = validate_role_manifest(manifest)
    for role, alias in (("mesh", args.image), ("client", args.client_image)):
        require(images[role]["image_fingerprint"] == image_fingerprint(alias), "capacity/image fingerprint mismatch")
    devices = query("/1.0/profiles/default")["devices"]
    pool = pool_path(devices)
    instances = query("/1.0/instances?recursion=1")
    require(len(instances) == args.existing, "existing roster count changed")
    counts = {"mesh": 0, "client": 0}
    names = set()
    for instance in instances:
        name = instance["name"]
        require(instance["type"] == "container" and name not in names, "invalid existing roster")
        if re.fullmatch(r"prpl-(controller|agent-0[1-4])", name):
            role = "mesh"
        else:
            require(re.fullmatch(r"prpl-client-(0[1-9]|[1-9][0-9]|100)", name), "unexpected nested instance name")
            role = "client"
        require(instance["config"].get("volatile.base_image") == images[role]["image_fingerprint"],
                "existing instance has the wrong role image")
        require(pool_path(instance["expanded_devices"]) == pool, "existing instance uses a different pool")
        names.add(name)
        counts[role] += 1
    checked_capacity(role_capacity(images, available(pool), 5 - counts["mesh"], 100 - counts["client"]))


def main():
    parser = argparse.ArgumentParser(description="Stopped-template sanitation and 105-instance guest capacity guards")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("trim-pool")
    copy = subparsers.add_parser("copy-check")
    copy.add_argument("--client", action="store_true")
    clean = subparsers.add_parser("sanitize")
    clean.add_argument("--output", type=Path, required=True)
    clean.add_argument("--compare-controller", action="store_true")
    clean.add_argument("--client", action="store_true")
    prepare = subparsers.add_parser("prepare-check")
    prepare.add_argument("--sanitation", type=Path, required=True)
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--state", type=Path, required=True)
    prepare.add_argument("--reclaim", nargs="+", required=True)
    prepare.add_argument("--client-image")
    prepare.add_argument("--client-sanitation", type=Path)
    firstboot = subparsers.add_parser("firstboot-check")
    firstboot.add_argument("--image", required=True)
    firstboot.add_argument("--state", type=Path, required=True)
    firstboot.add_argument("--existing", type=int, required=True)
    firstboot.add_argument("--expected", type=int, required=True)
    firstboot.add_argument("--client-image", default="prpl-client-local")
    args = parser.parse_args()
    if args.action == "trim-pool":
        pool = pool_path(query("/1.0/profiles/default")["devices"])
        if filesystem_type(pool) == "btrfs":
            subprocess.run(["btrfs", "filesystem", "sync", str(pool)], check=True)
            subprocess.run(["fstrim", "--", str(pool)], check=True)
    elif args.action == "copy-check":
        root, pool = stopped_root("prpl-client-01" if args.client else "prpl-controller")
        measured = footprint(root)
        required = 2 * measured["expanded_bytes"] + 2 * GIB
        free = available(pool)
        require(free["bytes"] >= required and free["inodes"] >= 2 * measured["entries"] + 8192,
                "insufficient guest workspace for template copy/publication")
    elif args.action == "sanitize":
        root, unused_pool = stopped_root(CLIENT_TEMPLATE if args.client else TEMPLATE)
        reference = stopped_root("prpl-client-01" if args.client else "prpl-controller")[0] if args.compare_controller else None
        print(json.dumps(sanitize(root, args.output, reference, REQUIRED_CLIENT if args.client else REQUIRED_NATIVE), sort_keys=True))
    elif args.action == "prepare-check":
        root, pool = stopped_root(TEMPLATE)
        if args.client_image or args.client_sanitation:
            require(args.client_image and args.client_sanitation, "both client image and sanitation are required")
            client_root, client_pool = stopped_root(CLIENT_TEMPLATE)
            require(client_pool == pool, "mesh/client templates must share storage")
            images = {"mesh": publication_record(root, args.sanitation, args.image, REQUIRED_NATIVE),
                      "client": publication_record(client_root, args.client_sanitation, args.client_image, REQUIRED_CLIENT)}
            for relative in REQUIRED_CLIENT:
                require(digest(root / relative) == digest(client_root / relative),
                        "mesh/client supplicant binaries differ")
            require(TEMPLATE in args.reclaim and CLIENT_TEMPLATE in args.reclaim, "missing reclaim templates")
            reclaimed = reclaim_space(args.reclaim, pool)
            free = available(pool)
            free["bytes"] += reclaimed
            result = role_capacity(images, free)
            result.update(reclaim_bytes=reclaimed, reclaim_instances=args.reclaim)
            checked_capacity(result)
            manifest = {"schema_version": 3, "expected_instances": INSTANCES,
                        "images": images, "preparation_capacity": result}
            validate_role_manifest(manifest)
            write_json(args.state, manifest)
            return
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
        require_empty_clean_roots(root)
        published = footprint(root)
        measured = publication_budget(sanitation["after"], published)
        require(TEMPLATE in args.reclaim and len(set(args.reclaim)) == len(args.reclaim), "invalid reclaim roster")
        reclaim_bytes = reclaim_space(args.reclaim, pool)
        free = available(pool)
        free["bytes"] += reclaim_bytes
        result = capacity(measured, free)
        result["reclaim_bytes"] = reclaim_bytes
        result["reclaim_instances"] = args.reclaim
        result["image_fingerprint"] = image_fingerprint(args.image)
        checked_capacity(result)
        write_json(args.state, {"schema_version": 2, "image_fingerprint": result["image_fingerprint"],
                                "expected_instances": INSTANCES, "measured": measured,
                                "publication": {"measured": published,
                                                "protected_sha256": sanitation["protected_after_sha256"],
                                                "cleaned_paths_empty": list(CLEAN)},
                                "sanitation": sanitation, "preparation_capacity": result})
    else:
        manifest = json.loads(args.state.read_text())
        require(manifest["expected_instances"] == args.expected == INSTANCES,
                "missing fixed 105-instance capacity manifest")
        if manifest["schema_version"] == 3:
            firstboot_roles(args, manifest)
            return
        require(manifest["image_fingerprint"] == image_fingerprint(args.image), "capacity/image fingerprint mismatch")
        measured = manifest_measurement(manifest)
        pool = pool_path(query("/1.0/profiles/default")["devices"])
        result = capacity(measured, available(pool), INSTANCES - args.existing)
        result["image_fingerprint"] = manifest["image_fingerprint"]
        checked_capacity(result)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"thin image guard: {error}")
