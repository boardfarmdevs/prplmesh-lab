from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from wmdcfg.actuator import ActuatorError, ControlClient
from wmdcfg.compiler import compile_scenario
from wmdcfg.inventory import discover
from wmdcfg.model import ScenarioError
from wmdcfg.parser import parse
from wmdcfg.runner import Runner
from wmdcfg.world import export_wmd, load_json, verify_world_plan

from .conductor import LiveConductor, load_manifest
from .events import EventStore
from .server import RoomDemoServer


DEMO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DEMO_ROOT.parent
CONFIGURATOR = REPO_ROOT / "wmediumd/configurator"
DEFAULT_MANIFEST = DEMO_ROOT / "manifests/private-client-room-walk.json"
DEFAULT_VIEWER = CONFIGURATOR / "worlds/viewer"


def _address(value: str) -> tuple[str, int]:
    try:
        host, raw_port = value.rsplit(":", 1)
        port = int(raw_port)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError("use HOST:PORT") from error
    if not host or not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("use HOST:PORT")
    return host, port


def _prepare(world_path: Path, binding_path: Path):
    world = load_json(world_path)
    verify_world_plan(world)
    source = export_wmd(world, "all")
    scenario = parse(source)
    inventory = discover()
    binding_doc = json.loads(binding_path.read_text(encoding="utf-8"))
    bindings = binding_doc.get("roles")
    if not isinstance(bindings, dict):
        raise ScenarioError(f"{binding_path}: roles must be an object")
    plan = compile_scenario(scenario, source, inventory, bindings)
    return world, source, inventory, binding_doc, plan


def _status(socket_path: str) -> dict:
    with ControlClient(socket_path) as client:
        status = client.status()
    return {
        "instance_id": status.instance_id,
        "generation": status.generation,
        "num_stations": status.num_stations,
        "capabilities": sorted(status.capabilities),
    }


def _paths(args) -> tuple[dict, Path, Path]:
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path, REPO_ROOT)
    world = args.world.resolve() if args.world else REPO_ROOT / manifest["world"]
    bindings = args.bindings.resolve() if args.bindings else REPO_ROOT / manifest["bindings"]
    return manifest, world, bindings


def _file_index(run_dir: Path) -> dict:
    files = {}
    for path in sorted(run_dir.iterdir()):
        if not path.is_file() or path.name == "evidence-index.json":
            continue
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {"schema": "easymesh.room-demo.evidence.v1", "files": files}


def _copy_inputs(runner, source, inventory, binding_doc, world_path, manifest) -> None:
    runner.run_dir.mkdir(parents=True, exist_ok=True)
    (runner.run_dir / "world.wmd").write_text(source, encoding="utf-8")
    (runner.run_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (runner.run_dir / "bindings.json").write_text(
        json.dumps(binding_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (runner.run_dir / "demo-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copy2(world_path, runner.run_dir / "world.json")


def _check(args) -> int:
    manifest, world_path, bindings_path = _paths(args)
    status = _status(args.socket)
    world, _source, _inventory, _binding_doc, plan = _prepare(world_path, bindings_path)
    hero = manifest["hero"]["role"]
    print(json.dumps({
        "status": "ready",
        "manifest": manifest["name"],
        "world": world["name"],
        "duration_ms": world["duration_ms"],
        "roles": len(world["roles"]),
        "hero": {
            "role": hero,
            "container": plan["bindings"][hero]["container"],
            "radio_permanent_mac": plan["bindings"][hero]["radio_permanent_mac"],
            "station_mac": plan["bindings"][hero].get("station_mac"),
        },
        "wmediumd": status,
        "plan_generations": sum(bool(item["updates"]) for item in plan["events"]),
    }, indent=2, sort_keys=True))
    return 0


def _run(args) -> int:
    if args.mode == "act" and not args.yes_act:
        raise ActuatorError("act mode requires --yes-act")
    manifest, world_path, bindings_path = _paths(args)
    _status(args.socket)
    world, source, inventory, binding_doc, plan = _prepare(world_path, bindings_path)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{manifest['name']}"
    runner = Runner(plan, args.socket, args.output_root, run_id=run_id,
                    clock_interval_ms=args.clock_interval_ms)
    store = EventStore(run_id, world, runner.run_dir / "live-events.jsonl")
    runner.event_callback = store.ingest
    conductor = LiveConductor(store, plan, manifest, mode=args.mode,
                              repo_root=REPO_ROOT, base_url=args.base_url)
    server = RoomDemoServer(args.listen, store, DEFAULT_VIEWER)
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = args.lock.open("a+")
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_stream.close()
        raise ActuatorError(f"another room demo owns {args.lock}") from error
    lock_stream.seek(0)
    lock_stream.truncate()
    lock_stream.write(run_id + "\n")
    lock_stream.flush()

    server_started = False
    try:
        _copy_inputs(runner, source, inventory, binding_doc, world_path, manifest)
        server.start()
        server_started = True
        host, port = server.address
        display_host = "127.0.0.1" if host == "0.0.0.0" else host
        print(f"room-demo: immersive viewer http://{display_host}:{port}/viewer/?mode=live")
        print(f"room-demo: run {run_id}; mode={args.mode}; hero={conductor.hero_mac}; "
              "RF writer=wmdcfg Runner")
        failure: Exception | None = None
        conductor.preflight()
        conductor.start()
        try:
            runner.execute()
        except Exception as error:
            failure = error
            print(f"room-demo: run failed: {error}", file=sys.stderr)
        finally:
            conductor.stop()
        runner_summary = json.loads(
            (runner.run_dir / "summary.json").read_text(encoding="utf-8")
        )
        conductor_summary = conductor.summary()
        if conductor_summary["worker_errors"] and failure is None:
            failure = RuntimeError("one or more live workers failed")
        if args.mode == "act" and (
            conductor_summary["action_attempts"] != 1
            or conductor_summary["action_successes"] != 1
            or conductor_summary["verification_successes"] != 1
        ) and failure is None:
            failure = RuntimeError("act mode did not complete one verified steering action")
        outcome = "passed" if failure is None and runner_summary.get("outcome") == "passed" else "failed"
        restored = bool(runner_summary.get("restored"))
        demo_summary = {
            "schema": "easymesh.room-demo.summary.v1",
            "run_id": run_id,
            "outcome": outcome,
            "restored": restored,
            "error": str(failure) if failure else runner_summary.get("error"),
            "runner": runner_summary,
            "conductor": conductor_summary,
        }
        (runner.run_dir / "demo-summary.json").write_text(
            json.dumps(demo_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        store.emit("run.completed", world["duration_ms"], {
            "outcome": outcome,
            "restored": restored,
            "error": demo_summary["error"],
            "summary": conductor_summary,
        }, producer="conductor")
        (runner.run_dir / "evidence-index.json").write_text(
            json.dumps(_file_index(runner.run_dir), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"room-demo: outcome={outcome} restored={str(restored).lower()} "
              f"actions={conductor.action_attempts} verified={conductor.verification_successes}")
        print(f"room-demo: evidence {runner.run_dir}")
        if args.linger_seconds > 0:
            print(f"room-demo: completed view remains available for {args.linger_seconds}s")
            time.sleep(args.linger_seconds)
        return 0 if outcome == "passed" else 1
    except Exception as error:
        conductor.stop()
        runner.run_dir.mkdir(parents=True, exist_ok=True)
        restored = not (runner.run_dir / "event-plan.json").exists()
        failed_summary = {
            "schema": "easymesh.room-demo.summary.v1",
            "run_id": run_id,
            "outcome": "failed",
            "restored": restored,
            "error": str(error),
            "runner": None,
            "conductor": conductor.summary(),
        }
        (runner.run_dir / "demo-summary.json").write_text(
            json.dumps(failed_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        store.emit("run.completed", store.current()["world_time_ms"], {
            "outcome": "failed", "restored": restored, "error": str(error),
            "summary": conductor.summary(),
        }, producer="conductor")
        (runner.run_dir / "evidence-index.json").write_text(
            json.dumps(_file_index(runner.run_dir), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"room-demo: {error}", file=sys.stderr)
        return 2
    finally:
        if server_started:
            server.close()
        else:
            server.httpd.server_close()
        fcntl.flock(lock_stream, fcntl.LOCK_UN)
        lock_stream.close()


def _replay(args) -> int:
    store = EventStore.from_evidence(args.run_directory.resolve())
    server = RoomDemoServer(args.listen, store, DEFAULT_VIEWER)
    server.start()
    host, port = server.address
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"room-demo: replay http://{display_host}:{port}/viewer/?mode=replay")
    print(f"room-demo: evidence {args.run_directory.resolve()}")
    try:
        if args.serve_seconds > 0:
            time.sleep(args.serve_seconds)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="room-demo",
        description="Run and present the closed-loop prplMesh room demonstration.",
    )
    commands = result.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("check", "compile and validate the live radio bindings without changing RF"),
        ("run", "run, present, verify and restore one live room experiment"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                             help="demo contract JSON (default: private client room walk)")
        command.add_argument("--world", type=Path, help="override the manifest Golden World")
        command.add_argument("--bindings", type=Path, help="override manifest role bindings")
        command.add_argument("--socket", default="/run/prpl-wmediumd/control.sock",
                             help="wmediumd control socket")
    run = commands.choices["run"]
    run.add_argument("--mode", choices=("stimulus", "recommend", "act"), default="recommend",
                     help="presentation authority (default: recommend; no network action)")
    run.add_argument("--yes-act", action="store_true",
                     help="required second confirmation for the bounded act mode")
    run.add_argument("--base-url", default="http://127.0.0.1:8092")
    run.add_argument("--listen", type=_address, default=("127.0.0.1", 8891), metavar="HOST:PORT")
    run.add_argument("--output-root", type=Path, default=Path("/tmp/prplmesh-room-demo-runs"))
    run.add_argument("--linger-seconds", type=int, default=60,
                     help="retain completed live view before exit (default: 60)")
    run.add_argument("--clock-interval-ms", type=int, default=250)
    run.add_argument("--lock", type=Path, default=Path("/run/lock/prplmesh-room-demo.lock"))
    replay = commands.add_parser("replay", help="serve a completed evidence directory offline")
    replay.add_argument("run_directory", type=Path)
    replay.add_argument("--listen", type=_address, default=("127.0.0.1", 8891), metavar="HOST:PORT")
    replay.add_argument("--serve-seconds", type=int, default=0,
                        help="exit after N seconds; zero serves until Ctrl-C")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "replay":
            return _replay(args)
        return _run(args)
    except (OSError, json.JSONDecodeError, ScenarioError, ActuatorError, ValueError) as error:
        print(f"room-demo: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
