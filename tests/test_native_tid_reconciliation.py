from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0028-reconcile-native-tid-queue-instances.patch"
DB_PATH = "controller/src/beerocks/master/db/db.cpp"
IMPL_PATH = "framework/platform/nbapi/ambiorix_impl.cpp"


def patch_fragments(path):
    selected = False
    in_hunk = False
    fragments = []
    for line in PATCH.read_text().splitlines():
        if line.startswith("diff --git "):
            selected = line == f"diff --git a/{path} b/{path}"
            in_hunk = False
        elif selected and line.startswith("@@ "):
            in_hunk = True
        elif selected and in_hunk and line.startswith(("+", " ")):
            fragments.append(line[1:])
    assert fragments, path
    return "\n".join(fragments)


def native_methods():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True,
                   capture_output=True, text=True)
    source = patch_fragments(IMPL_PATH)
    start = source.index("bool AmbiorixImpl::sync_uint32_instances(")
    end = source.index("\nbool AmbiorixImpl::remove_instance", start)
    implementation = source[start:end].strip()
    database = patch_fragments(DB_PATH)
    end = database.index("\nbool db::dm_clear_sta_stats")
    database = database[:end]
    if "bool db::dm_add_tid_queue_sizes(" not in database:
        database = r'''
bool db::dm_add_tid_queue_sizes(
    const Station &station,
    const std::vector<wfa_map::tlvAssociatedWiFi6StaStatusReport::sTidQueueSize> &tid_queue_vector)
{
    if (station.dm_path.empty()) {
''' + database
    return implementation, database


HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <utility>
#include <vector>

using amxd_status_t = int;
constexpr int amxd_status_ok = 0;
constexpr int amxd_status_failed = 1;
constexpr int amxd_tattr_change_ro = 1;
using Parameters = std::map<std::string, uint32_t>;
using Snapshot = std::map<uint32_t, Parameters>;
const std::string station_path = "Device.WiFi.DataElements.Network.Device.1.Radio.1.BSS.1.STA.9";
const std::string table_path = station_path + ".TIDQueueSizes";

void require(bool condition, const std::string &message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(42);
    }
}

struct amxd_object_t {
    uint32_t index = 0;
    Parameters parameters;
    std::map<uint32_t, std::unique_ptr<amxd_object_t>> instances;
};

struct Event {
    std::string kind;
    uint32_t index;
    Parameters parameters;
    uint32_t from = 0;
    uint32_t to = 0;
    bool initialized = false;
};

struct Model {
    amxd_object_t table;
    uint32_t last_index = 100;
    std::vector<Event> events;
    std::map<std::string, unsigned> calls;
    std::set<const void *> active_transactions;
    unsigned initialized = 0;
    unsigned cleaned = 0;
    std::string fail_operation;
    unsigned fail_occurrence = 1;

    bool fail(const std::string &operation) {
        auto occurrence = ++calls[operation];
        return operation == fail_operation && occurrence == fail_occurrence;
    }

    Snapshot snapshot() const {
        Snapshot result;
        for (const auto &instance : table.instances) {
            result.emplace(instance.first, instance.second->parameters);
        }
        return result;
    }

    void publish(const Snapshot &snapshot) {
        table.instances.clear();
        for (const auto &row : snapshot) {
            auto instance = std::make_unique<amxd_object_t>();
            instance->index = row.first;
            instance->parameters = row.second;
            table.instances.emplace(row.first, std::move(instance));
        }
    }

    void seed(unsigned count = 8) {
        Snapshot snapshot;
        for (uint32_t tid = 0; tid < count; ++tid) {
            snapshot.emplace(++last_index, Parameters{{"TID", tid}, {"Size", 100 + tid}});
        }
        publish(snapshot);
    }

    void reset_observation() {
        require(active_transactions.empty(), "transaction resources remain owned");
        events.clear();
        calls.clear();
        initialized = cleaned = 0;
        fail_operation.clear();
        fail_occurrence = 1;
    }

    unsigned event_count(const std::string &kind) const {
        return std::count_if(events.begin(), events.end(), [&](const Event &event) {
            return event.kind == kind;
        });
    }
};
Model *model = nullptr;

struct Action {
    std::string kind;
    uint32_t index = 0;
    Parameters parameters;
};

struct amxd_trans_t {
    bool initialized = false;
    bool allow_read_only = false;
    bool selected_table = false;
    uint32_t selected_index = 0;
    int pending_add = -1;
    std::vector<Action> actions;
};

amxd_status_t amxd_trans_init(amxd_trans_t *transaction)
{
    if (model->fail("init")) return amxd_status_failed;
    require(model->active_transactions.insert(transaction).second, "transaction initialized twice");
    transaction->initialized = true;
    ++model->initialized;
    return amxd_status_ok;
}

void amxd_trans_clean(amxd_trans_t *transaction)
{
    require(transaction->initialized, "cleaning an uninitialized transaction");
    require(model->active_transactions.erase(transaction) == 1, "transaction cleaned twice");
    transaction->initialized = false;
    transaction->actions.clear();
    ++model->cleaned;
}

amxd_status_t amxd_trans_set_attr(amxd_trans_t *transaction, int attribute, bool enabled)
{
    if (model->fail("attr")) return amxd_status_failed;
    require(attribute == amxd_tattr_change_ro, "unexpected transaction attribute");
    transaction->allow_read_only = enabled;
    return amxd_status_ok;
}

amxd_status_t amxd_trans_select_object(amxd_trans_t *transaction, amxd_object_t *object)
{
    if (model->fail("select")) return amxd_status_failed;
    transaction->selected_table = object == &model->table;
    transaction->selected_index = object->index;
    transaction->pending_add = -1;
    return amxd_status_ok;
}

amxd_status_t amxd_trans_del_inst(amxd_trans_t *transaction, uint32_t index, const char *name)
{
    if (model->fail("delete")) return amxd_status_failed;
    require(transaction->selected_table && name == nullptr, "delete must select the table");
    transaction->actions.push_back({"delete", index, {}});
    return amxd_status_ok;
}

amxd_status_t amxd_trans_add_inst(amxd_trans_t *transaction, uint32_t index, const char *name)
{
    if (model->fail("add")) return amxd_status_failed;
    require(transaction->selected_table && index == 0 && name == nullptr,
            "creation must allocate a native instance index");
    transaction->actions.push_back({"add", 0, {}});
    transaction->pending_add = static_cast<int>(transaction->actions.size()) - 1;
    transaction->selected_table = false;
    return amxd_status_ok;
}

amxd_status_t trans_set_uint32(amxd_trans_t *transaction, const char *parameter, uint32_t value)
{
    if (model->fail("set")) return amxd_status_failed;
    if (transaction->pending_add >= 0) {
        transaction->actions.at(transaction->pending_add).parameters[parameter] = value;
    } else {
        require(!transaction->selected_table, "value write must select an instance");
        transaction->actions.push_back({"set", transaction->selected_index, {{parameter, value}}});
    }
    return amxd_status_ok;
}

uint32_t object_get_uint32(amxd_object_t *object, const char *parameter, amxd_status_t *status)
{
    if (model->fail(std::string("read-") + parameter) || !object->parameters.count(parameter)) {
        *status = amxd_status_failed;
        return 0;
    }
    *status = amxd_status_ok;
    return object->parameters.at(parameter);
}

uint32_t amxd_object_get_index(amxd_object_t *object) { return object->index; }
#define amxd_object_for_each(kind, iterator, object) \
    for (auto iterator = (object)->instances.begin(); iterator != (object)->instances.end(); ++iterator)
#define amxc_llist_it_get_data(iterator, type, member) ((iterator)->second.get())
#define amxd_object_get_value(type, object, parameter, status) object_get_uint32(object, parameter, status)
#define amxd_trans_set_value(type, transaction, parameter, value) trans_set_uint32(transaction, parameter, value)

namespace Amxrt {
Model *getDatamodel() { return model; }
}

amxd_status_t amxd_trans_apply(amxd_trans_t *transaction, Model *target)
{
    require(target == model && transaction->allow_read_only, "incorrect transaction target or access");
    if (model->fail("apply")) return amxd_status_failed;
    auto staged = model->snapshot();
    auto next_index = model->last_index;
    std::vector<Event> notifications;
    for (const auto &action : transaction->actions) {
        if (action.kind == "add") {
            auto parameters = Parameters{{"TID", 0}, {"Size", 0}};
            for (const auto &parameter : action.parameters) parameters[parameter.first] = parameter.second;
            staged[++next_index] = parameters;
            notifications.push_back({"added", next_index, parameters, 0, 0,
                                     action.parameters.count("TID") && action.parameters.count("Size")});
            notifications.push_back({"counter", next_index, {}});
        } else if (action.kind == "delete") {
            require(staged.erase(action.index) == 1, "deleting an absent instance");
            notifications.push_back({"removed", action.index, {}});
            notifications.push_back({"counter", action.index, {}});
        } else {
            require(staged.count(action.index), "writing an absent instance");
            auto &parameters = staged.at(action.index);
            for (const auto &parameter : action.parameters) {
                const auto previous = parameters.at(parameter.first);
                parameters[parameter.first] = parameter.second;
                if (previous != parameter.second) {
                    notifications.push_back({"changed", action.index, {{parameter.first, parameter.second}},
                                             previous, parameter.second});
                }
            }
        }
    }
    std::set<uint32_t> unique_tids;
    for (const auto &row : staged) {
        if (!unique_tids.insert(row.second.at("TID")).second) return amxd_status_failed;
    }
    model->publish(staged);
    model->last_index = next_index;
    model->events.insert(model->events.end(), notifications.begin(), notifications.end());
    if (transaction->pending_add >= 0) transaction->selected_index = next_index;
    transaction->pending_add = -1;
    transaction->actions.clear();
    return amxd_status_ok;
}

class AmbiorixImpl {
public:
    amxd_object_t *find_object(const std::string &path) {
        require(path == table_path, "wrong TID table path");
        return model->fail("find") ? nullptr : &model->table;
    }
    bool sync_uint32_instances(const std::string &, const std::string &, const std::string &,
                               const std::map<uint32_t, uint32_t> &);
};

NATIVE_IMPLEMENTATION

namespace wfa_map {
struct tlvAssociatedWiFi6StaStatusReport {
    struct sTidQueueSize { uint8_t tid; uint8_t queue_size; };
};
}
using TidQueue = wfa_map::tlvAssociatedWiFi6StaStatusReport::sTidQueueSize;
using Report = std::vector<TidQueue>;
struct Station { std::string dm_path = station_path; };

struct Datamodel {
    AmbiorixImpl implementation;
    unsigned calls = 0;
    bool sync_uint32_instances(const std::string &path, const std::string &key,
                               const std::string &value, const std::map<uint32_t, uint32_t> &rows) {
        ++calls;
        require(key == "TID" && value == "Size", "incorrect DB column mapping");
        return implementation.sync_uint32_instances(path, key, value, rows);
    }
};
struct db {
    Datamodel *m_ambiorix_datamodel;
    bool dm_add_tid_queue_sizes(const Station &, const Report &);
};

NATIVE_DATABASE

Report complete_report()
{
    Report report;
    for (uint8_t tid = 0; tid < 8; ++tid) report.push_back({tid, static_cast<uint8_t>(100 + tid)});
    return report;
}

std::map<uint32_t, uint32_t> indices_by_tid()
{
    std::map<uint32_t, uint32_t> indices;
    for (const auto &row : model->snapshot()) {
        require(indices.emplace(row.second.at("TID"), row.first).second, "duplicate TIDs in model");
    }
    return indices;
}

void expect_rows(const Report &report)
{
    std::map<uint32_t, uint32_t> expected, actual;
    for (const auto &row : report) expected.emplace(row.tid, row.queue_size);
    for (const auto &row : model->snapshot()) actual.emplace(row.second.at("TID"), row.second.at("Size"));
    require(actual == expected && model->table.instances.size() == expected.size(), "incorrect TID rows");
}

void expect_cleanup()
{
    require(model->active_transactions.empty() && model->initialized == model->cleaned,
            "transaction allocation leak");
}

int main(int count, char **arguments)
{
    assert(count == 2);
    const std::string scenario = arguments[1];
    Model storage;
    model = &storage;
    Datamodel datamodel;
    db database{&datamodel};
    Station station;
    auto report = complete_report();

    if (scenario == "initial") {
        require(database.dm_add_tid_queue_sizes(station, report), "initial report failed");
        expect_rows(report);
        require(model->event_count("added") == 8 && model->event_count("counter") == 8 &&
                model->event_count("changed") == 0 && model->event_count("removed") == 0,
                "incorrect initial notifications");
        for (const auto &event : model->events) {
            if (event.kind == "added") {
                require(event.initialized && event.parameters.at("Size") == 100 + event.parameters.at("TID"),
                        "instance became visible before TID and Size initialization");
            }
        }
        require(model->calls["apply"] == 1, "initial cohort needs one atomic transaction");
    } else if (scenario == "repeat" || scenario == "reorder") {
        require(database.dm_add_tid_queue_sizes(station, report), "initial report failed");
        expect_cleanup();
        auto before = model->snapshot();
        auto last_index = model->last_index;
        model->reset_observation();
        for (unsigned iteration = 0; iteration < 20; ++iteration) {
            if (scenario == "reorder") std::rotate(report.begin(), report.begin() + 1, report.end());
            require(database.dm_add_tid_queue_sizes(station, report), "repeated report failed");
            require(model->snapshot() == before && model->last_index == last_index,
                    "unchanged TIDs lost native instance identities");
            require(model->events.empty() && model->calls["apply"] == 0,
                    "unchanged report emitted notifications or applied a transaction");
            expect_cleanup();
        }
    } else if (scenario == "size") {
        model->seed();
        const auto before = indices_by_tid();
        report[3].queue_size = 203;
        require(database.dm_add_tid_queue_sizes(station, report), "size update failed");
        expect_rows(report);
        require(indices_by_tid() == before, "size update changed indices");
        require(model->events.size() == 1 && model->events.front().kind == "changed" &&
                model->events.front().index == before.at(3) &&
                model->events.front().parameters == Parameters{{"Size", 203}} &&
                model->events.front().from == 103 && model->events.front().to == 203,
                "size update must emit only the changed Size");
    } else if (scenario == "sparse") {
        model->seed();
        const auto before = indices_by_tid();
        report = {{1, 101}, {3, 133}, {12, 212}};
        require(database.dm_add_tid_queue_sizes(station, report), "sparse update failed");
        expect_rows(report);
        const auto after = indices_by_tid();
        require(after.at(1) == before.at(1) && after.at(3) == before.at(3), "surviving TID indices changed");
        require(after.at(12) > before.rbegin()->second, "new TID reused an old instance index");
        require(model->event_count("removed") == 6 && model->event_count("added") == 1 &&
                model->event_count("counter") == 7 && model->event_count("changed") == 1,
                "sparse update performed extra structural mutations");
    } else if (scenario == "empty") {
        model->seed();
        require(database.dm_add_tid_queue_sizes(station, {}), "empty report failed");
        expect_rows({});
        require(model->event_count("removed") == 8 && model->event_count("counter") == 8 &&
                model->event_count("added") == 0, "empty report did not delete the old cohort");
        expect_cleanup();
        model->reset_observation();
        require(database.dm_add_tid_queue_sizes(station, {}), "repeated empty report failed");
        require(model->events.empty() && model->calls["apply"] == 0, "empty table was mutated");
    } else if (scenario == "atomic") {
        model->seed(1);
        const auto before = indices_by_tid();
        report = {{0, 100}, {7, 207}};
        require(database.dm_add_tid_queue_sizes(station, report), "creation conflicted with existing unique TID zero");
        expect_rows(report);
        require(indices_by_tid().at(0) == before.at(0), "existing TID zero was replaced");
        require(model->calls["apply"] == 1 && model->event_count("added") == 1 &&
                model->event_count("removed") == 0 && model->event_count("changed") == 0,
                "creation split across transactions");
        const auto &event = model->events.front();
        require(event.kind == "added" && event.initialized && event.parameters == Parameters{{"TID", 7}, {"Size", 207}},
                "new TID was not initialized atomically");
    } else if (scenario == "duplicate" || scenario == "duplicate-identical") {
        model->seed();
        const auto before = model->snapshot();
        report.push_back({3, static_cast<uint8_t>(scenario == "duplicate" ? 222 : 103)});
        require(!database.dm_add_tid_queue_sizes(station, report), "duplicate report accepted");
        require(datamodel.calls == 0 && model->calls.empty() && model->snapshot() == before,
                "duplicate input reached the data model");
    } else if (scenario == "no-station-path") {
        station.dm_path.clear();
        require(database.dm_add_tid_queue_sizes(station, report), "station without a DM path changed behavior");
        require(datamodel.calls == 0 && model->calls.empty(), "missing STA path reached the data model");
    } else if (scenario.compare(0, 5, "fail-") == 0) {
        model->seed();
        const auto before = model->snapshot();
        const auto last_index = model->last_index;
        const auto operation = scenario.substr(5);
        model->fail_operation = operation;
        if (operation == "select" || operation == "set") report[3].queue_size = 203;
        if (operation == "delete") {
            report = {{0, 100}};
            model->fail_occurrence = 2;
        }
        if (operation == "add" || operation == "set-key" || operation == "set-size") {
            report.push_back({12, 212});
        }
        if (operation == "set-key" || operation == "set-size") {
            model->fail_operation = "set";
            model->fail_occurrence = operation == "set-key" ? 1 : 2;
        }
        if (operation == "read-TID" || operation == "read-Size") {
            report[0].queue_size = 200;
            model->fail_occurrence = 2;
        }
        if (operation == "apply") {
            report = {{1, 101}, {3, 133}, {12, 212}};
        }
        require(!database.dm_add_tid_queue_sizes(station, report), "transaction failure was swallowed");
        require(model->snapshot() == before && model->last_index == last_index, "failed transaction changed the model");
        expect_cleanup();
        require(model->cleaned == (operation == "init" || operation == "find" ? 0u : 1u),
                "incorrect transaction cleanup count");
        model->reset_observation();
        require(database.dm_add_tid_queue_sizes(station, report), "retry after failure did not recover");
        expect_rows(report);
    } else {
        return 43;
    }
    expect_cleanup();
    std::cout << "PASS " << scenario << '\n';
}
'''


@pytest.fixture(scope="module")
def reconciliation_binaries(tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for native TID reconciliation regression")
    implementation, database = native_methods()
    directory = tmp_path_factory.mktemp("native-tid-reconciliation")
    binaries = {}

    def build(variant):
        if variant in binaries:
            return binaries[variant]
        method = implementation
        db_method = database
        if variant == "recreate":
            original = "auto desired = pending.find(current_key);"
            assert method.count(original) == 1
            method = method.replace(original, original + "\n        desired = pending.end();")
        elif variant == "split-creation":
            original = "amxd_trans_add_inst(&transaction, 0, nullptr) != amxd_status_ok ||"
            assert method.count(original) == 1
            method = method.replace(original, original +
                                    "\n            amxd_trans_apply(&transaction, Amxrt::getDatamodel()) != amxd_status_ok ||")
        elif variant == "allow-duplicates":
            original = "if (!rows.emplace(tid_queue.tid, tid_queue.queue_size).second) {\n            return false;"
            assert db_method.count(original) == 1
            db_method = db_method.replace(original, original.replace("return false;", "continue;"))
        elif variant == "no-cleanup":
            method, count = re.subn(
                r"    std::unique_ptr<amxd_trans_t, decltype\(&amxd_trans_clean\)> cleanup\(&transaction,\s*amxd_trans_clean\);\n",
                "", method,
            )
            assert count == 1
        else:
            assert variant == "patched"
        program = directory / f"{variant}.cpp"
        program.write_text(HARNESS.replace("NATIVE_IMPLEMENTATION", method)
                           .replace("NATIVE_DATABASE", db_method))
        binary = directory / variant
        result = subprocess.run(
            [compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", str(program), "-o", str(binary)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        binaries[variant] = binary
        return binary

    return build


SCENARIOS = [
    "initial", "repeat", "reorder", "size", "sparse", "empty", "atomic",
    "duplicate", "duplicate-identical", "no-station-path", "fail-find", "fail-init",
    "fail-attr", "fail-read-TID", "fail-read-Size", "fail-select", "fail-delete",
    "fail-add", "fail-set", "fail-set-key", "fail-set-size", "fail-apply",
]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_native_tid_reconciliation(reconciliation_binaries, scenario):
    binary = reconciliation_binaries("patched")
    result = subprocess.run([str(binary), scenario], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"PASS {scenario}\n"


@pytest.mark.parametrize("variant,scenario,diagnostic", [
    ("recreate", "repeat", "unchanged TIDs lost native instance identities"),
    ("split-creation", "atomic", "creation conflicted with existing unique TID zero"),
    ("allow-duplicates", "duplicate", "duplicate report accepted"),
    ("no-cleanup", "initial", "transaction allocation leak"),
    ("no-cleanup", "fail-set-size", "transaction allocation leak"),
])
def test_tid_reconciliation_negative_controls(reconciliation_binaries, variant, scenario, diagnostic):
    binary = reconciliation_binaries(variant)
    result = subprocess.run([str(binary), scenario], capture_output=True, text=True, timeout=5)
    assert result.returncode == 42, result.stdout + result.stderr
    assert diagnostic in result.stderr
