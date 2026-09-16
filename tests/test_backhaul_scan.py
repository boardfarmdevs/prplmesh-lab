from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "patches/prplmesh/0024-nl80211-backhaul-scan-results.patch").read_text()


def test_native_scan_is_triggered_and_only_unfiltered_busy_scans_are_coalesced():
    assert '+    return wpa_ctrl_send_msg("SCAN TYPE=ONLY");' in PATCH
    assert '+    if (cmd == "SCAN TYPE=ONLY" && !strncmp(buffer, "FAIL-BUSY", 9)) {' in PATCH
    assert '     if ((!strncmp(buffer, "FAIL", 4)) || (!strncmp(buffer, "UNKNOWN", 7))) {' in PATCH


def test_actual_native_scan_parser_without_exceptions(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for the native scan parser regression")
    section = PATCH.split("int sta_wlan_hal_nl80211::get_scan_results", 1)[1].split(
        "--- a/common/beerocks/bwl/nl80211/base_", 1)[0]
    body = "\n".join(line[1:] for line in section.splitlines() if line.startswith("+"))
    source = r'''
#include <array>
#include <cassert>
#include <regex>
#include <sstream>
#include <string>
#include <vector>
namespace beerocks {
enum class eFreqType { FREQ_AUTO, FREQ_24G, FREQ_5G, FREQ_6G };
namespace net { namespace network_utils {
const std::string ZERO_MAC = "00:00:00:00:00:00";
}}
}
namespace tlvf {
std::string mac_from_string(const std::string &value) { return value; }
}
namespace son { namespace wireless_utils {
int freq_to_channel(int frequency) {
    if (frequency == 2437) return 6;
    if (frequency == 5180) return 36;
    if (frequency == 5975) return 5;
    return 0;
}
beerocks::eFreqType which_freq_type(int frequency) {
    if (frequency == 2437) return beerocks::eFreqType::FREQ_24G;
    if (frequency == 5180) return beerocks::eFreqType::FREQ_5G;
    if (frequency == 5975) return beerocks::eFreqType::FREQ_6G;
    return beerocks::eFreqType::FREQ_AUTO;
}
}}
struct sScanResult {
    std::string bssid;
    int channel = 0;
    beerocks::eFreqType freq_type = beerocks::eFreqType::FREQ_AUTO;
    int rssi = 0;
};
std::string response;
bool success = true;
bool wpa_ctrl_send_msg(const std::string &command, char **reply) {
    assert(command == "SCAN_RESULTS");
    *reply = const_cast<char *>(response.c_str());
    return success;
}
int parse(const std::string &ssid, std::vector<sScanResult> &list) {
''' + body + r'''
}
int main() {
    const std::string valid = "02:00:00:00:04:02\t5180\t-78\t[WPA2-PSK-CCMP][ESS]\tmesh_backhaul\n";
    response = "bssid / frequency / signal level / flags / ssid\n" + valid +
        "02:00:00:00:0d:02\t2437\t-42\t[ESS]\tmesh_backhaul\n" +
        "02:00:00:00:0e:02\t5975\t-51\t[ESS]\tmesh_backhaul\n" +
        "02:00:00:00:01:01\t5180\t-30\t[ESS]\tprivate_ssid\n";
    std::vector<sScanResult> list(1);
    assert(parse("mesh_backhaul", list) == 3 && list.size() == 3);
    assert(list[0].channel == 36 && list[0].rssi == -78);
    assert(list[1].freq_type == beerocks::eFreqType::FREQ_24G);
    assert(list[2].freq_type == beerocks::eFreqType::FREQ_6G);
    response = "invalid\t5180\t-1\t[ESS]\tmesh_backhaul\n"
        "00:00:00:00:00:00\t5180\t-1\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t5180junk\t-1\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t99999999999999999999999\t-1\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t5180\t-128\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t5180\t1\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t123\t-1\t[ESS]\tmesh_backhaul\n"
        "02:00:00:00:04:02\t5180\t-1\t[IBSS]\tmesh_backhaul\n"
        "truncated";
    assert(parse("mesh_backhaul", list) == 0 && list.empty());
    response = "02:00:00:00:04:02\t5180\t-1\t[ESS]\tmesh with spaces\n";
    assert(parse("mesh with spaces", list) == 1);
    response.clear();
    for (int count = 0; count < 300; ++count) response += valid;
    assert(parse("mesh_backhaul", list) == 256);
    success = false;
    assert(parse("mesh_backhaul", list) == 0 && list.empty());
}
'''
    source_file = tmp_path / "scan.cpp"
    executable = tmp_path / "scan"
    source_file.write_text(source)
    subprocess.run([compiler, "-std=c++14", "-fno-exceptions", "-Wall", "-Wextra", "-Werror",
                    str(source_file), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
