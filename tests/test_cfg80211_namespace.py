from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "scripts/cfg80211"
PATCH = DIRECTORY / "0001-scope-socket-release-to-owner-netns.patch"


@pytest.mark.parametrize("namespace_guard", [True, False])
def test_socket_release_preserves_other_namespace_owners(tmp_path, namespace_guard):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for cfg80211 namespace regression")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    guard = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                      if line.startswith("+\t")) if namespace_guard else ""
    program = r'''
#include <assert.h>
struct Radio { int wiphy; unsigned int mutations; };
struct Notify { int net; };
static int wiphy_net(int *wiphy) { return *wiphy; }
static int net_eq(int left, int right) { return left == right; }
static void release(struct Radio *radios, struct Notify *notify)
{
    for (unsigned int index = 0; index < 2; index++) {
        struct Radio *rdev = &radios[index];
GUARD
        rdev->mutations++;
    }
}
int main(void)
{
    struct Radio radios[] = {{1, 0}, {2, 0}};
    struct Notify foreign = {3}, first = {1}, second = {2};
    release(radios, &foreign);
    assert(radios[0].mutations == 0 && radios[1].mutations == 0);
    release(radios, &first);
    assert(radios[0].mutations == 1 && radios[1].mutations == 0);
    release(radios, &second);
    assert(radios[0].mutations == 1 && radios[1].mutations == 1);
    return 0;
}
'''.replace("GUARD", guard)
    source = tmp_path / "namespace.c"
    binary = tmp_path / "namespace"
    source.write_text(program)
    subprocess.run([compiler, "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                    "-Wno-unused-parameter", str(source), "-o", str(binary)],
                   check=True, capture_output=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert (result.returncode == 0) == namespace_guard


def test_guard_precedes_all_radio_socket_cleanup():
    patch = PATCH.read_text()
    assert patch.index("net_eq(wiphy_net(&rdev->wiphy), notify->net)") < patch.index("list_for_each_entry_rcu(sched_scan_req,")
    assert 'MODULE_VERSION("lab-netns-owner-1")' in patch
    builder = (DIRECTORY / "build-cfg80211.sh").read_text()
    assert 'apt-get source --download-only "$PACKAGE=$VERSION"' in builder
    assert "sha256sum -c checksums" in builder
    assert '"${CFG80211_BUILD_JOBS:-4}"' in builder
