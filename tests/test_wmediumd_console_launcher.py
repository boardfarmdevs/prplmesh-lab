"""The lab's console launcher hands the running medium's metadata to the console
(moved from the console's packaging test when the console became easymesh-medium's)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_publishes_console_metadata():
    text = (ROOT / "scripts/wmediumd-console.sh").read_text()
    for want in (
        "INVENTORY=$RUNTIME/identity-inventory.json",
        "publish_runtime_metadata",
        "generate-wmediumd-identity-inventory.py",
        '--output "$INVENTORY"',
        "printf '%s\\t%s\\t%s\\n' \"$pid\" \"$sha256\" \"$executable\"",
    ):
        assert want in text, f"wmediumd-console.sh missing runtime handoff {want!r}"
