from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/prplmesh/0031-scope-neighbor-cache.patch"
SOURCE_PATH = "common/beerocks/bcl/source/network/network_utils.cpp"


def neighbor_fragment(patched):
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
    assert source.startswith("std::shared_ptr<std::unordered_map<std::string, std::string>>\n")
    assert source.endswith("\n}")
    return source


HARNESS = r'''
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <unordered_map>

bool fail_next_allocation = false;
void *operator new(std::size_t size)
{
    if (fail_next_allocation) {
        fail_next_allocation = false;
        throw std::bad_alloc();
    }
    auto pointer = std::malloc(size ? size : 1);
    if (!pointer) {
        throw std::bad_alloc();
    }
    return pointer;
}
void operator delete(void *pointer) noexcept { std::free(pointer); }
void *operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void *pointer) noexcept { ::operator delete(pointer); }
void operator delete(void *pointer, std::size_t) noexcept { ::operator delete(pointer); }
void operator delete[](void *pointer, std::size_t) noexcept { ::operator delete(pointer); }

constexpr int NETLINK_ROUTE = 0;
constexpr int AF_INET = 2;
constexpr int AF_INET6 = 10;
constexpr int NUD_NOARP = 64;
constexpr std::size_t MAC_ADDR_CHAR_SIZE = 17;
constexpr std::size_t IPV4_ADDR_CHAR_SIZE = 15;
struct LogSink {
    template <typename Value> LogSink &operator<<(const Value &) { return *this; }
};
#define LOG(level) LogSink()

const char *scenario = nullptr;
bool selected(const char *name) { return std::strcmp(scenario, name) == 0; }
unsigned sockets_allocated = 0;
unsigned sockets_freed = 0;
unsigned caches_allocated = 0;
unsigned caches_freed = 0;
unsigned hash_tables_allocated = 0;
unsigned hash_tables_freed = 0;

struct nl_sock {};
struct nl_addr { const char *text; bool is_ip; };
struct nl_object {
    int state;
    int family;
    nl_addr *mac;
    nl_addr *ip;
    nl_object *next;
};
using rtnl_neigh = nl_object;
struct nl_cache {
    int count;
    nl_object *first;
    unsigned char *hash_table;
};
nl_addr first_mac{"02:00:00:00:00:01", false};
nl_addr first_ip{"192.0.2.1", true};
nl_addr second_mac{"02:00:00:00:00:02", false};
nl_addr second_ip{"192.0.2.2", true};
nl_object neighbors[6];

nl_sock *nl_socket_alloc()
{
    if (selected("socket_failure")) {
        return nullptr;
    }
    ++sockets_allocated;
    return new nl_sock;
}
void nl_socket_free(nl_sock *socket)
{
    assert(socket);
    ++sockets_freed;
    assert(sockets_freed <= sockets_allocated);
    delete socket;
}
int nl_connect(nl_sock *, int) { return selected("connect_failure") ? -1 : 0; }
const char *nl_geterror(int) { return "injected failure"; }

int rtnl_neigh_alloc_cache(nl_sock *, nl_cache **output)
{
    assert(*output == nullptr);
    if (selected("cache_failure")) {
        return -1;
    }
    for (auto &neighbor : neighbors) {
        neighbor = {0, AF_INET, &first_mac, &first_ip, nullptr};
    }
    auto cache = new nl_cache{1, &neighbors[0], new unsigned char[8192]{}};
    ++caches_allocated;
    ++hash_tables_allocated;
    if (selected("empty") || selected("negative_count")) {
        cache->count = selected("empty") ? 0 : -1;
        cache->first = nullptr;
    } else if (selected("missing_first")) {
        cache->first = nullptr;
    } else if (selected("noarp")) {
        neighbors[0].state = NUD_NOARP;
    } else if (selected("ipv6")) {
        neighbors[0].family = AF_INET6;
    } else if (selected("missing_mac")) {
        neighbors[0].mac = nullptr;
    } else if (selected("missing_ip")) {
        neighbors[0].ip = nullptr;
    } else if (selected("truncated")) {
        cache->count = 3;
    } else if (selected("mixed")) {
        cache->count = 6;
        for (std::size_t index = 0; index < 5; ++index) {
            neighbors[index].next = &neighbors[index + 1];
        }
        neighbors[1].state = NUD_NOARP;
        neighbors[2].family = AF_INET6;
        neighbors[3].mac = nullptr;
        neighbors[4].ip = nullptr;
        neighbors[5].mac = &second_mac;
        neighbors[5].ip = &second_ip;
    }
    *output = cache;
    return 0;
}
void nl_cache_free(nl_cache *cache)
{
    assert(cache && cache->hash_table);
    ++caches_freed;
    ++hash_tables_freed;
    assert(caches_freed <= caches_allocated);
    delete[] cache->hash_table;
    delete cache;
}
int nl_cache_nitems(nl_cache *cache) { return cache->count; }
nl_object *nl_cache_get_first(nl_cache *cache) { return cache->first; }
nl_object *nl_cache_get_next(nl_object *neighbor) { return neighbor->next; }
int rtnl_neigh_get_state(rtnl_neigh *neighbor) { return neighbor->state; }
int rtnl_neigh_get_family(rtnl_neigh *neighbor) { return neighbor->family; }
nl_addr *rtnl_neigh_get_lladdr(rtnl_neigh *neighbor) { return neighbor->mac; }
nl_addr *rtnl_neigh_get_dst(rtnl_neigh *neighbor) { return neighbor->ip; }
char *nl_addr2str(nl_addr *address, char *buffer, std::size_t size)
{
    assert(std::strlen(address->text) < size);
    std::strcpy(buffer, address->text);
    if (address->is_ip && selected("map_bad_alloc")) {
        fail_next_allocation = true;
    }
    return buffer;
}

struct network_utils {
    static std::shared_ptr<std::unordered_map<std::string, std::string>> get_arp_table(bool);
};

NATIVE_FRAGMENT

int main(int argc, char **argv)
{
    assert(argc == 5);
    scenario = argv[1];
    const auto iterations = std::strtoul(argv[2], nullptr, 10);
    const bool mac_as_key = std::strcmp(argv[3], "mac") == 0;
    const auto expected_size = std::strtoul(argv[4], nullptr, 10);
    unsigned exceptions = 0;
    for (std::size_t iteration = 0; iteration < iterations; ++iteration) {
        std::shared_ptr<std::unordered_map<std::string, std::string>> table;
        bool allocation_failed = false;
        try {
            table = network_utils::get_arp_table(mac_as_key);
        } catch (const std::bad_alloc &) {
            allocation_failed = true;
            ++exceptions;
        }
        assert(allocation_failed == selected("map_bad_alloc"));
        assert(!fail_next_allocation);
        const bool expect_null = allocation_failed || selected("socket_failure") ||
            selected("connect_failure") || selected("cache_failure") || selected("missing_first");
        assert(static_cast<bool>(table) == !expect_null);
        if (table) {
            assert(table->size() == expected_size);
            if (expected_size) {
                assert(table->at(mac_as_key ? first_mac.text : first_ip.text) ==
                       (mac_as_key ? first_ip.text : first_mac.text));
            }
            if (expected_size == 2) {
                assert(table->at(mac_as_key ? second_mac.text : second_ip.text) ==
                       (mac_as_key ? second_ip.text : second_mac.text));
            }
        }
        assert(sockets_allocated == sockets_freed);
    }
    assert(caches_allocated == hash_tables_allocated);
    assert(caches_freed == hash_tables_freed);
    std::printf("cache_allocations=%u cache_frees=%u hash_allocations=%u hash_frees=%u exceptions=%u\n",
                caches_allocated, caches_freed, hash_tables_allocated, hash_tables_freed, exceptions);
    return caches_allocated == caches_freed ? 0 : 42;
}
'''


@pytest.fixture(scope="module", params=[True, False], ids=["patched", "unpatched"])
def neighbor_binary(request, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler required for neighbor cache ownership regression")
    directory = tmp_path_factory.mktemp("neighbor-cache-memory")
    program = directory / "neighbor.cpp"
    program.write_text(HARNESS.replace("NATIVE_FRAGMENT", neighbor_fragment(request.param)))
    binary = directory / "neighbor"
    result = subprocess.run(
        [compiler, "-std=c++14", "-O0", "-Wall", "-Wextra", "-Werror",
         str(program), "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return binary, request.param


CASES = [
    ("socket_failure", 1, "mac", 0),
    ("connect_failure", 1, "mac", 0),
    ("cache_failure", 1, "mac", 0),
    ("empty", 1, "mac", 0),
    ("empty", 64, "mac", 0),
    ("negative_count", 1, "mac", 0),
    ("missing_first", 1, "mac", 0),
    ("populated", 1, "mac", 1),
    ("populated", 64, "ip", 1),
    ("noarp", 1, "mac", 0),
    ("ipv6", 1, "mac", 0),
    ("missing_mac", 1, "mac", 0),
    ("missing_ip", 1, "mac", 0),
    ("truncated", 1, "mac", 1),
    ("mixed", 1, "mac", 2),
    ("mixed", 1, "ip", 2),
    ("map_bad_alloc", 16, "mac", 0),
    ("map_bad_alloc", 16, "ip", 0),
]


@pytest.mark.parametrize("scenario,iterations,key,size", CASES,
                         ids=[f"{name}-{count}-{key}" for name, count, key, _ in CASES])
def test_neighbor_cache_ownership(neighbor_binary, scenario, iterations, key, size):
    binary, patched = neighbor_binary
    result = subprocess.run([str(binary), scenario, str(iterations), key, str(size)],
                            capture_output=True, text=True, timeout=5)
    expect_leak = not patched and scenario in {"empty", "negative_count", "map_bad_alloc"}
    assert result.returncode == (42 if expect_leak else 0), result.stdout + result.stderr
    match = re.fullmatch(
        r"cache_allocations=(\d+) cache_frees=(\d+) hash_allocations=(\d+) hash_frees=(\d+) exceptions=(\d+)\n",
        result.stdout,
    )
    assert match is not None, result.stdout
    allocated, freed, hash_allocated, hash_freed, exceptions = map(int, match.groups())
    assert allocated == hash_allocated
    assert freed == hash_freed
    assert allocated == (0 if scenario.endswith("failure") else iterations)
    assert allocated - freed == (iterations if expect_leak else 0)
    assert exceptions == (iterations if scenario == "map_bad_alloc" else 0)
