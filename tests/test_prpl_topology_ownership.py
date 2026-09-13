from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0019-controller-order-associated-client-recovery.patch"


def fragments():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    return "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                     if line.startswith(("+", " ")) and not line.startswith("+++"))


def test_native_notifications_record_live_association_authority():
    source = fragments()
    notification = source[source.index('        LOG(INFO) << "client connected, al_mac="'):]
    assert "client->association_event_time = std::chrono::steady_clock::now();" in notification


@pytest.mark.parametrize("removed_guard", [None, "age", "completion", "empty", "owner", "detach"])
def test_native_topology_recovery_preserves_newer_ownership(tmp_path, removed_guard):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native topology reconciliation")
    source = fragments()
    handler = source[source.index("bool topology_task::handle_associated_clients_tlv"):
                     source.index("void topology_task::handle_vbss_configuration_tlv")]
    ownership = source[source.index("    std::shared_ptr<Agent::sRadio::sBss> old_parent"):
                       source.index("bool db::remove_sta")]
    ownership = ownership[:ownership.index("\n}")]
    removal = source[source.index("bool db::remove_sta"):
                     source.index("bool db::set_agent_ipv4")]
    state = source[source.index("bool db::set_sta_state"):
                   source.index("beerocks::eNodeState db::get_sta_state")]
    removal = removal.replace("db::remove_sta", "Database::remove_sta")
    state = state.replace("db::set_sta_state", "Database::set_sta_state")
    if removed_guard == "age":
        handler = handler.replace("association_times.at(connected.first) <= station->association_event_time", "false")
    elif removed_guard == "completion":
        handler = handler.replace("son_actions::handle_completed_connection(database, cmdu_tx, tasks,",
                                  "son_actions::skip_completion(database, cmdu_tx, tasks,")
    elif removed_guard == "empty":
        handler = handler.replace("    std::unordered_map<sMacAddr, sMacAddr> previous_connected;",
                                  "    if (!assoc_client_tlv) return true;\n    std::unordered_map<sMacAddr, sMacAddr> previous_connected;")
    elif removed_guard == "owner":
        handler = handler.replace("station->get_bss() == bss &&", "true &&")
        handler = handler.replace("station && station->get_bss() == bss", "station != nullptr")
    elif removed_guard == "detach":
        removal = removal.replace("bss->connected_stations.erase(mac);", "(void)mac;")
    program = r'''
#include <chrono>
#include <cstdint>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>
#define LOG(level) std::ostringstream()
using sMacAddr = int;
using Clock = std::chrono::steady_clock;
namespace beerocks {
enum eNodeState { STATE_DISCONNECTED, STATE_CONNECTED };
constexpr int IFACE_TYPE_WIFI_UNSPECIFIED = 1;
}
namespace tlvf {
int mac_from_string(const std::string &address) { return std::stoi(address); }
std::string mac_to_string(int address) { return std::to_string(address); }
}
template<class Value> struct MacMap : std::map<int, std::shared_ptr<Value>> {
    void add(std::shared_ptr<Value> value) { (*this)[value->mac] = value; }
};
struct Bss;
struct Station {
    int mac = 0, steering_task_id = 1, btm_request_task_id = 2;
    beerocks::eNodeState state = beerocks::STATE_DISCONNECTED;
    Clock::time_point association_event_time = Clock::time_point::min();
    std::shared_ptr<Bss> parent, previous;
    std::string dm_path;
    unsigned clears = 0;
    std::shared_ptr<Bss> get_bss() { return parent; }
    void set_bss(std::shared_ptr<Bss> bss) { previous = parent; parent = bss; }
    void clear_cross_rssi() { clears++; }
};
struct Bss { int bssid; MacMap<Station> connected_stations; };
struct Agent {
    struct sRadio {
        using sBss = Bss;
        int radio_uid = 1;
        std::map<int, std::shared_ptr<Bss>> bsses;
    };
    int al_mac;
    std::map<int, std::shared_ptr<sRadio>> radios;
};
struct Database {
    MacMap<Station> m_stations;
    std::map<std::pair<int,int>, std::shared_ptr<Bss>> bsses;
    std::shared_ptr<Agent::sRadio> radio = std::make_shared<Agent::sRadio>();
    unsigned completions = 0, clears = 0;
    bool add_success = true, remove_success = true;
    std::vector<int> cleaned_aps;
    std::shared_ptr<Station> get_station(int mac) {
        auto found = m_stations.find(mac);
        return found == m_stations.end() ? nullptr : found->second;
    }
    std::shared_ptr<Bss> get_bss(int bssid, int agent) {
        auto found = bsses.find({bssid, agent});
        return found == bsses.end() ? nullptr : found->second;
    }
    void set_station_bss(std::shared_ptr<Station> station, std::shared_ptr<Bss> bss) {
        OWNERSHIP
    }
    std::shared_ptr<Station> add_station(int agent, int mac, int bssid) {
        if (!add_success) return nullptr;
        auto station = get_station(mac);
        if (!station) {
            station = std::make_shared<Station>();
            station->mac = mac;
            m_stations.add(station);
        }
        set_station_bss(station, get_bss(bssid, agent));
        station->dm_path = std::to_string(bssid);
        return station;
    }
    bool remove_sta(const sMacAddr &mac);
    bool set_sta_state(const std::string &mac, beerocks::eNodeState state);
    std::shared_ptr<Agent::sRadio> get_radio_by_bssid(int) { return radio; }
    int get_radio_wifi_channel(int) { return 36; }
    void set_sta_wifi_channel(int, int) {}
    void set_sta_backhaul_iface_type(int, int) {}
    void clear_sta_stats_info(int) { clears++; }
    void dm_clear_sta_stats(int) { clears++; }
    int get_dhcp_task_id() { return 3; }
    bool dm_remove_sta(Station &station) { station.dm_path.clear(); return remove_success; }
};
REMOVAL
STATE_METHOD
struct Tasks {
    unsigned events = 0;
    bool is_task_running(int) { return true; }
    void push_event(int, int) { events++; }
};
struct client_steering_task { enum { STA_CONNECTED }; };
struct DhcpTask { enum { STA_CONNECTED }; };
namespace son_actions {
void handle_completed_connection(Database &database, int, Tasks &, std::string mac) {
    auto station = database.get_station(tlvf::mac_from_string(mac));
    database.set_sta_state(mac, beerocks::STATE_CONNECTED);
    database.completions++;
    if (station->previous && station->previous != station->parent)
        database.cleaned_aps.push_back(station->previous->bssid);
}
void skip_completion(Database &, int, Tasks &, std::string) {}
void handle_dead_station(std::string mac, bool, Database &database, Tasks &) {
    database.set_sta_state(mac, beerocks::STATE_DISCONNECTED);
}
}
namespace wfa_map {
struct Client {
    int address;
    uint16_t age;
    bool valid = true;
    int mac() { return address; }
    uint16_t time_since_last_association_sec() { return age; }
};
struct BssEntry {
    int address;
    std::vector<Client> clients;
    bool valid = true;
    int bssid() { return address; }
    int clients_associated_list_length() { return clients.size(); }
    std::tuple<bool, Client &> clients_associated_list(int index) {
        return {clients.at(index).valid, clients.at(index)};
    }
};
struct tlvAssociatedClients {
    std::vector<BssEntry> bsses;
    int bss_list_length() { return bsses.size(); }
    std::tuple<bool, BssEntry &> bss_list(int index) {
        return {bsses.at(index).valid, bsses.at(index)};
    }
};
}
namespace ieee1905_1 {
struct CmduMessageRx {
    std::shared_ptr<wfa_map::tlvAssociatedClients> report;
    template<class Value> std::shared_ptr<Value> getClass() { return report; }
};
}
struct topology_task {
    Database &database;
    int cmdu_tx = 0;
    Tasks tasks;
    bool handle_associated_clients_tlv(ieee1905_1::CmduMessageRx &, Agent &);
};
HANDLER
int main() {
    Database database;
    auto old_bss = std::make_shared<Bss>(); old_bss->bssid = 101;
    auto new_bss = std::make_shared<Bss>(); new_bss->bssid = 201;
    Agent old_agent{10, {}}, new_agent{20, {}};
    auto old_radio = std::make_shared<Agent::sRadio>(); old_radio->bsses[101] = old_bss;
    auto new_radio = std::make_shared<Agent::sRadio>(); new_radio->bsses[201] = new_bss;
    old_agent.radios[1] = old_radio; new_agent.radios[1] = new_radio;
    database.bsses[{101,10}] = old_bss; database.bsses[{201,20}] = new_bss;
    auto station = database.add_station(10, 11, 101);
    database.set_sta_state("11", beerocks::STATE_CONNECTED);
    station->association_event_time = Clock::now() - std::chrono::seconds(100);
    topology_task task{database, 0, {}};
    auto apply = [&](Agent &agent, std::vector<wfa_map::BssEntry> bsses) {
        ieee1905_1::CmduMessageRx message{std::make_shared<wfa_map::tlvAssociatedClients>()};
        message.report->bsses = bsses;
        return task.handle_associated_clients_tlv(message, agent);
    };
    if (!apply(new_agent, {{201, {{11, 10}}}})) return 1;
    if (station->parent != new_bss || station->state != beerocks::STATE_CONNECTED ||
        database.completions != 1 || database.cleaned_aps != std::vector<int>{101} ||
        task.tasks.events != 3 || old_bss->connected_stations.count(11)) return 1;
    auto connection_time = station->association_event_time;
    if (!apply(old_agent, {{101, {{11, UINT16_MAX}}}}) || station->parent != new_bss ||
        database.completions != 1) return 1;
    if (!apply(old_agent, {{101, {{11, 100}}}}) || station->parent != new_bss ||
        database.completions != 1) return 1;
    if (!apply(new_agent, {{201, {{11, 10}}}}) || station->association_event_time != connection_time ||
        database.completions != 1 || database.clears != 2) return 1;
    old_bss->connected_stations[11] = station;
    if (!apply(old_agent, {{101, {}}}) || station->state != beerocks::STATE_CONNECTED ||
        station->dm_path.empty()) return 1;
    old_bss->connected_stations.erase(11);
    ieee1905_1::CmduMessageRx empty{};
    if (!task.handle_associated_clients_tlv(empty, new_agent) ||
        station->state != beerocks::STATE_DISCONNECTED || !station->dm_path.empty() ||
        !database.get_station(11) || new_bss->connected_stations.count(11)) return 1;
    auto departure_time = station->association_event_time;
    if (!task.handle_associated_clients_tlv(empty, new_agent) ||
        station->association_event_time != departure_time) return 1;
    if (!apply(old_agent, {{101, {{11, 100}}}}) || station->state != beerocks::STATE_DISCONNECTED) return 1;
    station->association_event_time = Clock::now() - std::chrono::seconds(5);
    if (!apply(new_agent, {{201, {{11, 0}}}}) || station->state != beerocks::STATE_CONNECTED ||
        database.completions != 2) return 1;
    if (!apply(old_agent, {{101, {{22, 30}}}}) || !database.get_station(22)) return 1;
    auto previous_time = database.get_station(22)->association_event_time;
    database.set_sta_state("22", beerocks::STATE_CONNECTED);
    database.set_station_bss(database.get_station(22), old_bss);
    if (database.get_station(22)->association_event_time != previous_time) return 1;
    if (!database.remove_sta(22) || database.get_station(22) || old_bss->connected_stations.count(22)) return 1;
    auto orphan = std::make_shared<Station>(); orphan->mac = 42; orphan->parent = new_bss;
    orphan->state = beerocks::STATE_CONNECTED; new_bss->connected_stations[42] = orphan;
    if (!apply(new_agent, {{201, {{11, 0}, {42, 20}}}}) || !database.get_station(42) ||
        database.get_station(42) == orphan || new_bss->connected_stations.at(42) != database.get_station(42)) return 1;
    auto completions = database.completions;
    if (apply(new_agent, {{101, {{55, 0}}}}) || apply(new_agent, {{201, {{55, 0}, {55, 0}}}}) ||
        apply(new_agent, {{201, {}, false}}) || apply(new_agent, {{201, {{55, 0, false}}}})) return 1;
    if (database.completions != completions || database.get_station(55)) return 1;
    database.add_success = false;
    if (apply(new_agent, {{201, {{55, 0}}}})) return 1;
    database.add_success = true; database.remove_success = false;
    if (task.handle_associated_clients_tlv(empty, new_agent)) return 1;
}
'''.replace("OWNERSHIP", ownership).replace("REMOVAL", removal).replace("STATE_METHOD", state).replace("HANDLER", handler)
    cpp = tmp_path / "topology.cpp"
    cpp.write_text(program)
    binary = tmp_path / "topology"
    compiled = subprocess.run([compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
                              capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary)], timeout=5)
    assert (result.returncode == 0) == (removed_guard is None)
