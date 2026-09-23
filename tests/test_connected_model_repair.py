from pathlib import Path
import shutil
import subprocess

import pytest

from test_backhaul_roaming import added_source


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0029-repair-connected-station-model-path.patch"


@pytest.mark.parametrize("negative_control", [False, True])
def test_connected_path_repair_preserves_native_authority(tmp_path, negative_control):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native model repair regression")
    patch = PATCH.read_text()
    header = added_source("controller/src/beerocks/master/db/topology_query_tracker.h")
    getter = next(line[1:] for line in patch.splitlines() if line.startswith("+    bool may_repair"))
    header = header.replace("    bool may_restore() const", getter + "\n    bool may_restore() const", 1)
    branch = patch.split("+++ b/controller/src/beerocks/master/tasks/topology_task.cpp\n")[1]
    branch = branch.split("--- a/controller/src/beerocks/master/controller.cpp")[0]
    branch = "\n".join(line[1:] for line in branch.splitlines() if line.startswith("+"))
    source = r"""
#include <cassert>
#include <map>
#include <sstream>
#include <string>
HEADER
namespace beerocks { constexpr int STATE_CONNECTED = 2; }
namespace tlvf { std::string mac_to_string(int value) { return std::to_string(value); } }
#define LOG(level) std::ostringstream()
using son::TopologyQueryTracker;
struct Station {
    int state = beerocks::STATE_CONNECTED;
    int owner = 10;
    std::string parent_mac = "10";
    std::string dm_path;
    son::AssociationRecoveryState association_recovery;
    TopologyQueryTracker::Time association_event_time = TopologyQueryTracker::Time(std::chrono::seconds(10));
    int get_bss() const { return owner; }
};
struct Database {
    int calls = 0;
    bool success = true;
    Station *station = nullptr;
    bool add_station(int agent, int mac, int owner) {
        assert(agent == 1 && mac == 20 && owner == 10);
        ++calls;
        if (success) station->dm_path = "native.BSS.1.STA.1";
        return success;
    }
} database;
struct Agent { int al_mac = 1; } agent;
struct Message { int getMessageId() const { return 100; } } cmdu_rx;
int fallthrough = 0;
bool reconcile(Station *station, int bss, TopologyQueryTracker::Time query_sent,
               TopologyQueryTracker::Time now) {
    database.station = station;
    for (const auto &connected : std::map<int, int>{{20, 10}}) {
BRANCH
        ++fallthrough;
    }
    return true;
}
int main() {
    using Time = TopologyQueryTracker::Time;
    const Time query(std::chrono::seconds(11));
    const Time now(std::chrono::seconds(12));
    for (int failure = 0; failure < 11; ++failure) {
        Station station;
        auto sent = query;
        auto observed = now;
        int bss = 10;
        if (failure == 1) station.state = 0;
        if (failure == 2) station.dm_path = "existing";
        if (failure == 3) station.owner = 11;
        if (failure == 4) bss = 0;
        if (failure == 5) station.parent_mac = "11";
        if (failure == 6) station.association_recovery.client_departed();
        if (failure == 7) sent = Time::min();
        if (failure == 8) sent = station.association_event_time;
        if (failure == 9) observed = query - std::chrono::seconds(1);
        if (failure == 10) observed = query + std::chrono::seconds(6);
        const auto original_time = station.association_event_time;
        database.calls = fallthrough = 0;
        assert(reconcile(&station, bss, sent, observed));
        assert(database.calls == (failure == 0 ? 1 : 0));
        assert(fallthrough == (failure == 0 ? 0 : 1));
        assert(station.association_event_time == original_time);
        assert(station.parent_mac == (failure == 5 ? "11" : "10"));
        assert(station.state == (failure == 1 ? 0 : beerocks::STATE_CONNECTED));
    }
    Station station;
    database.success = false;
    database.calls = fallthrough = 0;
    assert(!reconcile(&station, 10, query, now));
    assert(database.calls == 1 && fallthrough == 0 && station.dm_path.empty());
}
"""
    source = source.replace("HEADER", header).replace("BRANCH", "" if negative_control else branch)
    path = tmp_path / "repair.cpp"
    path.write_text(source)
    binary = tmp_path / "repair"
    subprocess.run([compiler, "-std=c++14", str(path), "-o", str(binary)], check=True,
                   capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
    assert (result.returncode != 0) is negative_control, result.stderr


@pytest.mark.parametrize("negative_control", [False, True])
def test_matching_metrics_request_missing_model_repair(tmp_path, negative_control):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native model repair regression")
    patch = PATCH.read_text().split("+++ b/controller/src/beerocks/master/controller.cpp\n")[1]
    branch = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+"))
    source = r"""
#include <cassert>
#include <string>
#include <vector>
namespace beerocks { constexpr int STATE_CONNECTED = 2; }
struct Recovery {
    bool departed = false;
    bool may_repair_connected_path() const { return !departed; }
};
struct Station {
    int state = beerocks::STATE_CONNECTED;
    std::string dm_path;
    Recovery association_recovery;
};
struct Database {
    Station *station = nullptr;
    Station *get_station(int) { return station; }
} database;
struct Metric { int sta_mac() const { return 1; } } metric;
int queries = 0, writes = 0;
void accept_metrics(bool owner_matches) {
    bool needs_topology_query = false;
    for (auto sta_link_metric : std::vector<Metric *>{&metric, &metric}) {
        if (!owner_matches) continue;
BRANCH
        ++writes;
    }
    if (needs_topology_query) ++queries;
}
int main() {
    for (int scenario = 0; scenario < 6; ++scenario) {
        Station station;
        database.station = scenario == 1 ? nullptr : &station;
        if (scenario == 2) station.state = 0;
        if (scenario == 3) station.dm_path = "native.STA.1";
        if (scenario == 4) station.association_recovery.departed = true;
        queries = writes = 0;
        accept_metrics(scenario != 5);
        assert(queries == (scenario == 0 ? 1 : 0));
        assert(writes == ((scenario == 0 || scenario == 5) ? 0 : 2));
        assert(station.dm_path == (scenario == 3 ? "native.STA.1" : ""));
    }
}
""".replace("BRANCH", "" if negative_control else branch)
    path = tmp_path / "trigger.cpp"
    path.write_text(source)
    binary = tmp_path / "trigger"
    subprocess.run([compiler, "-std=c++14", str(path), "-o", str(binary)], check=True,
                   capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
    assert (result.returncode != 0) is negative_control, result.stderr
