#!/usr/bin/env python3
import argparse
import subprocess
import tempfile
from pathlib import Path


parser = argparse.ArgumentParser(description="Compile the native timer and reject unsolicited candidate resets")
parser.add_argument("source", type=Path)
args = parser.parse_args()
source = args.source.read_text()
start = source.index("void LinkMetricsTask::work()")
end = source.index("void LinkMetricsTask::handle_event(", start)
harness = r'''
#include <cassert>
#include <chrono>
#include <iostream>
#include <memory>
#include <vector>
#define LOG(level) std::cerr
namespace ieee1905_1 {
enum class eMessageType { LINK_METRIC_QUERY_MESSAGE, UNASSOCIATED_STA_LINK_METRICS_QUERY_MESSAGE };
constexpr int BOTH_TX_AND_RX_LINK_METRICS = 3;
struct tlvLinkMetricQueryAllNeighbors {
    int value = 0;
    int &link_metrics_type() { return value; }
};
}
namespace wfa_map { struct tlvUnassociatedStaLinkMetricsQuery {}; }
struct Agent { int al_mac = 1; };
struct Database {
    struct { std::chrono::seconds link_metrics_request_interval_seconds{1}; } config;
    std::vector<std::shared_ptr<Agent>> agents{5, std::make_shared<Agent>()};
    const auto &get_all_connected_agents() { return agents; }
};
struct Message {
    ieee1905_1::eMessageType type;
    std::vector<ieee1905_1::eMessageType> sent;
    bool create(int, ieee1905_1::eMessageType value) { type = value; return true; }
    template<class Class> auto addClass() { return std::make_shared<Class>(); }
};
namespace son_actions {
void send_cmdu_to_agent(int, Message &message, Database &) { message.sent.push_back(message.type); }
}
struct LinkMetricsTask {
    Database database;
    Message cmdu_tx;
    std::chrono::steady_clock::time_point last_query_request;
    void work();
};
'''
harness += source[start:end]
harness += r'''
int main() {
    LinkMetricsTask task;
    task.last_query_request = std::chrono::steady_clock::now() - std::chrono::seconds(3);
    task.work();
    assert(task.cmdu_tx.sent.size() == 5);
    for (auto type : task.cmdu_tx.sent) {
        assert(type == ieee1905_1::eMessageType::LINK_METRIC_QUERY_MESSAGE);
    }
    task.work();
    assert(task.cmdu_tx.sent.size() == 5);
    task.database.config.link_metrics_request_interval_seconds = std::chrono::seconds(0);
    task.last_query_request -= std::chrono::seconds(3);
    task.work();
    assert(task.cmdu_tx.sent.size() == 5);
    std::cout << "PASS native timer preserves neighbor queries without clearing candidate registrations\n";
}
'''
with tempfile.TemporaryDirectory(prefix="prpl-link-timer-") as directory:
    root = Path(directory)
    translation_unit = root / "test.cpp"
    binary = root / "test"
    translation_unit.write_text(harness)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(translation_unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
assert "UNASSOCIATED_STA_LINK_METRICS_QUERY_MESSAGE" in source[end:]
