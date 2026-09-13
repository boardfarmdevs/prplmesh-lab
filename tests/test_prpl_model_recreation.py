from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0017-controller-reconcile-recreated-agent-model.patch"


def fragments():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    return "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                     if line.startswith(("+", " ")) and not line.startswith("+++"))


@pytest.mark.parametrize("repair_enabled", [True, False])
def test_native_model_recreation(tmp_path, repair_enabled):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native recovery fragments")
    source = fragments()
    removal = source[source.index("    if (!dm_remove_device_element(mac))"):
                     source.index("        const auto expected_prefix")]
    removal = removal[:removal.index("    return true;") + len("    return true;")]
    repair = source[source.index("    const auto sta_prefix"):
                    source.index('    LOG(DEBUG) << "Setting byte counter')]
    channel = source[source.index("            bool has_current_channel"):
                     source.index("            radio->bsses.keep_new_prepare();")]
    if not repair_enabled:
        repair = ""
    program = r'''
#include <cassert>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
struct Bss;
struct Station {
    std::string dm_path;
    std::weak_ptr<Bss> owner;
    bool backhaul = false;
    unsigned associations = 0;
    bool is_bSta() { return backhaul; }
    std::shared_ptr<Bss> get_bss() { return owner.lock(); }
};
struct Bss {
    std::string dm_path;
    std::unordered_map<int, std::shared_ptr<Station>> connected_stations;
};
struct Agent { std::string dm_path; };
struct Database {
    std::unordered_map<int, std::shared_ptr<Agent>> m_agents;
    std::unordered_map<int, std::shared_ptr<Station>> m_stations;
    bool remove_success = true, add_success = true;
    bool dm_remove_device_element(int) { return remove_success; }
    bool dm_add_sta_element(int, int, Station &station) {
        station.dm_path = station.get_bss()->dm_path + ".STA.100";
        station.associations++;
        return add_success;
    }
    bool remove(int mac) {
        auto agent = m_agents.at(mac);
        REMOVAL
    }
    bool publish(std::shared_ptr<Bss> bss) {
        bool ret_val = true;
        int al_mac = 1, bssid = 1;
        (void)bss; (void)al_mac; (void)bssid;
        REPAIR
        return ret_val;
    }
};
struct Profile { int op_class, channel; };
struct Radio { std::vector<Profile> current_operating_class_profile; };
bool missing_channels(const std::vector<Radio *> &radios) {
    bool needs_operating_channel_report = false;
    for (auto radio : radios) {
        CHANNEL
    }
    return needs_operating_channel_report;
}
int main() {
    Database database;
    auto bss = std::make_shared<Bss>();
    bss->dm_path = "Device.6.Radio.3.BSS.1";
    auto other = std::make_shared<Bss>();
    other->dm_path = "Device.7.Radio.3.BSS.1";
    const std::vector<std::string> paths = {
        "Device.5.Radio.3.BSS.1.STA.1", "", "Device.6.Radio.3.BSS.11.STA.1",
        "Device.6.Radio.3.BSS.1.STA.12", "Device.7.Radio.3.BSS.1.STA.1", ""
    };
    for (unsigned index = 0; index < paths.size(); index++) {
        auto station = std::make_shared<Station>();
        station->dm_path = paths[index];
        station->owner = index == 4 ? other : bss;
        station->backhaul = index == 5;
        bss->connected_stations[index] = station;
    }
    assert(database.publish(bss));
    for (int index = 0; index < 3; index++) {
        auto station = bss->connected_stations.at(index);
        if (station->dm_path != bss->dm_path + ".STA.100") return 1;
        assert(station->associations == 1);
    }
    assert(database.publish(bss));
    for (int index = 0; index < 3; index++) assert(bss->connected_stations.at(index)->associations == 1);
    for (int index = 3; index < 6; index++) {
        assert(bss->connected_stations.at(index)->associations == 0);
        assert(bss->connected_stations.at(index)->dm_path == paths[index]);
    }
    bss->connected_stations.at(0)->dm_path.clear();
    database.add_success = false;
    assert(!database.publish(bss));
    auto agent = std::make_shared<Agent>();
    agent->dm_path = "Device.5";
    database.m_agents[5] = agent;
    for (int identity : {5, 50, 6}) {
        auto station = std::make_shared<Station>();
        station->dm_path = "Device." + std::to_string(identity) + ".Radio.3.BSS.1.STA.1";
        database.m_stations[identity] = station;
    }
    database.remove_success = false;
    assert(!database.remove(5));
    assert(database.m_agents.count(5) && !database.m_stations.at(5)->dm_path.empty());
    database.remove_success = true;
    assert(database.remove(5));
    assert(!database.m_agents.count(5) && database.m_stations.at(5)->dm_path.empty());
    assert(!database.m_stations.at(50)->dm_path.empty() && !database.m_stations.at(6)->dm_path.empty());
    Radio known{{{0,0}, {131,5}}}, missing{{{0,0}, {0,0}}}, malformed{{{131,0}}};
    assert(!missing_channels({&known}));
    assert(missing_channels({&known, &missing}));
    assert(missing_channels({&malformed}));
    assert(missing.current_operating_class_profile[0].op_class == 0);
}
'''.replace("REMOVAL", removal).replace("REPAIR", repair).replace("CHANNEL", channel)
    cpp = tmp_path / "model.cpp"
    cpp.write_text(program)
    binary = tmp_path / "model"
    subprocess.run([compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(binary)], timeout=5)
    assert result.returncode == (0 if repair_enabled else 1)


def test_native_channel_recovery_uses_report_not_synthetic_values():
    source = fragments()
    request = source[source.index("    if (needs_operating_channel_report)"):]
    assert request.count("cmdu_tx.create(") == 1
    assert "CHANNEL_SELECTION_REQUEST_MESSAGE" in request
    assert "send_cmdu_to_agent(al_mac, cmdu_tx, database)" in request
    assert "handle_current_op_class(" not in request
    assert "set_radio_wifi_channel(" not in request
