from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "patches/prplmesh/0023-linux-backhaul-recovery-credentials.patch").read_text()


def test_provisioning_uses_the_supplicant_credentials_before_native_start():
    script = (ROOT / "scripts/container/setup-nl80211-node.sh").read_text()
    assert 'backhaul_template="$project/manifests/wpa_backhaul.conf"' in script
    assert 'backhaul_ssid=$(sed' in script
    assert 'backhaul_passphrase=$(sed' in script
    assert "backhaul_security=WPA2-Personal" in script
    assert script.index("backhaul_security=WPA2-Personal") < script.index('"$install/scripts/prplmesh_utils.sh" start')
    template = (ROOT / "manifests/wpa_backhaul.conf").read_text()
    assert re.search(r'^    ssid="[^"\n]+"$', template, re.M)
    assert re.search(r'^    psk="[^"\n]+"$', template, re.M)
    assert "    key_mgmt=WPA-PSK\n" in template


def test_native_strings_exclude_fixed_buffer_padding():
    assert '+    char ssid[beerocks::message::WIFI_SSID_MAX_LENGTH]{};' in PATCH
    assert '+    char pass[beerocks::message::WIFI_PASS_MAX_LENGTH]{};' in PATCH
    assert '+    db->device_conf.back_radio.ssid = std::string(ssid, strnlen(ssid, sizeof(ssid)));' in PATCH
    assert '+    db->device_conf.back_radio.pass = std::string(pass, strnlen(pass, sizeof(pass)));' in PATCH


def test_native_credential_branch_and_bounded_strings(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("g++ is required for the native credential regression")
    section = PATCH.split("--- a/agent/", 1)[0]
    added = "\n".join(line[1:] for line in section.splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    assert "if (radio_dir == BPL_RADIO_BACK)" in added
    source = r'''
#include <cassert>
#include <cstring>
#include <functional>
#include <string>
#include <unordered_map>
constexpr int BPL_SSID_LEN = 33;
constexpr int BPL_PASS_LEN = 65;
constexpr int BPL_SEC_LEN = 32;
constexpr int BPL_RADIO_BACK = 1;
constexpr int RETURN_OK = 0;
constexpr int RETURN_ERR = -1;
const std::string BPL_WLAN_SEC_NONE_STR = "None";
std::unordered_map<std::string, std::string> configured;
bool readable = true;
bool cfg_get_params(std::unordered_map<std::string, std::string> &parameters,
                    std::function<bool(const std::string &)> filter) {
    for (const auto &entry : configured) {
        if (filter(entry.first)) parameters.insert(entry);
    }
    return readable;
}
namespace mapf { namespace utils {
void copy_string(char *destination, const char *value, size_t capacity) {
    std::strncpy(destination, value, capacity - 1);
    destination[capacity - 1] = 0;
}
}}
int credentials(int radio_dir, char *ssid, char *pass, char *sec) {
''' + added + r'''
    return RETURN_OK;
}
int main() {
    char ssid[BPL_SSID_LEN], pass[BPL_PASS_LEN], sec[BPL_SEC_LEN];
    configured = {{"backhaul_ssid", "mesh_backhaul"},
                  {"backhaul_passphrase", "prplmesh_pass"},
                  {"backhaul_security", "WPA2-Personal"}};
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_OK);
    assert(std::string(sec) == "WPA2-Personal");
    assert(std::string(ssid, strnlen(ssid, sizeof(ssid))) == "mesh_backhaul");
    assert(std::string(pass, strnlen(pass, sizeof(pass))) == "prplmesh_pass");
    std::string command = "SET_NETWORK 0 ssid \"" + std::string(ssid, strnlen(ssid, sizeof(ssid))) + "\"";
    assert(command.size() == std::strlen(command.c_str()));
    assert(command.back() == '"');
    configured.erase("backhaul_security");
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_ERR);
    assert(!ssid[0] && !pass[0] && !sec[0]);
    configured["backhaul_security"] = "WPA2-Personal";
    configured["backhaul_passphrase"] = "";
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_ERR);
    configured["backhaul_security"] = "None";
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_OK);
    configured["backhaul_ssid"] = std::string(32, 's');
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_OK);
    configured["backhaul_ssid"].push_back('s');
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_ERR);
    configured["backhaul_ssid"] = "mesh_backhaul";
    configured["backhaul_passphrase"] = std::string(65, 'p');
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_ERR);
    readable = false;
    assert(credentials(BPL_RADIO_BACK, ssid, pass, sec) == RETURN_ERR);
}
'''
    source_file = tmp_path / "credentials.cpp"
    executable = tmp_path / "credentials"
    source_file.write_text(source)
    subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(source_file), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
