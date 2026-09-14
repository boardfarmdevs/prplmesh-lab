from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0018-controller-reconcile-conflicting-station-reports.patch"


def native_fragments():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    return "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                     if line.startswith(("+", " ")) and not line.startswith("+++"))


@pytest.mark.parametrize("recovery_enabled", [True, False])
def test_conflicting_native_reports_request_authoritative_recovery(tmp_path, recovery_enabled):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native controller regression")
    source = native_fragments()
    handler = source[source.index("bool Controller::handle_tlv_associated_sta_link_metrics"):
                     source.index("bool Controller::handle_cmdu_1905_available_spectrum_inquiry_message")]
    if not recovery_enabled:
        handler = handler.replace("needs_topology_query = true;", "needs_topology_query = false;")
    traffic = re.search(
        r"        auto station = database.get_station\(sta_traffic_stat->sta_mac\(\)\);"
        r"[\s\S]*?(?=        db::sAssociatedStaTrafficStats stats;)", source
    ).group()
    program = r'''
#include <cassert>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>
#define LOG(level) std::ostringstream()
using sMacAddr = int;
namespace tlvf {
std::string mac_to_string(int address) { return std::to_string(address); }
}
struct Bss { int bssid; };
struct Station {
    std::shared_ptr<Bss> parent;
    std::shared_ptr<Bss> get_bss() { return parent; }
};
struct Report {
    int bssid;
    int downlink_estimated_mac_data_rate_mbps = 54;
    int uplink_estimated_mac_data_rate_mbps = 54;
    int sta_measured_uplink_rcpi_dbm_enc = 120;
};
namespace wfa_map {
struct tlvAssociatedStaLinkMetrics {
    int identity;
    Report report;
    bool valid = true;
    int sta_mac() { return identity; }
    std::tuple<bool, Report> bssid_info_list(int) { return {valid, report}; }
};
}
using Metric = wfa_map::tlvAssociatedStaLinkMetrics;
namespace ieee1905_1 {
struct CmduMessageRx {
    std::vector<std::shared_ptr<Metric>> reports;
    template<typename Message> std::vector<std::shared_ptr<Message>> getClassList() {
        return reports;
    }
};
}
struct Database {
    std::map<std::pair<int, int>, std::shared_ptr<Bss>> bsses;
    std::map<int, std::shared_ptr<Station>> stations;
    std::vector<int> link_updates, traffic_updates;
    unsigned queries = 0;
    int queried_agent = 0;
    bool query_success = true, metric_success = true;
    std::shared_ptr<Bss> get_bss(int bssid, int agent) {
        auto found = bsses.find({bssid, agent});
        return found == bsses.end() ? nullptr : found->second;
    }
    std::shared_ptr<Station> get_station(int identity) {
        auto found = stations.find(identity);
        return found == stations.end() ? nullptr : found->second;
    }
    std::string get_sta_parent(const std::string &identity) {
        auto station = get_station(std::stoi(identity));
        return station && station->parent ? std::to_string(station->parent->bssid) : "0";
    }
    bool dm_set_sta_link_metrics(int identity, int, int, int) {
        link_updates.push_back(identity);
        return metric_success;
    }
};
namespace son_actions {
bool send_topology_query_msg(int agent, int, Database &database) {
    database.queries++;
    database.queried_agent = agent;
    return database.query_success;
}
}
struct Controller {
    Database &database;
    int cmdu_tx = 0;
    bool handle_tlv_associated_sta_link_metrics(const sMacAddr &, ieee1905_1::CmduMessageRx &);
    void traffic(int src_mac, const std::vector<std::shared_ptr<Metric>> &reports) {
        for (auto &sta_traffic_stat : reports) {
            TRAFFIC_GUARD
            database.traffic_updates.push_back(sta_traffic_stat->sta_mac());
        }
    }
};
LINK_HANDLER
std::shared_ptr<Metric> metric(int station, int bssid, bool valid = true) {
    return std::make_shared<Metric>(Metric{station, Report{bssid}, valid});
}
int main() {
    Database database;
    auto old_bss = std::make_shared<Bss>(Bss{101});
    auto new_bss = std::make_shared<Bss>(Bss{201});
    database.bsses[{101,10}] = old_bss;
    database.bsses[{201,20}] = new_bss;
    database.stations[11] = std::make_shared<Station>(Station{old_bss});
    database.stations[12] = std::make_shared<Station>(Station{old_bss});
    database.stations[22] = std::make_shared<Station>(Station{new_bss});
    database.stations[44] = std::make_shared<Station>(Station{nullptr});
    Controller controller{database};
    ieee1905_1::CmduMessageRx current{{metric(11,101)}};
    assert(controller.handle_tlv_associated_sta_link_metrics(10, current));
    assert(database.queries == 0 && database.link_updates == std::vector<int>{11});
    ieee1905_1::CmduMessageRx conflict{{metric(11,201), metric(12,201), metric(22,201)}};
    assert(controller.handle_tlv_associated_sta_link_metrics(20, conflict));
    if (database.queries != 1) return 1;
    assert(database.queried_agent == 20);
    assert(database.link_updates == (std::vector<int>{11,22}));
    assert(database.stations.at(11)->parent == old_bss);
    assert(database.stations.at(12)->parent == old_bss);
    ieee1905_1::CmduMessageRx foreign{{metric(11,101), metric(12,201,false)}};
    assert(controller.handle_tlv_associated_sta_link_metrics(20, foreign));
    assert(database.queries == 1 && database.link_updates.size() == 2);
    database.query_success = false;
    assert(!controller.handle_tlv_associated_sta_link_metrics(20, conflict));
    assert(database.queries == 2);
    database.metric_success = false;
    assert(!controller.handle_tlv_associated_sta_link_metrics(10, current));
    controller.traffic(20, {metric(11,201),metric(22,201),metric(33,201),metric(44,201)});
    assert(database.traffic_updates == std::vector<int>{22});
    controller.traffic(10, {metric(11,101),metric(22,101)});
    assert(database.traffic_updates == (std::vector<int>{22,11}));
}
'''.replace("LINK_HANDLER", handler).replace("TRAFFIC_GUARD", traffic)
    cpp = tmp_path / "controller.cpp"
    cpp.write_text(program)
    binary = tmp_path / "controller"
    subprocess.run([compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(binary)], timeout=5)
    assert result.returncode == (0 if recovery_enabled else 1)


def test_owner_guards_cover_optional_station_reports():
    source = native_fragments()
    assert "if (!database.get_bss(metrics.bssid, src_mac))" in source
    assert source.count("if (!parent_bss || !database.get_bss(parent_bss->bssid, src_mac))") == 2
    assert "database.add_station(" not in source
    assert "database.set_station_bss(" not in source
