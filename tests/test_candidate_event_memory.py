from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0030-owned-candidate-event.patch"
SOURCE_PATH = "common/beerocks/bwl/nl80211/mon_wlan_hal_nl80211.cpp"


def candidate_fragment(patched):
    result = subprocess.run(
        ["git", "apply", "--numstat", str(PATCH)], check=True,
        capture_output=True, text=True,
    )
    assert [line.split("\t")[2] for line in result.stdout.splitlines()] == [SOURCE_PATH]
    selected = (" ", "+" if patched else "-")
    fragments = []
    in_hunk = False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line.startswith(selected):
            fragments.append(line[1:])
    source = "\n".join(fragments)
    start = source.index("    if (stats.empty()) {")
    end = source.index("    return true;", start) + len("    return true;")
    return source[start:end]


HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iterator>
#include <memory>
#include <new>
#include <utility>
#include <vector>

struct alignas(std::max_align_t) Allocation {
    std::size_t size;
};
std::size_t live_blocks = 0;
std::size_t live_bytes = 0;
int allocations_before_failure = -1;

void *operator new(std::size_t size)
{
    if (allocations_before_failure == 0) {
        throw std::bad_alloc();
    }
    if (allocations_before_failure > 0) {
        --allocations_before_failure;
    }
    auto allocation = static_cast<Allocation *>(std::malloc(sizeof(Allocation) + size));
    if (!allocation) {
        throw std::bad_alloc();
    }
    allocation->size = size;
    ++live_blocks;
    live_bytes += size;
    return allocation + 1;
}

void operator delete(void *pointer) noexcept
{
    if (pointer) {
        auto allocation = static_cast<Allocation *>(pointer) - 1;
        --live_blocks;
        live_bytes -= allocation->size;
        std::free(allocation);
    }
}
void *operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void *pointer) noexcept { ::operator delete(pointer); }
void operator delete(void *pointer, std::size_t) noexcept { ::operator delete(pointer); }
void operator delete[](void *pointer, std::size_t) noexcept { ::operator delete(pointer); }

struct sMacAddr { uint8_t oct[6]; };
typedef struct {
    sMacAddr mac_adress;
    int32_t signal_strength;
    uint8_t channel;
    uint8_t operating_class;
    uint64_t time_stamp;
} sUnassociatedStationStats;
typedef struct {
    std::vector<sUnassociatedStationStats> un_stations_stats;
} sUnassociatedStationsStats;

#define ALLOC_SMART_BUFFER(size) \
    std::shared_ptr<char>(new char[size], [](char *obj) { \
        if (obj) \
            delete[] obj; \
    })
struct LogSink {
    LogSink &operator<<(const char *) { return *this; }
};
#define LOG(level) LogSink()

enum Event { Unassociation_Stations_Stats };
using hal_event_t = std::pair<int, std::shared_ptr<void>>;
using hal_event_ptr_t = std::shared_ptr<hal_event_t>;
using hal_event_cb_t = std::function<bool(hal_event_ptr_t)>;
struct CallbackFailure {};

struct Hal {
    std::vector<hal_event_ptr_t> queue;
    bool fail_queue_allocation = false;

    bool event_queue_push(int event, std::shared_ptr<void> data)
    {
        if (fail_queue_allocation) {
            allocations_before_failure = 0;
        }
        auto event_ptr = std::make_shared<hal_event_t>(hal_event_t(event, data));
        queue.push_back(event_ptr);
        return true;
    }

    bool publish(std::vector<sUnassociatedStationStats> stats)
    {
NATIVE_FRAGMENT
    }

    void dispatch(const hal_event_cb_t &callback)
    {
        while (!queue.empty()) {
            auto event = queue.back();
            queue.pop_back();
            assert(callback(event));
        }
    }
};

std::vector<sUnassociatedStationStats> make_stats(std::size_t count, uint64_t seed)
{
    std::vector<sUnassociatedStationStats> stats(count);
    for (std::size_t index = 0; index < count; ++index) {
        auto &station = stats[index];
        station.mac_adress = {{2, 0, 0, 16, static_cast<uint8_t>(index), 0}};
        station.signal_strength = -90 + static_cast<int32_t>(index % 50);
        station.channel = 36;
        station.operating_class = 115;
        station.time_stamp = seed + index;
    }
    return stats;
}

void check_payload(const std::shared_ptr<void> &payload, std::size_t count, uint64_t seed)
{
    assert(payload);
    const auto &stats = static_cast<const sUnassociatedStationsStats *>(payload.get())->un_stations_stats;
    assert(stats.size() == count);
    for (std::size_t index = 0; index < count; ++index) {
        const auto &station = stats[index];
        assert(station.mac_adress.oct[0] == 2);
        assert(station.mac_adress.oct[3] == 16);
        assert(station.mac_adress.oct[4] == static_cast<uint8_t>(index));
        assert(station.signal_strength == -90 + static_cast<int32_t>(index % 50));
        assert(station.channel == 36);
        assert(station.operating_class == 115);
        assert(station.time_stamp == seed + index);
    }
}

std::size_t exercise(const char *scenario, std::size_t count, std::size_t burst)
{
    Hal hal;
    const bool retain = std::strcmp(scenario, "retain") == 0;
    const bool throw_callback = std::strcmp(scenario, "callback_throw") == 0;
    const bool fail_owner = std::strcmp(scenario, "owner_bad_alloc") == 0;
    const bool fail_queue = std::strcmp(scenario, "queue_bad_alloc") == 0;
    hal.fail_queue_allocation = fail_queue;
    for (std::size_t index = 0; index < burst; ++index) {
        auto stats = make_stats(count, 1000 + index);
        if (fail_owner) {
            allocations_before_failure = 0;
        }
        bool allocation_failed = false;
        try {
            assert(hal.publish(std::move(stats)) == (count != 0));
        } catch (const std::bad_alloc &) {
            allocation_failed = true;
        }
        allocations_before_failure = -1;
        assert(allocation_failed == ((fail_owner || fail_queue) && count != 0));
    }
    if (fail_owner || fail_queue || count == 0) {
        assert(hal.queue.empty());
        return 0;
    }
    assert(hal.queue.size() == burst);
    std::vector<hal_event_ptr_t> copied_events;
    std::vector<std::shared_ptr<void>> copied_payloads;
    std::vector<std::weak_ptr<void>> witnesses;
    std::size_t delivered = 0;
    const hal_event_cb_t callback = [&](hal_event_ptr_t event) {
        assert(event->first == Event::Unassociation_Stations_Stats);
        const auto seed = 1000 + burst - 1 - delivered;
        check_payload(event->second, count, seed);
        ++delivered;
        if (retain) {
            copied_events.push_back(event);
            auto erased_owner = event->second;
            copied_payloads.push_back(erased_owner);
            witnesses.push_back(erased_owner);
        }
        if (throw_callback) {
            throw CallbackFailure();
        }
        return true;
    };
    bool callback_failed = false;
    try {
        hal.dispatch(callback);
    } catch (const CallbackFailure &) {
        callback_failed = true;
    }
    assert(callback_failed == throw_callback);
    assert(hal.queue.empty());
    assert(delivered == burst);
    for (std::size_t index = 0; index < copied_payloads.size(); ++index) {
        const auto seed = 1000 + burst - 1 - index;
        check_payload(copied_payloads[index], count, seed);
        auto last_owner = copied_payloads[index];
        copied_payloads[index].reset();
        assert(!witnesses[index].expired());
        last_owner.reset();
        check_payload(copied_events[index]->second, count, seed);
        assert(!witnesses[index].expired());
        last_owner = copied_events[index]->second;
        copied_events[index].reset();
        check_payload(last_owner, count, seed);
        assert(!witnesses[index].expired());
        last_owner.reset();
        assert(witnesses[index].expired());
    }
    return delivered;
}

int main(int argc, char **argv)
{
    assert(argc == 4);
    const auto count = std::strtoul(argv[2], nullptr, 10);
    const auto burst = std::strtoul(argv[3], nullptr, 10);
    const auto baseline_blocks = live_blocks;
    const auto baseline_bytes = live_bytes;
    const auto delivered = exercise(argv[1], count, burst);
    const auto outstanding_blocks = live_blocks - baseline_blocks;
    const auto outstanding_bytes = live_bytes - baseline_bytes;
    std::printf("outstanding_blocks=%zu outstanding_bytes=%zu delivered=%zu\n",
                outstanding_blocks, outstanding_bytes, delivered);
    return outstanding_blocks == 0 && outstanding_bytes == 0 ? 0 : 42;
}
'''


@pytest.fixture(scope="module", params=[True, False], ids=["patched", "unpatched"])
def candidate_binary(request, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for candidate event ownership regression")
    directory = tmp_path_factory.mktemp("candidate-event-memory")
    program = directory / "candidate.cpp"
    program.write_text(HARNESS.replace("NATIVE_FRAGMENT", candidate_fragment(request.param)))
    binary = directory / "candidate"
    result = subprocess.run(
        [compiler, "-std=c++14", "-O0", "-Wall", "-Wextra", "-Werror",
         str(program), "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return binary, request.param


CASES = [
    ("discard", 0, 1),
    ("discard", 1, 1),
    ("discard", 9, 1),
    ("discard", 100, 1),
    ("discard", 100, 128),
    ("retain", 1, 1),
    ("retain", 9, 1),
    ("retain", 100, 1),
    ("retain", 100, 128),
    ("callback_throw", 100, 1),
    ("owner_bad_alloc", 0, 1),
    ("owner_bad_alloc", 100, 1),
    ("queue_bad_alloc", 100, 1),
]


@pytest.mark.parametrize("scenario,count,burst", CASES,
                         ids=[f"{scenario}-{count}-{burst}" for scenario, count, burst in CASES])
def test_candidate_event_ownership(candidate_binary, scenario, count, burst):
    binary, patched = candidate_binary
    result = subprocess.run([str(binary), scenario, str(count), str(burst)],
                            capture_output=True, text=True, timeout=5)
    expect_leak = not patched and count != 0 and scenario != "owner_bad_alloc"
    assert result.returncode == (42 if expect_leak else 0), result.stdout + result.stderr
    match = re.fullmatch(r"outstanding_blocks=(\d+) outstanding_bytes=(\d+) delivered=(\d+)\n",
                         result.stdout)
    assert match is not None, result.stdout
    blocks, size, delivered = map(int, match.groups())
    assert delivered == (0 if count == 0 or scenario.endswith("bad_alloc") else burst)
    if expect_leak:
        assert blocks == burst
        assert size >= count * 24 * burst
    else:
        assert blocks == 0
        assert size == 0
