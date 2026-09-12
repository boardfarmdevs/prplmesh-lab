import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "native_controller_trace", Path(__file__).with_name("native-controller-trace.py"))
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class FakeProbe:
    def __init__(self, fail_attach=False):
        self.opened = False
        self.cleaned = False
        self.attached = 0
        self.fail_attach = fail_attach

    def __getitem__(self, key):
        return self if key == "events" else [SimpleNamespace(value=0)]

    def open_perf_buffer(self, *_args, **_kwargs):
        self.opened = True

    def attach_uprobe(self, **_kwargs):
        if not self.opened:
            raise AssertionError("probe attached before its event consumer")
        if self.fail_attach:
            raise RuntimeError("attachment failed")
        self.attached += 1

    attach_uretprobe = attach_uprobe

    def detach_uprobe(self, **_kwargs):
        self.attached -= 1

    detach_uretprobe = detach_uprobe

    def perf_buffer_poll(self, **_kwargs):
        pass

    def cleanup(self):
        self.cleaned = True


class NativeTraceTest(unittest.TestCase):
    def run_trace(self, stack, probe):
        with contextlib.ExitStack() as contexts:
            contexts.enter_context(patch.dict("sys.modules", {
                "bcc": SimpleNamespace(BPF=lambda **_kwargs: probe)}))
            contexts.enter_context(patch.object(trace.os, "geteuid", return_value=0))
            contexts.enter_context(patch.object(trace, "controller", return_value=("binary", "digest")))
            contexts.enter_context(patch.object(trace.signal, "signal"))
            contexts.enter_context(patch.object(trace.time, "monotonic", side_effect=[0, 10]))
            contexts.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return trace.main(["--stack", stack, "--seconds", "5"])

    def test_consumer_precedes_both_native_profiles(self):
        for stack in ("rdk", "prpl"):
            with self.subTest(stack=stack):
                probe = FakeProbe()
                self.assertEqual(self.run_trace(stack, probe), 0)
                self.assertTrue(probe.cleaned)
                self.assertEqual(probe.attached, 0)

    def test_failed_attachment_cleans_up(self):
        probe = FakeProbe(fail_attach=True)
        with self.assertRaisesRegex(RuntimeError, "attachment failed"):
            self.run_trace("rdk", probe)
        self.assertTrue(probe.cleaned)
