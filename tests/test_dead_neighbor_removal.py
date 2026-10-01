from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0033-controller-scope-wired-neighbor-removal.patch"
SOURCE_PATH = "controller/src/beerocks/master/tasks/topology_task.cpp"


def dead_neighbors_fragment(patched):
    result = subprocess.run(
        ["git", "apply", "--numstat", str(PATCH)], check=True,
        capture_output=True, text=True,
    )
    assert [line.split("\t")[2] for line in result.stdout.splitlines()] == [SOURCE_PATH]
    selected = (" ", "+" if patched else "-")
    fragments = []
    in_hunk = False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line.startswith(selected):
            fragments.append(line[1:])
    source = "\n".join(fragments)
    assert source.startswith("void topology_task::handle_dead_neighbors(")
    assert source.endswith("\n}")
    return source


HARNESS = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <list>
#include <map>
#include <memory>
#include <string>
#include <unordered_set>

struct LogSink {
    template <typename Value> LogSink &operator<<(const Value &) { return *this; }
};
#define LOG(level) LogSink()

struct sMacAddr {
    unsigned char oct[6];
    bool operator==(const sMacAddr &other) const { return std::memcmp(oct, other.oct, 6) == 0; }
    bool operator!=(const sMacAddr &other) const { return !(*this == other); }
    bool operator<(const sMacAddr &other) const { return std::memcmp(oct, other.oct, 6) < 0; }
};
namespace std {
template <> struct hash<sMacAddr> {
    size_t operator()(const sMacAddr &mac) const { return mac.oct[4] << 8 | mac.oct[5]; }
};
} // namespace std
sMacAddr mac(unsigned char a, unsigned char b) { return {{2, 0, 0, 0x27, a, b}}; }

namespace tlvf {
std::string mac_to_string(const sMacAddr &mac)
{
    char text[18];
    std::snprintf(text, sizeof(text), "%02x:%02x:%02x:%02x:%02x:%02x", mac.oct[0], mac.oct[1],
                  mac.oct[2], mac.oct[3], mac.oct[4], mac.oct[5]);
    return text;
}
} // namespace tlvf

struct Agent {
    sMacAddr al_mac;
    sMacAddr parent_mac;
    struct {
        std::weak_ptr<Agent> parent_agent;
    } backhaul;
};
struct Radio {
    sMacAddr radio_uid;
};
struct Bss {
    Radio radio;
};
struct Station {
    std::shared_ptr<Bss> bss;
    std::shared_ptr<Bss> get_bss() { return bss; }
};

struct Database {
    std::map<sMacAddr, std::shared_ptr<Agent>> agents;
    std::map<sMacAddr, std::shared_ptr<Station>> stations;
    std::map<sMacAddr, std::list<sMacAddr>> neighbors;
    std::map<sMacAddr, sMacAddr> radio_owners;
    std::list<sMacAddr> get_1905_1_neighbors(const sMacAddr &al_mac) { return neighbors[al_mac]; }
    std::shared_ptr<Agent> get_agent(const sMacAddr &al_mac)
    {
        auto agent = agents.find(al_mac);
        return agent == agents.end() ? nullptr : agent->second;
    }
    std::shared_ptr<Station> get_station(const sMacAddr &station_mac)
    {
        auto station = stations.find(station_mac);
        return station == stations.end() ? nullptr : station->second;
    }
    std::shared_ptr<Agent> get_agent_by_radio_uid(const sMacAddr &radio_uid)
    {
        auto owner = radio_owners.find(radio_uid);
        return owner == radio_owners.end() ? nullptr : get_agent(owner->second);
    }
    bool remove_agent(const sMacAddr &al_mac) { return agents.erase(al_mac) == 1; }
};
struct Tasks {};

std::list<std::string> dead_stations;
namespace son_actions {
void handle_dead_station(const std::string &station_mac, bool, Database &, Tasks &)
{
    dead_stations.push_back(station_mac);
}
} // namespace son_actions

struct topology_task {
    Database &database;
    Tasks &tasks;
    void handle_dead_neighbors(const sMacAddr &src_mac, const sMacAddr &al_mac,
                               std::unordered_set<sMacAddr> reported_neighbor_al_macs);
};

NATIVE_FRAGMENT

// The prpl lab: the controller's own Agent (01:01) with the wired prpl-agent-05 (06:01)
// below it; prpl-agent-01 (02:01) and prpl-agent-03 (04:01) are wireless.
const sMacAddr controller = mac(1, 1), agent_01 = mac(2, 1), agent_03 = mac(4, 1),
               agent_05 = mac(6, 1);

std::shared_ptr<Agent> add_agent(Database &database, const sMacAddr &al_mac,
                                 const sMacAddr &station_mac, std::shared_ptr<Bss> bss)
{
    auto agent = std::make_shared<Agent>(Agent{al_mac, station_mac, {}});
    database.agents[al_mac] = agent;
    database.stations[station_mac] = std::make_shared<Station>(Station{bss});
    return agent;
}

std::shared_ptr<Bss> bss_of(Database &database, const sMacAddr &owner, unsigned char radio)
{
    const sMacAddr radio_uid{{2, 0, 0, 0, radio, 0}};
    database.radio_owners[radio_uid] = owner;
    return std::make_shared<Bss>(Bss{Radio{radio_uid}});
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    const std::string scenario = argv[1];
    Database database;
    Tasks tasks;
    topology_task task{database, tasks};

    add_agent(database, controller, mac(0x10, 1), nullptr);
    auto wired = add_agent(database, agent_05, mac(0x16, 1), nullptr);
    wired->backhaul.parent_agent = database.agents[controller];
    add_agent(database, agent_01, mac(0x12, 1), bss_of(database, controller, 1));
    add_agent(database, agent_03, mac(0x14, 1), bss_of(database, agent_01, 4));

    sMacAddr reporter = agent_03;
    std::unordered_set<sMacAddr> reported;
    if (scenario == "wireless_roamed_off_wired") {
        // prpl-agent-03 left prpl-agent-05's backhaul BSS for prpl-agent-01's.
        database.neighbors[agent_03] = {agent_05, agent_01};
        reported = {agent_01};
    } else if (scenario == "wired_parent_unknown") {
        wired->backhaul.parent_agent.reset();
        database.neighbors[agent_03] = {agent_05, agent_01};
        reported = {agent_01};
    } else if (scenario == "wired_child_gone") {
        reporter = controller;
        database.neighbors[controller] = {agent_05, agent_01};
        reported = {agent_01};
    } else if (scenario == "wireless_child_gone") {
        reporter = agent_01;
        database.neighbors[agent_01] = {controller, agent_03};
        reported = {controller};
    } else if (scenario == "wireless_rerouted") {
        // prpl-agent-03 is now below prpl-agent-01, so prpl-agent-05 does not own it.
        reporter = agent_05;
        database.neighbors[agent_05] = {controller, agent_03};
        reported = {controller};
    } else {
        return 2;
    }
    task.handle_dead_neighbors(reporter, reporter, reported);

    std::string present;
    for (const auto &agent : database.agents) {
        present += (present.empty() ? "" : " ") + tlvf::mac_to_string(agent.first).substr(12);
    }
    std::printf("agents=%s dead_stations=%zu\n", present.c_str(), dead_stations.size());
    return 0;
}
'''


@pytest.fixture(scope="module", params=[True, False], ids=["patched", "unpatched"])
def dead_neighbors_binary(request, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for dead neighbor regression")
    directory = tmp_path_factory.mktemp("dead-neighbors")
    program = directory / "dead_neighbors.cpp"
    program.write_text(HARNESS.replace("NATIVE_FRAGMENT", dead_neighbors_fragment(request.param)))
    binary = directory / "dead_neighbors"
    result = subprocess.run(
        [compiler, "-std=c++14", "-O0", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
         str(program), "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return binary, request.param


ALL = "01:01 02:01 04:01 06:01"
WITHOUT_05 = "agents=01:01 02:01 04:01 dead_stations=1\n"
KEPT = f"agents={ALL} dead_stations=0\n"
CASES = {
    # scenario: (patched, unpatched)
    "wireless_roamed_off_wired": (KEPT, WITHOUT_05),
    "wired_parent_unknown": (KEPT, WITHOUT_05),
    "wired_child_gone": (WITHOUT_05, WITHOUT_05),
    "wireless_child_gone": ("agents=01:01 02:01 06:01 dead_stations=1\n",) * 2,
    "wireless_rerouted": (KEPT, KEPT),
}


@pytest.mark.parametrize("scenario", CASES)
def test_dead_neighbor_removal(dead_neighbors_binary, scenario):
    binary, patched = dead_neighbors_binary
    result = subprocess.run([str(binary), scenario], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == CASES[scenario][0 if patched else 1]
