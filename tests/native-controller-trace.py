#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import time
import threading


PROFILES = {
    "rdk": ("onewifi_em_ctrl", "dbb74dab3009f4e01cf0c0c9ba519760f2350997f245fb6afc0defbafc5de20d"),
    "prpl": ("beerocks_controller", "5f66442074ee3fd51b7a172dad4fa7996fcb94d19db1c7a01dc2ab5ffe74673d"),
}
PRPL_ASSOCIATION = "_ZN3son2db18dm_add_sta_elementERK8sMacAddrS3_RN8prplmesh10controller2db7StationE"


def program(stack):
    common = """
#include <uapi/linux/ptrace.h>
struct event {
    u64 timestamp;
    u8 station[6];
    u8 bssid[6];
    u8 associated;
    u8 rcpi;
};
BPF_PERF_OUTPUT(events);
BPF_ARRAY(count, u64, 1);
static inline int publish(struct pt_regs *context, struct event *event) {
    event->timestamp = bpf_ktime_get_ns();
    int index = 0;
    u64 *total = count.lookup(&index);
    if (total) __sync_fetch_and_add(total, 1);
    events.perf_submit(context, event, sizeof(*event));
    return 0;
}
"""
    if stack == "rdk":
        return common + """
int commit(struct pt_regs *context) {
    u32 object = 0;
    struct event event = {};
    bpf_probe_read_user(&object, sizeof(object), (void *)(context->bp - 0x78));
    bpf_probe_read_user(event.station, 6, (void *)((u64)object + 4));
    bpf_probe_read_user(event.bssid, 6, (void *)((u64)object + 10));
    bpf_probe_read_user(&event.associated, 1, (void *)((u64)object + 22));
    bpf_probe_read_user(&event.rcpi, 1, (void *)((u64)object + 0xd4));
    return publish(context, &event);
}
"""
    return common + """
BPF_HASH(pending, u64, struct event, 1024);
int enter(struct pt_regs *context) {
    u64 thread = bpf_get_current_pid_tgid();
    struct event event = {};
    bpf_probe_read_user(event.station, 6, (void *)PT_REGS_PARM4(context));
    bpf_probe_read_user(event.bssid, 6, (void *)PT_REGS_PARM3(context));
    event.associated = 1;
    event.rcpi = 255;
    pending.update(&thread, &event);
    return 0;
}
int commit(struct pt_regs *context) {
    u64 thread = bpf_get_current_pid_tgid();
    struct event *event = pending.lookup(&thread);
    if (event && PT_REGS_RC(context) == 1) publish(context, event);
    pending.delete(&thread);
    return 0;
}
"""


def controller(stack):
    name, expected = PROFILES[stack]
    matches = []
    for entry in Path("/proc").glob("[0-9]*/exe"):
        try:
            if entry.resolve().name == name:
                matches.append(entry)
        except OSError:
            continue
    if len(matches) != 1:
        raise ValueError(f"requires exactly one {name} process, found {len(matches)}")
    binary = matches[0]
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"unsupported native binary SHA256: {actual}; qualify a new probe profile")
    return str(binary), expected


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded, opt-in native association commit probes")
    parser.add_argument("--stack", choices=tuple(PROFILES), required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--watch-stdin", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() or not 5 <= args.seconds <= 180:
        parser.error("requires root and 5..180 seconds")
    from bcc import BPF
    binary, digest = controller(args.stack)
    records = 0
    lost = 0
    stopping = False
    output_lock = threading.Lock()

    def emit(value):
        with output_lock:
            print(json.dumps(value), flush=True)

    def stop(_signal=None, _frame=None):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    probe = BPF(text=program(args.stack))
    try:
        def consume(_cpu, data, _size):
            nonlocal records
            event = probe["events"].event(data)
            records += 1
            emit({"kind": "commit", "monotonic_ns": event.timestamp,
                              "sta": ":".join(f"{octet:02x}" for octet in event.station),
                              "bssid": ":".join(f"{octet:02x}" for octet in event.bssid),
                              "associated": bool(event.associated),
                              "rcpi": event.rcpi if event.rcpi <= 220 else None})

        def dropped(amount):
            nonlocal lost
            lost += amount

        probe["events"].open_perf_buffer(consume, page_cnt=64, lost_cb=dropped)
        if args.stack == "rdk":
            for address in (0xdf948, 0xdf989):
                probe.attach_uprobe(name=binary, addr=address, fn_name="commit")
        else:
            probe.attach_uprobe(name=binary, sym=PRPL_ASSOCIATION, fn_name="enter")
            probe.attach_uretprobe(name=binary, sym=PRPL_ASSOCIATION, fn_name="commit")
        emit({"kind": "identity", "stack": args.stack, "sha256": digest,
                          "binary": binary, "clock": "guest-monotonic",
                          "boundary": "native-model-association-commit"})
        emit({"kind": "ready"})

        def control():
            for raw in sys.stdin:
                request = raw.strip()
                if request.startswith("clock:") and request[6:].isdigit():
                    emit({"kind": "clock", "request": request, "monotonic_ms": time.monotonic_ns() / 1000000})
                else:
                    stop()
                    return
            stop()

        if args.watch_stdin:
            threading.Thread(target=control, daemon=True).start()
        deadline = time.monotonic() + args.seconds
        while not stopping and time.monotonic() < deadline:
            probe.perf_buffer_poll(timeout=100)
            if records > 100000:
                raise ValueError("native trace exceeded event budget")
        if args.stack == "rdk":
            for address in (0xdf948, 0xdf989):
                probe.detach_uprobe(name=binary, addr=address)
        else:
            probe.detach_uprobe(name=binary, sym=PRPL_ASSOCIATION)
            probe.detach_uretprobe(name=binary, sym=PRPL_ASSOCIATION)
        probe.perf_buffer_poll(timeout=100)
        emitted = probe["count"][0].value
        if lost or emitted != records:
            raise RuntimeError(f"incomplete trace: received={records}, emitted={emitted}, lost={lost}")
        if controller(args.stack) != (binary, digest):
            raise RuntimeError("controller changed during trace")
        emit({"kind": "end", "records": records, "emitted": emitted, "lost": lost})
    finally:
        probe.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
