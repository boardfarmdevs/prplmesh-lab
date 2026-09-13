from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/hostap/0002-notify-successful-reauthorization.patch"


@pytest.mark.parametrize("remove_pending_guard", [False, True])
def test_native_authorization_event_tracks_new_associations(tmp_path, remove_pending_guard):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for hostapd event regression")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    source = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                       if line.startswith(("+", " ")) and not line.startswith("+++"))
    guard = source[source.index("\tif (!!authorized"):
                   source.index("\tif (authorized)")]
    if remove_pending_guard:
        guard = guard.replace(" &&\n\t    !(authorized && sta->authorization_event_pending)", "")
    program = r'''
#include <assert.h>
#define WLAN_STA_AUTHORIZED 1
struct Station {
    unsigned int flags;
    unsigned int authorization_event_pending:1;
    unsigned int connected_events;
    unsigned int disconnected_events;
};
static void authorize(struct Station *sta, int authorized)
{
GUARD
    if (authorized) {
        sta->flags |= WLAN_STA_AUTHORIZED;
        sta->connected_events++;
    } else {
        sta->flags &= ~WLAN_STA_AUTHORIZED;
        sta->disconnected_events++;
    }
}
int main(void)
{
    struct Station station = {0};
    authorize(&station, 0);
    assert(station.disconnected_events == 0);
    station.authorization_event_pending = 1;
    authorize(&station, 1);
    assert(station.connected_events == 1);
    assert(!station.authorization_event_pending);
    authorize(&station, 1);
    assert(station.connected_events == 1);
    station.authorization_event_pending = 1;
    authorize(&station, 1);
    assert(station.connected_events == 2);
    assert(station.disconnected_events == 0);
    authorize(&station, 1);
    assert(station.connected_events == 2);
    station.authorization_event_pending = 1;
    authorize(&station, 0);
    assert(station.disconnected_events == 1);
    assert(!station.authorization_event_pending);
    authorize(&station, 0);
    assert(station.disconnected_events == 1);
    authorize(&station, 1);
    assert(station.connected_events == 3);
    assert(station.disconnected_events == 1);
    return 0;
}
'''.replace("GUARD", guard)
    source_file = tmp_path / "reauthorization.c"
    binary = tmp_path / "reauthorization"
    source_file.write_text(program)
    subprocess.run([compiler, "-Wall", "-Wextra", "-Werror", str(source_file),
                    "-o", str(binary)], check=True, capture_output=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert (result.returncode == 0) != remove_pending_guard


def test_failed_association_responses_do_not_arm_notification():
    source = PATCH.read_text()
    assert " \tif (status != WLAN_STATUS_SUCCESS)\n \t\treturn;\n \n+\tsta->authorization_event_pending = 1;" in source
