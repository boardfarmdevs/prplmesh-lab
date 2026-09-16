from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "patches/prplmesh/0025-native-controller-backhaul-roaming.patch"


def added_source(relative, include_context=False):
    patch = PATCH_PATH.read_text()
    section = patch.split(f"+++ b/{relative}\n", 1)[1].split("--- a/", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines()
                     if (line.startswith("+") or (include_context and line.startswith(" ")))
                     and not line.startswith("+++"))


def test_native_reconnect_requires_positive_controller_contact_after_link_up(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native connectivity regression")
    branch = added_source("agent/src/beerocks/slave/tasks/controller_connectivity_task.cpp")
    receiver = added_source("agent/src/beerocks/slave/son_slave_thread.cpp", True)
    contact = receiver[receiver.index("if (db->controller_info.bridge_mac !="):]
    contact = contact[:contact.index("\n        }") + len("\n        }")]
    source = r'''
#include <cassert>
#include <chrono>
#include <sstream>
using Clock = std::chrono::steady_clock;
enum class State { WAIT_FOR_CONTROLLER_DISCOVERY, CONTROLLER_MONITORING, CONNECTION_TIMEOUT };
struct Database {
    struct Controller { int bridge_mac = 0; Clock::time_point last_controller_contact_time; } controller_info;
} database;
struct AgentDB {
    struct SafeDB { Database *operator->() { return &database; } };
    static SafeDB get() { return {}; }
};
namespace network_utils { constexpr int ZERO_MAC = 0; }
#define LOG(level) std::ostringstream()
#define FSM_MOVE_STATE(next) state = State::next
void receive(int src_mac) {
    auto db = AgentDB::get();
CONTACT
}
void tick(State &state, Clock::time_point m_backhaul_connected_time, bool timeout) {
    switch (state) {
    case State::WAIT_FOR_CONTROLLER_DISCOVERY: {
BRANCH
        if (timeout) state = State::CONNECTION_TIMEOUT;
        break;
    }
    default: break;
    }
}
int main() {
    const auto link_up = Clock::now();
    const auto fresh = link_up + std::chrono::seconds(1);
    auto state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    database.controller_info = {0, fresh};
    tick(state, link_up, true);
    assert(state == State::CONNECTION_TIMEOUT);
    state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    database.controller_info = {1, link_up - std::chrono::seconds(1)};
    tick(state, link_up, false);
    assert(state == State::WAIT_FOR_CONTROLLER_DISCOVERY);
    database.controller_info.last_controller_contact_time = link_up;
    tick(state, link_up, true);
    assert(state == State::CONNECTION_TIMEOUT);
    state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    database.controller_info.last_controller_contact_time = fresh;
    tick(state, link_up, true);
    assert(state == State::CONTROLLER_MONITORING);
    tick(state, link_up, true);
    assert(state == State::CONTROLLER_MONITORING);
    state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    tick(state, fresh + std::chrono::seconds(1), true);
    assert(state == State::CONNECTION_TIMEOUT);
    database.controller_info = {0, Clock::time_point{}};
    receive(0);
    assert(database.controller_info.last_controller_contact_time == Clock::time_point{});
    database.controller_info.bridge_mac = 1;
    receive(2);
    assert(database.controller_info.last_controller_contact_time == Clock::time_point{});
    state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    tick(state, link_up, true);
    assert(state == State::CONNECTION_TIMEOUT);
    receive(1);
    assert(database.controller_info.last_controller_contact_time > link_up);
    state = State::WAIT_FOR_CONTROLLER_DISCOVERY;
    tick(state, link_up, true);
    assert(state == State::CONTROLLER_MONITORING);
}
'''.replace("BRANCH", branch).replace("CONTACT", contact)
    program = tmp_path / "connectivity.cpp"
    program.write_text(source)
    binary = tmp_path / "connectivity"
    subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(program), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_native_topology_query_recovery_requires_fresh_same_owner_proof(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native query regression")
    header = added_source("controller/src/beerocks/master/db/topology_query_tracker.h")
    (tmp_path / "query.h").write_text(header)
    source = r'''
#include "query.h"
#include <cassert>
using son::TopologyQueryTracker;
int main() {
    using Clock = TopologyQueryTracker::Clock;
    const auto event = Clock::now();
    const auto query = event + std::chrono::seconds(1);
    const auto now = query + std::chrono::seconds(1);
    const auto absent = TopologyQueryTracker::Time::min();
    TopologyQueryTracker tracker, other_agent;
    const auto mid = tracker.next_mid();
    assert(mid && mid != tracker.next_mid());
    assert(tracker.consume(mid, now) == absent);
    tracker.sent(mid, query);
    assert(other_agent.consume(mid, now) == absent);
    assert(tracker.consume(mid + 1, now) == absent);
    const auto proof = tracker.consume(mid, now);
    assert(proof == query && tracker.consume(mid, now) == absent);
    assert(tracker.restores_same_owner(true, true, true, event, proof, now));
    assert(!tracker.restores_same_owner(true, true, false, event, proof, now));
    assert(!tracker.restores_same_owner(false, true, true, event, proof, now));
    assert(!tracker.restores_same_owner(true, false, true, event, proof, now));
    assert(!tracker.restores_same_owner(true, true, true, query, proof, now));
    assert(!tracker.restores_same_owner(true, true, true, now, proof, now));
    assert(!tracker.restores_same_owner(true, true, true, event, absent, now));
    assert(!tracker.restores_same_owner(true, true, true, event, proof, event));
    assert(!tracker.restores_same_owner(true, true, true, event, proof, now + std::chrono::seconds(5)));
    son::AssociationRecoveryState authority;
    assert(!authority.may_restore());
    authority.infrastructure_lost();
    assert(authority.may_restore());
    authority.associated();
    assert(!authority.may_restore());
    authority.client_departed();
    authority.infrastructure_lost();
    assert(!authority.may_restore());
    authority.associated();
    authority.infrastructure_lost();
    assert(authority.may_restore());
    authority.client_departed();
    assert(!authority.may_restore());
    tracker.sent(mid, query);
    assert(tracker.consume(mid, query + std::chrono::seconds(6)) == absent);
    tracker.sent(mid, query);
    assert(tracker.consume(mid, event) == absent);
    tracker.sent(0, query);
    assert(tracker.consume(0, now) == absent);
    for (uint16_t sequence = 1; sequence <= 17; ++sequence) tracker.sent(sequence, query);
    assert(tracker.consume(1, now) == absent);
    assert(tracker.consume(2, now) == query);
    for (unsigned sequence = 0; sequence < 65536; ++sequence) assert(tracker.next_mid() != 0);
}
'''
    (tmp_path / "query.cpp").write_text(source)
    binary = tmp_path / "query"
    subprocess.run([compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "query.cpp"), "-o", str(binary)], check=True,
                   capture_output=True, text=True)
    subprocess.run([str(binary)], check=True, timeout=5)
    sender = added_source("controller/src/beerocks/master/son_actions.cpp", True)
    handler = added_source("controller/src/beerocks/master/tasks/topology_task.cpp", True)
    assert "cmdu_tx.create(mid, ieee1905_1::eMessageType::TOPOLOGY_QUERY_MESSAGE)" in sender
    assert sender.index("if (!send_cmdu_to_agent") < sender.index("topology_queries.sent")
    assert "src_mac == al_mac" in handler and "topology_queries.consume" in handler
    assert "station->parent_mac == tlvf::mac_to_string(connected.second)" in handler
    assert "station->state != beerocks::STATE_CONNECTED || station->dm_path.empty()" in handler
    assert "station->association_recovery.may_restore()" in handler
    assert "client->association_recovery.client_departed()" in handler
    assert "client->association_recovery.associated()" in handler
    database = added_source("controller/src/beerocks/master/db/db.cpp", True)
    assert "station.association_recovery.infrastructure_lost()" in database
    assert "entry.second->association_recovery.infrastructure_lost()" in database
    assert "association_times.at(connected.first) <= station->association_event_time &&" in handler
    assert "station->association_event_time = restored ? now : association_times.at(connected.first)" in handler


def test_native_policy_executes_hysteresis_path_safety_and_retry_limits(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native policy regression")
    header = added_source("controller/src/beerocks/master/tasks/backhaul_roaming_policy.h")
    (tmp_path / "policy.h").write_text(header)
    source = r'''
#include "policy.h"
#include <cassert>
using namespace son;
int main() {
    BackhaulRoamingPolicy::Nodes nodes{
        {"root", {"", true, true, -128, -1}},
        {"relay", {"root", false, true, -82, 10000}},
        {"mover", {"root", false, true, -84, 10000}},
        {"child", {"mover", false, true, -60, 10000}}
    };
    const std::vector<BackhaulRoamingCandidate> choices{
        {"relay-bss", "relay", -69, 36}, {"child-bss", "child", -40, 36},
        {"self-bss", "mover", -20, 36}, {"unknown-bss", "unknown", -30, 36}
    };
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid == "relay-bss");
    nodes["relay"].rssi = -85;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["relay"].rssi = -84;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["relay"].rssi = -82;
    nodes["relay"].connected = false;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["relay"].connected = true;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 26000).bssid.empty());
    nodes["relay"].parent = "child";
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["relay"].parent = "relay";
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["relay"].parent = "root";
    nodes["mover"].rssi = -74;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    nodes["mover"].rssi = -84;
    nodes["relay"].observed_ms = 11000;
    assert(BackhaulRoamingPolicy::select(nodes, "mover", choices, 10000).bssid.empty());
    BackhaulRoamingPolicy policy;
    assert(!policy.observe("mover", "old", "new", 0));
    assert(!policy.observe("mover", "old", "new", 5000));
    assert(policy.observe("mover", "old", "new", 10000));
    assert(!policy.observe("mover", "old", "", 11000));
    assert(!policy.observe("mover", "old", "new", 12000));
    assert(policy.observe("mover", "old", "new", 17000));
    policy.completed("mover", "new", false, 17000);
    assert(!policy.observe("mover", "old", "new", 18000));
    assert(!policy.observe("mover", "old", "new", 22000));
    assert(!policy.observe("mover", "old", "new", 33000));
    assert(policy.observe("mover", "old", "new", 38000));
    policy.completed("mover", "new", false, 38000);
    for (int64_t now = 43000; now < 78000; now += 5000) {
        assert(!policy.observe("mover", "old", "new", now));
    }
    assert(policy.observe("mover", "old", "new", 78000));
    policy.completed("mover", "new", false, 78000);
    for (int64_t now = 83000; now < 200000; now += 5000) {
        assert(!policy.observe("mover", "old", "new", now));
    }
    policy.completed("mover", "new", true, 200000);
    assert(!policy.observe("mover", "new", "old", 200001));
    assert(!policy.observe("mover", "new", "old", 205000));
    assert(!policy.observe("mover", "new", "old", 210000));
    assert(!policy.observe("mover", "new", "old", 215000));
    assert(policy.observe("mover", "new", "old", 220000));
    BackhaulRoamingReservation reservation;
    assert(!reservation.timed_out(20000) && !reservation.retry_due(100000));
    reservation.sent(0);
    assert(!reservation.timed_out(14999) && reservation.timed_out(15000));
    assert(!reservation.retry_due(34999) && reservation.retry_due(35000));
    assert(reservation.attempts == 1);
    reservation.sent(35000);
    assert(!reservation.retry_due(69999) && reservation.retry_due(70000));
    reservation.sent(70000);
    assert(reservation.timed_out(85000) && !reservation.retry_due(200000));
    assert(reservation.attempts == 3);
    assert(BackhaulRoamingReservation::settled("target", "target", 17, 0, "", 0, 0));
    assert(BackhaulRoamingReservation::settled("target", "recovered-root", 17, 17, "target", 1, 2));
    assert(!BackhaulRoamingReservation::settled("target", "recovered-root", 17, 16, "target", 1, 2));
    assert(!BackhaulRoamingReservation::settled("target", "recovered-root", 17, 17, "other-target", 1, 2));
    assert(!BackhaulRoamingReservation::settled("target", "recovered-root", 17, 0, "", 1, 2));
    assert(!BackhaulRoamingReservation::settled("target", "recovered-root", 17, 17, "target", 2, 2));
    assert(BackhaulRoamingReservation::settled("target", "recovered-root", 17, 17, "target", UINT32_MAX, 0));
}
'''
    (tmp_path / "policy.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "policy.cpp"), "-o", str(tmp_path / "policy")], check=True)
    subprocess.run([str(tmp_path / "policy")], check=True)


def test_native_receiver_only_and_controller_1905_actuation():
    patch = PATCH_PATH.read_text()
    assert '"SCAN TYPE=ONLY freq="' in patch
    assert '"BSS " + tlvf::mac_to_string(entry.bssid)' in patch
    assert "age >= 0 && age <= 2" in patch
    assert "response->sequence() != observation.sequence" in patch
    assert "BACKHAUL_STEERING_REQUEST_MESSAGE" in patch
    assert "son_actions::send_cmdu_to_agent(tlvf::mac_from_string(source)" in patch
    assert "response->backhaul_station_mac()" in patch
    assert "found->second.observed_ms > moving_started_ms" in patch
    assert "retaining topology reservation until native target is observed" in patch
    assert "retaining reservation for late native completion" in patch
    assert "db->backhaul.backhaul_bssid = bssid;" in patch
    assert "son_actions::send_topology_query_msg(source, transmit, database);" in patch
    assert "[this, bssid]" in patch
    assert "+                    database.get_radio_by_backhaul_cap(iface_mac);" in patch
    additions = "\n".join(line for line in patch.splitlines() if line.startswith("+"))
    for forbidden in ("backhaul-parent-handover", "wmediumd", "world.json", "system(", "popen(",
                      "SET_NETWORK", "bgscan", "02:00:"):
        assert forbidden not in additions
    task = added_source("controller/src/beerocks/master/tasks/backhaul_roaming_task.cpp")
    assert "complete(false" not in task
    assert "!moving_agent.empty()" in task
    assert "parent_bssid == moving_original" in task
    assert "found->second.station == moving_station && found->second.radio == moving_radio" in task
    assert "issue_steering(moving_agent, moving_target, now_ms)" in task
    assert re.search(r"BackhaulRoamingReservation::settled\(\s*moving_target", task)
    assert "completed_then_recovered agent=" in task
    assert re.search(r"m_completed_steering_mid\s*=\s*m_backhaul_steering_mid;", patch)
    assert "response->completed_steering_target()" in patch
    assert "++m_completed_steering_generation;" in patch
    assert "moving_completion_generation" in task
    rediscovery = task.split("if (!agent->backhaul.wireless_backhaul_radio ||", 1)[1].split("continue;", 1)[0]
    assert "BACKHAUL_STA_CAPABILITY_QUERY_MESSAGE" in rediscovery
    assert "son_actions::send_topology_query_msg(agent->al_mac" in rediscovery
    assert "now_ms + 5000" in rediscovery


def test_native_recovery_rejects_local_children_and_known_descendants(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native recovery regression")
    header = added_source("agent/src/beerocks/slave/backhaul_manager/backhaul_roaming_guard.h")
    (tmp_path / "guard.h").write_text(header)
    source = r'''
#include "guard.h"
#include <cassert>
using namespace beerocks;
int main() {
    BackhaulRecoveryGuard::Peers peers{
        {"root-bss", {"root", "", "", true}},
        {"own-bss", {"self", "root", "own-sta", false}},
        {"child-bss", {"child", "root", "child-sta", false}},
        {"grandchild-bss", {"grandchild", "child", "grandchild-sta", false}},
        {"peer-bss", {"peer", "root", "peer-sta", false}}
    };
    std::set<std::string> children{"child-sta"};
    assert(!BackhaulRecoveryGuard::allowed("self", "own-bss", peers, children));
    assert(!BackhaulRecoveryGuard::allowed("self", "child-bss", peers, children));
    assert(!BackhaulRecoveryGuard::allowed("self", "grandchild-bss", peers, children));
    assert(!BackhaulRecoveryGuard::allowed("self", "unknown-bss", peers, children));
    assert(BackhaulRecoveryGuard::allowed("self", "root-bss", peers, children));
    assert(BackhaulRecoveryGuard::allowed("self", "peer-bss", peers, children));
    peers["child-bss"].parent = "self";
    assert(!BackhaulRecoveryGuard::allowed("self", "grandchild-bss", peers, children));
    children.clear();
    assert(BackhaulRecoveryGuard::allowed("self", "child-bss", peers, children));
    peers["peer-bss"].parent = "peer";
    assert(!BackhaulRecoveryGuard::allowed("self", "peer-bss", peers, children));
}
'''
    (tmp_path / "guard.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "guard.cpp"), "-o", str(tmp_path / "guard")], check=True)
    subprocess.run([str(tmp_path / "guard")], check=True)
    patch = PATCH_PATH.read_text()
    assert "m_roaming_peers.empty()" in patch
    assert "native_backhaul_recovery three native heartbeats unanswered; parent=" in patch
    assert "request->topology_size() > 48" in patch
    assert "radio->associated_clients" in patch


def test_native_recovery_preserves_expected_disconnect_and_reconnect_grace(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native recovery timing regression")
    header = added_source("agent/src/beerocks/slave/backhaul_manager/backhaul_roaming_guard.h")
    (tmp_path / "guard.h").write_text(header)
    source = r'''
#include "guard.h"
#include <cassert>
using namespace beerocks;
auto at(int seconds) {
    return BackhaulRecoveryLease::Clock::time_point{std::chrono::seconds(seconds)};
}
int main() {
    BackhaulRecoveryLease lease;
    assert(!lease.due(at(100)));
    lease.controller_seen(at(100));
    lease.connected(at(100));
    assert(!lease.due(at(115)));
    assert(!lease.due(at(116)));
    assert(lease.probe_due(at(116)));
    lease.probe_sent(1, at(116));
    assert(!lease.probe_due(at(117)) && !lease.due(at(120)));
    assert(!lease.acknowledge(99, at(117)));
    assert(lease.acknowledge(1, at(117)));
    assert(!lease.probe_due(at(132)));
    assert(lease.probe_due(at(133)));
    lease.probe_sent(2, at(133));
    lease.controller_seen(at(134));
    assert(!lease.due(at(1000)));
    assert(!lease.acknowledge(2, at(135)));
    lease.probe_sent(3, at(150));
    lease.probe_sent(4, at(152));
    lease.probe_sent(5, at(154));
    assert(!lease.probe_due(at(156)));
    assert(!lease.due(at(155)) && lease.due(at(156)));
    assert(!lease.acknowledge(3, at(159)));
    lease.started("old-parent", at(156));
    assert(!lease.acknowledge(5, at(157)));
    assert(!lease.consume_disconnect("another-parent", at(157)));
    assert(lease.consume_disconnect("old-parent", at(157)));
    assert(!lease.consume_disconnect("old-parent", at(157)));
    assert(!lease.probe_due(at(171)));
    lease.connected(at(171));
    assert(!lease.probe_due(at(186)));
    assert(lease.probe_due(at(187)));
    lease.started("other-parent", at(190));
    assert(!lease.consume_disconnect("other-parent", at(196)));
    lease.started("other-parent", at(200));
    lease.connected(at(201));
    assert(!lease.consume_disconnect("other-parent", at(202)));
}
'''
    (tmp_path / "lease.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "lease.cpp"), "-o", str(tmp_path / "lease")], check=True)
    subprocess.run([str(tmp_path / "lease")], check=True)
    patch = PATCH_PATH.read_text()
    assert "m_roaming_lease.connected(std::chrono::steady_clock::now())" in patch
    assert "m_roaming_lease.consume_disconnect(tlvf::mac_to_string(notification->bssid)" in patch
    assert "native_backhaul_recovery expected disconnect; continuing scan" in patch
    assert "ieee1905_1::eMessageType::HIGHER_LAYER_DATA_MESSAGE" in patch
    assert "m_roaming_lease.probe_sent(m_roaming_probe_mid, now);" in patch
    assert "m_roaming_lease.acknowledge(cmdu_rx.getMessageId(), now)" in patch
    assert "dst_mac == db->bridge.mac && src_mac == db->controller_info.bridge_mac" in patch


def test_native_scan_publication_brackets_completed_parent_state(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native publication regression")
    additions = added_source("agent/src/beerocks/slave/backhaul_manager/backhaul_manager.cpp", include_context=True)
    function = additions.split("void BackhaulManager::send_roaming_scan_response", 1)[1]
    predicate = re.search(r"valid = valid[\s\S]*?;", function).group(0)
    source = r'''
#include <cassert>
#include <chrono>
#include <string>
#include <vector>
namespace beerocks { namespace net { namespace network_utils { constexpr int ZERO_MAC = 0; } } }
struct Front { int iface_mac = 7; };
struct Radio { Front front; };
struct BackRadio { std::string ssid = "mesh"; };
struct Config { BackRadio back_radio; };
struct Database { Config device_conf; };
struct Hal {
    int status_calls = 0;
    int fail_status_call = 0;
    bool connected = true;
    bool leave_during_read = false;
    bool change_during_read = false;
    std::string parent = "parent";
    bool update_status() { return ++status_calls != fail_status_call; }
    bool is_connected() { return connected; }
    std::string get_bssid() { return parent; }
    bool get_roaming_scan_results(const std::string &ssid, std::vector<int> &) {
        assert(ssid == "mesh");
        if (leave_during_read) connected = false;
        if (change_during_read) parent = "another-parent";
        return true;
    }
};
Radio stored_radio;
Radio *radio = &stored_radio;
Database database;
Database *db = &database;
Hal native_hal;
Hal *active_hal = &native_hal;
int m_roaming_scan_radio = 7;
int m_backhaul_steering_bssid = 0;
std::string m_roaming_scan_bssid = "parent";
auto m_roaming_scan_started = std::chrono::steady_clock::now();
bool sample(bool valid = true) {
    std::vector<int> entries;
''' + predicate + r'''
    return valid;
}
int main() {
    assert(sample() && native_hal.status_calls == 2);
    native_hal = Hal{};
    native_hal.connected = false;
    assert(!sample());
    native_hal = Hal{};
    native_hal.leave_during_read = true;
    assert(!sample());
    native_hal = Hal{};
    native_hal.change_during_read = true;
    assert(!sample());
    native_hal = Hal{};
    native_hal.fail_status_call = 2;
    assert(!sample());
    native_hal = Hal{};
    m_backhaul_steering_bssid = 1;
    assert(!sample());
    m_backhaul_steering_bssid = 0;
    m_roaming_scan_radio = 8;
    assert(!sample());
    m_roaming_scan_radio = 7;
    m_roaming_scan_started -= std::chrono::seconds(4);
    assert(!sample());
}
'''
    (tmp_path / "publication.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "publication.cpp"), "-o", str(tmp_path / "publication")], check=True)
    subprocess.run([str(tmp_path / "publication")], check=True)


def test_hostapd_reports_real_multi_ap_role_without_enabling_wps():
    patch = (ROOT / "patches/hostap/0003-report-multi-ap-role-without-wps.patch").read_text()
    assert '"ssid=%s\\nmulti_ap=%d\\n"' in patch
    assert "+\t\t\t  hapd->conf->multi_ap);" in patch
    assert patch.index('"ssid=%s\\nmulti_ap=%d\\n"') < patch.index("#ifdef CONFIG_WPS")
    assert '-\t\tret = os_snprintf(pos, end - pos, "multi_ap=%d\\n",' in patch


def test_native_roam_updates_only_the_controller_selected_network_target(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native roam regression")
    additions = added_source("common/beerocks/bwl/nl80211/sta_wlan_hal_nl80211.cpp", include_context=True)
    body = re.split(r"auto bssid_str\s*=\s*tlvf::mac_to_string\(bssid\);", additions, maxsplit=1)[1].split("\n}", 1)[0]
    source = r'''
#include <cassert>
#include <sstream>
#include <string>
#include <vector>
#define LOG(level) std::ostringstream()
int m_active_network_id = 7;
std::string m_active_bssid = "old-parent";
std::vector<std::string> calls;
bool pin_ok = true;
bool roam_ok = true;
std::string get_iface_name() { return "native-sta"; }
bool set_network(int network, const std::string &field, const std::string &value) {
    assert(network == 7 && field == "bssid");
    calls.push_back(field + " " + value);
    return pin_ok;
}
bool wpa_ctrl_send_msg(const std::string &command) {
    calls.push_back(command);
    return roam_ok;
}
bool roam(const std::string &bssid_str) {
''' + body + r'''
}
int main() {
    assert(roam("controller-target"));
    assert((calls == std::vector<std::string>{"bssid controller-target", "ROAM controller-target"}));
    assert(m_active_bssid == "old-parent");
    calls.clear();
    pin_ok = false;
    assert(!roam("controller-target"));
    assert((calls == std::vector<std::string>{"bssid controller-target"}));
    calls.clear();
    pin_ok = true;
    roam_ok = false;
    assert(!roam("controller-target"));
    assert((calls == std::vector<std::string>{"bssid controller-target", "ROAM controller-target", "bssid old-parent"}));
    assert(m_active_bssid == "old-parent");
}
'''
    (tmp_path / "roam.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "roam.cpp"), "-o", str(tmp_path / "roam")], check=True)
    subprocess.run([str(tmp_path / "roam")], check=True)


def test_native_fresh_scan_filter_rejects_unknown_or_old_bss_ages(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for native scan freshness regression")
    additions = added_source("common/beerocks/bwl/nl80211/sta_wlan_hal_nl80211.cpp", include_context=True)
    function = additions.split("bool sta_wlan_hal_nl80211::get_roaming_scan_results", 1)[1]
    begin = function.index("{")
    depth = 0
    end = begin
    for index, character in enumerate(function[begin:], begin):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    body = function[begin:end]
    source = r'''
#include <cassert>
#include <map>
#include <sstream>
#include <string>
#include <vector>
struct sScanResult { std::string bssid; int rssi; };
namespace tlvf {
std::string mac_to_string(const std::string &address) { return address; }
}
std::vector<sScanResult> scan;
std::map<std::string, std::string> details;
int get_scan_results(const std::string &ssid, std::vector<sScanResult> &output) {
    assert(ssid == "test-network");
    output = scan;
    return scan.size();
}
bool wpa_ctrl_send_msg(const std::string &command, char **reply) {
    assert(command.compare(0, 4, "BSS ") == 0);
    auto found = details.find(command.substr(4));
    if (found == details.end()) return false;
    *reply = const_cast<char *>(found->second.c_str());
    return true;
}
bool fresh(const std::string &ssid, std::vector<sScanResult> &results)
''' + body + r'''
int main() {
    scan = {{"fresh", -69}, {"limit", -75}, {"old", -55}, {"missing", -45},
            {"malformed", -25}, {"negative", -30}, {"unknown", -20}};
    details = {{"fresh", "id=1\nage=0\n"}, {"limit", "age=2\n"},
               {"old", "age=3\n"}, {"missing", "id=4\n"},
               {"malformed", "age=1junk\n"}, {"negative", "age=-1\n"}};
    std::vector<sScanResult> results;
    assert(fresh("test-network", results));
    assert(results.size() == 2 && results[0].rssi == -69 && results[1].rssi == -75);
    details.clear();
    assert(!fresh("test-network", results) && results.empty());
    scan.resize(65, {"fresh", -69});
    assert(!fresh("test-network", results) && results.empty());
    scan.clear();
    assert(!fresh("test-network", results) && results.empty());
}
'''
    (tmp_path / "fresh.cpp").write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(tmp_path / "fresh.cpp"), "-o", str(tmp_path / "fresh")], check=True)
    subprocess.run([str(tmp_path / "fresh")], check=True)
