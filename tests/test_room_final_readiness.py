import datetime as dt
import importlib.util
from pathlib import Path


def test_native_nanoseconds_work_on_python_310():
    path = Path(__file__).with_name("room-final-readiness.py")
    specification = importlib.util.spec_from_file_location("readiness", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.parse_timestamp("2026-09-09T21:33:19.167399448Z") == dt.datetime(
        2026, 9, 9, 21, 33, 19, 167399, tzinfo=dt.timezone.utc)
    assert module.parse_timestamp("2026-09-09T21:33:19Z").microsecond == 0
