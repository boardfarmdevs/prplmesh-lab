from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0027-release-nbapi-action-allocations.patch"
FUNCTIONS = (
    "get_param_string", "get_param_bool", "get_param_uint32",
    "get_uint64_from_bss_color_bitmap", "trigger_scan", "btm_request",
    "trigger_set_spatial_reuse", "update_vbss_capabilities",
    "trigger_vbss_creation", "trigger_vbss_destruction",
)


def native_fragments(patched):
    result = subprocess.run(
        ["git", "apply", "--numstat", str(PATCH)], check=True,
        capture_output=True, text=True,
    )
    assert result.stdout.splitlines()[0].split("\t")[2] == "controller/nbapi/on_action.cpp"
    selected = (" ", "+" if patched else "-")
    return "\n".join(
        line[1:] for line in PATCH.read_text().splitlines()
        if line.startswith(selected) and not line.startswith(("+++", "---"))
    )


def function_body(source, name):
    signature = re.search(r"^(?:static )?[\w:]+ " + name + r"\(", source, re.MULTILINE)
    assert signature is not None, name
    opening = source.index("{", signature.start())
    depth = 1
    ending = opening + 1
    while depth:
        assert ending < len(source), name
        if source[ending] == "{":
            depth += 1
        elif source[ending] == "}":
            depth -= 1
        ending += 1
    return source[signature.start():ending]


HARNESS = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <new>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#define LOG(level) std::ostringstream()
using amxd_status_t = int;
constexpr int amxd_status_ok = 0;
constexpr int amxd_status_unknown_error = 1;
constexpr int amxd_status_parameter_not_found = 2;
constexpr int amxd_status_object_not_found = 3;
constexpr int amxd_status_invalid_attr = 4;
constexpr int amxd_status_invalid_arg = 5;
constexpr int amxd_status_invalid_value = 6;
constexpr int PREFERRED_DWELLTIME_MS = 10;
struct amxd_function_t {};

std::set<void *> owned_allocations;
unsigned allocation_count = 0;
unsigned free_count = 0;
bool fail_conversion = false;
bool throw_after_read = false;

extern "C" void __real_free(void *pointer);
extern "C" void __wrap_free(void *pointer)
{
    if (pointer == nullptr) {
        return;
    }
    assert(owned_allocations.erase(pointer) == 1);
    ++free_count;
    __real_free(pointer);
}

char *copy_owned(const std::string &text)
{
    auto pointer = static_cast<char *>(std::malloc(text.size() + 1));
    assert(pointer != nullptr);
    std::memcpy(pointer, text.c_str(), text.size() + 1);
    assert(owned_allocations.insert(pointer).second);
    ++allocation_count;
    return pointer;
}

struct amxc_var_t {
    char *text = nullptr;
    uint64_t number = 0;
    std::map<std::string, amxc_var_t> fields;
};

void amxc_var_init(amxc_var_t *value)
{
    value->text = nullptr;
    value->number = 0;
}

void amxc_var_clean(amxc_var_t *value)
{
    std::free(value->text);
    value->text = nullptr;
    value->number = 0;
}

struct amxd_object_t {
    std::map<std::string, std::string> parameters;
    amxd_object_t *parent = nullptr;
    amxd_object_t *child = nullptr;
    bool read_success = true;
};

amxd_status_t amxd_object_get_param(amxd_object_t *object, const char *name,
                                   amxc_var_t *value)
{
    amxc_var_clean(value);
    if (!object || !object->parameters.count(name)) {
        return amxd_status_parameter_not_found;
    }
    value->text = copy_owned(object->parameters.at(name));
    value->number = std::strtoull(value->text, nullptr, 10);
    if (throw_after_read) {
        throw std::bad_alloc();
    }
    return object->read_success ? amxd_status_ok : amxd_status_unknown_error;
}

amxd_object_t *amxd_object_get_parent(amxd_object_t *object)
{
    return object ? object->parent : nullptr;
}

amxd_object_t *amxd_object_get_child(amxd_object_t *object, const char *)
{
    return object ? object->child : nullptr;
}

char *constcast_cstring_t(const amxc_var_t *value) { return value ? value->text : nullptr; }
bool constcast_bool(const amxc_var_t *value) { return value && value->number; }
uint32_t dyncast_uint32_t(const amxc_var_t *value) { return value ? value->number : 0; }
char *dyncast_cstring_t(const amxc_var_t *value)
{
    return fail_conversion || !value || !value->text ? nullptr : copy_owned(value->text);
}
amxc_var_t *get_argument(amxc_var_t *arguments, const char *name)
{
    auto found = arguments->fields.find(name);
    return found == arguments->fields.end() ? nullptr : &found->second;
}
#define amxc_var_constcast(type, value) constcast_##type(value)
#define amxc_var_dyncast(type, value) dyncast_##type(value)
#define GET_ARG(arguments, name) get_argument(arguments, name)
#define GET_CHAR(arguments, name) constcast_cstring_t(GET_ARG(arguments, name))
#define GET_UINT32(arguments, name) dyncast_uint32_t(GET_ARG(arguments, name))
#define GET_BOOL(arguments, name) constcast_bool(GET_ARG(arguments, name))

struct sMacAddr { uint8_t oct[6] = {}; };
namespace tlvf {
bool mac_from_string(uint8_t *octets, const std::string &text)
{
    if (text.size() != 17) {
        return false;
    }
    octets[5] = static_cast<uint8_t>(text.back());
    return true;
}
sMacAddr mac_from_string(const std::string &text)
{
    sMacAddr address;
    mac_from_string(address.oct, text);
    return address;
}
}
namespace beerocks {
namespace message { constexpr size_t SUPPORTED_CHANNELS_LENGTH = 16; }
namespace string_utils {
std::vector<std::string> str_split(const std::string &text, char separator)
{
    std::vector<std::string> values;
    std::istringstream input(text);
    std::string value;
    while (std::getline(input, value, separator)) {
        values.push_back(value);
    }
    return values;
}
}
}

struct Controller {
    bool success = true;
    unsigned calls = 0;
    bool imminent = false;
    uint32_t timer = 0;

    template<typename... Arguments> bool trigger_scan(Arguments &&...) {
        ++calls;
        return success;
    }
    template<typename... Arguments> bool trigger_set_spatial_reuse(Arguments &&...) {
        ++calls;
        return success;
    }
    template<typename... Arguments> bool update_agent_vbss_capabilities(Arguments &&...) {
        ++calls;
        return success;
    }
    template<typename... Arguments> bool trigger_vbss_creation(Arguments &&...) {
        ++calls;
        return success;
    }
    template<typename... Arguments> bool trigger_vbss_destruction(Arguments &&...) {
        ++calls;
        return success;
    }
    void send_btm_request(bool requested_imminent, uint32_t requested_timer,
                          uint32_t, uint32_t, uint32_t, const std::string &station,
                          const std::string &target) {
        assert(station == "02:00:00:00:00:03");
        assert(target == "02:00:00:00:00:04");
        imminent = requested_imminent;
        timer = requested_timer;
        ++calls;
    }
};
struct Database {
    Controller *controller = nullptr;
    bool allow_steering = true;
    Controller *get_controller_ctx() { return controller; }
    bool can_start_client_steering(const std::string &, const std::string &) {
        return allow_steering;
    }
};
Database *g_database = nullptr;

NATIVE_CODE

void set_argument(amxc_var_t &arguments, const std::string &name,
                  const char *text, uint64_t number = 0)
{
    arguments.fields[name].text = const_cast<char *>(text);
    arguments.fields[name].number = number;
}

int main(int count, char **arguments)
{
    assert(count == 5);
    const std::string action = arguments[1];
    const std::string scenario = arguments[2];
    const int expected_status = std::stoi(arguments[3]);
    const unsigned expected_calls = std::stoul(arguments[4]);

    for (unsigned iteration = 0; iteration < 16; ++iteration) {
        Controller controller;
        Database database;
        database.controller = &controller;
        g_database = &database;
        amxd_object_t radio, station, multiap, bss_table, bss, spatial;
        radio.parameters["ID"] = "02:00:00:00:00:01";
        radio.parameters["Value"] = "native-value";
        station.parameters["MACAddress"] = "02:00:00:00:00:03";
        bss.parameters["BSSID"] = "02:00:00:00:00:02";
        spatial.parameters = {{"SRGInformationValid", "1"}, {"BSSColor", "1"},
                              {"SRGBSSColorBitmap", "1 2"},
                              {"SRGPartialBSSIDBitmap", "3 4"}};
        radio.child = &spatial;
        multiap.parent = &station;
        bss.parent = &bss_table;
        bss_table.parent = &radio;
        amxc_var_t input, output;
        set_argument(input, "channels_list", "36");
        set_argument(input, "channels_num", nullptr, 1);
        set_argument(input, "TargetBSS", "02:00:00:00:00:04");
        set_argument(input, "vbssid", "02:00:00:00:00:02");
        set_argument(input, "client_mac", "02:00:00:00:00:03");
        set_argument(input, "ssid", "test-network");
        set_argument(input, "pass", "test-password");

        if (scenario == "no_controller") database.controller = nullptr;
        if (scenario == "controller_failure") controller.success = false;
        if (scenario == "empty_id") radio.parameters["ID"] = "";
        if (scenario == "empty_station") station.parameters["MACAddress"] = "";
        if (scenario == "empty_bssid") bss.parameters["BSSID"] = "";
        if (scenario == "missing_parent") multiap.parent = nullptr;
        if (scenario == "missing_radio") bss_table.parent = nullptr;
        if (scenario == "missing_spatial") radio.child = nullptr;
        if (scenario == "invalid_channel") set_argument(input, "channels_list", "256");
        if (scenario == "channel_count") set_argument(input, "channels_num", nullptr, 2);
        if (scenario == "empty_target") set_argument(input, "TargetBSS", "");
        if (scenario == "denied") database.allow_steering = false;
        if (scenario == "imminent") set_argument(input, "DisassociationImminent", nullptr, 1);
        if (scenario == "timer") set_argument(input, "DisassociationTimer", nullptr, 7);
        if (scenario == "short_password") set_argument(input, "pass", "short");
        if (scenario == "invalid_vbssid") set_argument(input, "vbssid", "invalid");
        if (scenario == "invalid_client") set_argument(input, "client_mac", "invalid");
        if (scenario == "empty_string") radio.parameters["Value"] = "";
        if (scenario == "missing_parameter") radio.parameters.erase("Value");
        if (scenario == "read_failure") radio.read_success = false;
        fail_conversion = scenario == "conversion_failure";
        throw_after_read = scenario == "exception";

        int status = amxd_status_ok;
        try {
            if (action == "helper") {
                auto value = get_param_string(&radio, "Value");
                assert(value == (scenario == "success" ? "native-value" : ""));
            } else if (action == "scan") {
                status = trigger_scan(&radio, nullptr, &input, &output);
            } else if (action == "btm") {
                status = btm_request(&multiap, nullptr, &input, &output);
            } else if (action == "spatial") {
                status = trigger_set_spatial_reuse(&radio, nullptr, &input, &output);
            } else if (action == "capabilities") {
                status = update_vbss_capabilities(&radio, nullptr, &input, &output);
            } else if (action == "creation") {
                status = trigger_vbss_creation(&radio, nullptr, &input, &output);
            } else if (action == "destruction") {
                status = trigger_vbss_destruction(&bss, nullptr, &input, &output);
            } else {
                return 44;
            }
        } catch (const std::bad_alloc &) {
            status = -1;
        }
        if (status != expected_status || controller.calls != expected_calls) {
            std::cerr << "behavior mismatch: " << status << " calls=" << controller.calls << '\n';
            return 43;
        }
        if (action == "btm" && controller.calls) {
            assert(controller.imminent == (scenario == "imminent" || scenario == "timer"));
            assert(controller.timer == (scenario == "imminent" ? 60u : scenario == "timer" ? 7u : 0u));
        }
    }
    std::cout << "allocations=" << allocation_count << " frees=" << free_count
              << " outstanding=" << owned_allocations.size() << '\n';
    return owned_allocations.empty() ? 0 : 42;
}
'''


@pytest.fixture(scope="module", params=[True, False], ids=["patched", "unpatched"])
def action_binary(request, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for NBAPI allocation regression")
    patched = request.param
    source = native_fragments(patched)
    definitions = []
    if patched:
        start = source.index("class ScopedVariant {")
        end = source.index("\n};", start) + len("\n};")
        definitions.append(source[start:end])
    definitions.extend(function_body(source, name) for name in FUNCTIONS)
    directory = tmp_path_factory.mktemp("nbapi-action-memory")
    program = directory / "actions.cpp"
    program.write_text(HARNESS.replace("NATIVE_CODE", "\n\n".join(definitions)))
    binary = directory / "actions"
    result = subprocess.run(
        [compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
         str(program), "-Wl,--wrap=free", "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return binary, patched


CASES = [
    ("helper", "success", 0, 0, True),
    ("helper", "empty_string", 0, 0, True),
    ("helper", "missing_parameter", 0, 0, False),
    ("helper", "read_failure", 0, 0, False),
    ("helper", "conversion_failure", 0, 0, False),
    ("scan", "invalid_channel", 1, 0, True),
    ("scan", "channel_count", 1, 0, True),
    ("btm", "missing_parent", 3, 0, False),
    ("btm", "empty_station", 4, 0, True),
    ("btm", "empty_target", 2, 0, True),
    ("btm", "denied", 5, 0, True),
    ("btm", "imminent", 0, 1, True),
    ("btm", "timer", 0, 1, True),
    ("spatial", "missing_spatial", 1, 0, True),
    ("creation", "short_password", 6, 0, True),
    ("creation", "invalid_vbssid", 6, 0, True),
    ("creation", "invalid_client", 6, 0, True),
    ("destruction", "invalid_client", 6, 0, False),
    ("destruction", "empty_bssid", 2, 0, True),
    ("destruction", "missing_radio", 3, 0, True),
]
for action in ("scan", "btm", "spatial", "capabilities", "creation", "destruction"):
    CASES.extend([(action, "success", 0, 1, True), (action, "no_controller", 1, 0, False)])
    if action != "btm":
        CASES.extend([(action, "controller_failure", 1, 1, True),
                      (action, "empty_id", 2, 0, True)])
for action in ("helper", "scan", "btm", "spatial", "capabilities", "creation", "destruction"):
    CASES.append((action, "exception", -1, 0, True))


@pytest.mark.parametrize("action,scenario,status,calls,old_leaks", CASES,
                         ids=[f"{case[0]}-{case[1]}" for case in CASES])
def test_native_action_allocation_ownership(action_binary, action, scenario, status, calls, old_leaks):
    binary, patched = action_binary
    result = subprocess.run([str(binary), action, scenario, str(status), str(calls)],
                            capture_output=True, text=True, timeout=5)
    expect_leak = old_leaks and not patched
    assert result.returncode == (42 if expect_leak else 0), result.stdout + result.stderr
    counts = re.fullmatch(r"allocations=(\d+) frees=(\d+) outstanding=(\d+)\n", result.stdout)
    assert counts is not None, result.stdout
    allocated, freed, outstanding = map(int, counts.groups())
    assert allocated - freed == outstanding
    if expect_leak:
        assert outstanding >= 16
    else:
        assert outstanding == 0
