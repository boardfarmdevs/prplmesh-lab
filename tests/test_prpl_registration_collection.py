from pathlib import Path
import shutil
import subprocess

import pytest


PATCH = Path(__file__).resolve().parents[1] / "patches/prplmesh/0020-controller-defer-registration-collection.patch"


@pytest.mark.parametrize("ignore_deferral", [False, True])
def test_native_registration_batches_without_quadratic_queries(tmp_path, ignore_deferral):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native registration regression")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    source = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                       if line.startswith(("+", " ")) and not line.startswith("+++"))
    method = source[source.index("bool Controller::add_unassociated_station("):
                    source.index("bool Controller::remove_unassociated_station(")]
    if ignore_deferral:
        method = method.replace("return defer_query ||", "return (defer_query && false) ||")
    program = r'''
#include <cassert>
#include <cstdint>
#include <tuple>
#include <vector>
using sMacAddr = int;
struct Database {
    bool valid = true;
    std::vector<std::tuple<int, int, int, int, int>> registrations;
    bool add_unassociated_station(int station, int channel, int operating_class, int agent, int radio) {
        if (valid) registrations.emplace_back(station, channel, operating_class, agent, radio);
        return valid;
    }
};
struct Controller {
    Database database;
    int cmdu_tx = 0;
    unsigned queries = 0;
    bool query_success = true;
    bool send_unassociated_sta_link_metrics_query_message(int, Database &) {
        queries++;
        return query_success;
    }
    bool add_unassociated_station(const sMacAddr &, uint8_t, uint8_t, const sMacAddr &,
                                  const sMacAddr &, bool defer_query = false);
};
NATIVE_METHOD
int main() {
    Controller controller;
    for (int station = 0; station < 100; station++) {
        for (int agent = 0; agent < 4; agent++)
            assert(controller.add_unassociated_station(station, 36, 115, agent, agent + 10, true));
    }
    assert(controller.database.registrations.size() == 400);
    assert(controller.queries == 0);
    assert(controller.database.registrations.back() == std::make_tuple(99, 36, 115, 3, 13));
    assert(controller.send_unassociated_sta_link_metrics_query_message(controller.cmdu_tx, controller.database));
    assert(controller.queries == 1);
    controller.database.valid = false;
    assert(!controller.add_unassociated_station(100, 36, 115, 0, 10, true));
    assert(!controller.add_unassociated_station(100, 36, 115, 0, 10));
    assert(controller.queries == 1);
    controller.database.valid = true;
    assert(controller.add_unassociated_station(100, 36, 115, 0, 10));
    assert(controller.queries == 2);
    controller.query_success = false;
    assert(!controller.add_unassociated_station(100, 36, 115, 0, 10));
    assert(controller.queries == 3);
    assert(controller.add_unassociated_station(100, 36, 115, 0, 10, true));
    assert(controller.queries == 3);
}
'''.replace("NATIVE_METHOD", method)
    source_file = tmp_path / "registration.cpp"
    binary = tmp_path / "registration"
    source_file.write_text(program)
    subprocess.run([compiler, "-Wall", "-Wextra", "-Werror", str(source_file), "-o", str(binary)],
                   check=True, capture_output=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert (result.returncode == 0) != ignore_deferral


def test_nbapi_deferral_is_optional_and_preserves_legacy_callers():
    source = PATCH.read_text()
    assert '+        bool defer_query = false);' in source
    assert '+                %in bool defer_query' in source
    assert '+                                                  GET_BOOL(args, "defer_query"))) {' in source
    assert "%mandatory bool defer_query" not in source
