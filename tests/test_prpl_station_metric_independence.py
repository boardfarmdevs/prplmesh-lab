from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0016-agent-preserve-station-metrics-without-channel-load.patch"


def native_fragments():
    block = PATCH.read_text().split("--- a/agent/src/beerocks/slave/tasks/link_metrics_collection_task.cpp\n")[1]
    block = block.split("--- a/")[0]
    lines = []
    in_hunk = False
    for line in block.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith(("+", " ")):
            lines.append(line[1:])
    source = "\n".join(lines)
    union = source[source.index("    std::unordered_map<sMacAddr,"):source.index("    for (const auto &entry : bss_metrics)")]
    values = source[source.index("        sApMetrics metric{}"):source.index("        // Check the BSSID")]
    serialization = source[source.index("        if (response.metric.available)"):source.index("        auto ap_extended_metrics_tlv = m_cmdu_tx.addClass")]
    return union, values, serialization


@pytest.mark.parametrize("include_unqualified", [True, False])
def test_native_bss_union_and_optional_load_serialization(tmp_path, include_unqualified):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native aggregation fragments")
    union, values, serialization = native_fragments()
    if not include_unqualified:
        union = union[:union.index("    for (const auto &metrics : ap_extended_metrics_tlv_list)")]
    source = tmp_path / "metrics.cpp"
    source.write_text("""#include <algorithm>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#define LOG(level) std::cerr
using sMacAddr = std::string;
namespace wfa_map {
struct tlvApMetrics {
    std::string identity;
    uint8_t load = 0;
    uint16_t stations = 1;
    int service = 0;
    std::vector<uint8_t> information;
    tlvApMetrics(std::string address = "", uint8_t utilization = 0) : identity(address), load(utilization) {}
    std::string &bssid() { return identity; }
    uint8_t &channel_utilization() { return load; }
    uint16_t &number_of_stas_currently_associated() { return stations; }
    int &estimated_service_parameters() { return service; }
    size_t estimated_service_info_field_length() { return information.size(); }
    uint8_t *estimated_service_info_field() { return information.data(); }
    bool alloc_estimated_service_info_field(size_t size) { information.resize(size); return true; }
};
}
struct sApMetrics {
    sMacAddr bssid;
    bool available = false;
    uint8_t channel_utilization = 0;
    uint16_t number_of_stas_currently_associated = 0;
    int estimated_service_parameters = 0;
    std::vector<uint8_t> estimated_service_info_field;
};
struct Message {
    std::vector<std::shared_ptr<wfa_map::tlvApMetrics>> emitted;
    template<class Type> std::shared_ptr<Type> addClass() {
        auto result = std::make_shared<Type>();
        emitted.push_back(result);
        return result;
    }
};
int main() {
    auto zero = std::make_shared<wfa_map::tlvApMetrics>("zero", 0);
    auto full = std::make_shared<wfa_map::tlvApMetrics>("full", 255);
    auto unknown = std::make_shared<wfa_map::tlvApMetrics>("unknown", 0);
    std::vector<std::shared_ptr<wfa_map::tlvApMetrics>> ap_metrics_tlv_list = {zero, full, nullptr};
    std::vector<std::shared_ptr<wfa_map::tlvApMetrics>> ap_extended_metrics_tlv_list = {zero, full, unknown, nullptr};
""" + union + """
    if (bss_metrics.size() != 3) return 1;
    Message m_cmdu_tx;
    size_t unavailable_bsses = 0;
    for (const auto &entry : bss_metrics) {
        const auto &bssid_tlv = entry.first;
        const auto &ap_metrics_tlv = entry.second;
""" + values + """
        if (!metric.available) {
            if (metric.bssid != "unknown") return 2;
            unavailable_bsses++;
        }
        struct { sApMetrics metric; } response{metric};
        auto serialize = [&]() {
""" + serialization + """
        };
        serialize();
    }
    if (unavailable_bsses != 1 || m_cmdu_tx.emitted.size() != 2) return 3;
    for (const auto &metrics : m_cmdu_tx.emitted) {
        if (metrics->identity == "zero" && metrics->load != 0) return 4;
        if (metrics->identity == "full" && metrics->load != 255) return 5;
        if (metrics->identity == "unknown") return 6;
    }
    return 0;
}
""")
    binary = tmp_path / "metrics"
    subprocess.run([compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(binary)], timeout=5)
    assert result.returncode == (0 if include_unqualified else 1)


def test_unavailable_load_does_not_suppress_independent_station_tlvs():
    _, _, serialization = native_fragments()
    assert "tlvAssociatedStaLinkMetrics" not in serialization
    assert "tlvApExtendedMetrics" not in serialization
    initial = (ROOT / "patches/prplmesh/0014-qualified-channel-utilization.patch").read_text()
    monitor = initial.split("--- a/agent/src/beerocks/fronthaul_manager/monitor/monitor_stats.cpp")[1]
    assert "+    if (!mon_wlan_hal->channel_utilization_available()) {\n+        return true;" in monitor
