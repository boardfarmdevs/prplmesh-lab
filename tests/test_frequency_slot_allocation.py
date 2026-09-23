from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches/wmediumd"
BASE = PATCHES / "0012-wmediumd-add-frequency-qualified-snr-control.patch"
FIX = PATCHES / "0035-wmediumd-linear-frequency-slot-allocation.patch"


def control_hunks(path):
    section = path.read_text().split("+++ b/wmediumd/control.c\n", 1)[1]
    section = section.split("\ndiff --git ", 1)[0].split("\n--- a/", 1)[0]
    hunks = []
    for line in section.splitlines(keepends=True):
        if line.startswith("@@ "):
            hunks.append(([], []))
        elif hunks and line.startswith((" ", "+", "-")):
            before, after = hunks[-1]
            if line[0] in " -":
                before.append(line[1:])
            if line[0] in " +":
                after.append(line[1:])
    assert hunks
    return [("".join(before), "".join(after)) for before, after in hunks]


def block(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        depth += (source[offset] == "{") - (source[offset] == "}")
        if depth == 0:
            return source[start:offset + 1]
    raise AssertionError(f"unterminated source block: {signature}")


def native_source(patched):
    source = "\n".join(after for _before, after in control_hunks(BASE))
    if patched:
        for before, after in control_hunks(FIX):
            assert source.count(before) == 1, "fix hunk must match the base source exactly"
            source = source.replace(before, after, 1)
    resolver = block(source, "static int resolve_frequency_links(")
    resolver, probes = re.subn(
        r"ctx->frequency_overrides\[([^\]]+)\]\.active",
        r"(allocation_step(), ctx->frequency_overrides[\1].active)",
        resolver,
    )
    assert probes == 1, "instrument the actual free-slot candidate inspection"
    helper = ""
    if "static bool slot_is_planned(" in source:
        helper = block(source, "static bool slot_is_planned(")
        expected = "if (resolved[i].override && resolved[i].slot == slot)"
        assert helper.count(expected) == 1
        helper = helper.replace(
            expected, "if ((allocation_step(), resolved[i].override) && resolved[i].slot == slot)"
        )
    return "\n".join((
        block(source, "struct resolved_frequency_update {") + ";",
        helper,
        resolver,
        block(source, "static int handle_frequency_apply("),
    ))


HARNESS = r'''
#include <assert.h>
#include <endian.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum {
    WMDC_OK, WMDC_ERR_PROTOCOL, WMDC_ERR_LENGTH, WMDC_ERR_GENERATION,
    WMDC_ERR_IDENTITY, WMDC_ERR_VALUE, WMDC_ERR_INTERNAL, WMDC_ERR_FREQUENCY
};
#define WMDC_FREQUENCY_OVERRIDE 1
#define WMDC_FREQUENCY_MIN_MHZ 2300U
#define WMDC_FREQUENCY_MAX_MHZ 7125U
#define WMDC_OP_APPLY_FREQUENCY 6

struct wmdc_frequency_link {
    uint8_t source[6], destination[6];
    uint32_t frequency_mhz;
    int16_t snr_db;
    uint16_t flags;
} __attribute__((packed));
struct wmd_frequency_override {
    int source, destination;
    uint32_t frequency_mhz;
    int snr_db;
    bool active;
};
struct wmediumd {
    struct wmd_frequency_override *frequency_overrides;
    size_t frequency_override_capacity;
    uint64_t control_generation;
};
struct wmdc_header { uint64_t generation; };
struct wmd_control_client {
    struct wmediumd *ctx;
    struct { int fd; } loop;
};

static uint64_t allocation_steps;
#ifdef COUNT_ALLOCATIONS
static uint64_t allocation_limit;
static jmp_buf allocation_jump;
#endif

static void allocation_step(void)
{
#ifdef COUNT_ALLOCATIONS
    ++allocation_steps;
    if (allocation_limit && allocation_steps > allocation_limit)
        longjmp(allocation_jump, 1);
#endif
}

static int station_index(struct wmediumd *context, const uint8_t *address)
{
    (void)context;
    if (address[0] != 0x42 || address[1] || address[2] || address[3])
        return -1;
    unsigned identity = ((unsigned)address[4] << 8) | address[5];
    return identity < 4096 ? (int)identity : -1;
}

static int frequency_override_slot(struct wmediumd *context, int source,
                                   int destination, uint32_t frequency)
{
    for (size_t index = 0; index < context->frequency_override_capacity; ++index) {
        const struct wmd_frequency_override *entry = &context->frequency_overrides[index];
        if (entry->active && entry->source == source && entry->destination == destination &&
            entry->frequency_mhz == frequency)
            return (int)index;
    }
    return -1;
}

static uint32_t response_status;
static uint64_t response_generation;
static size_t response_length;

static int send_response(int descriptor, uint16_t opcode, uint32_t status,
                         uint64_t generation, const void *payload, size_t length)
{
    (void)descriptor;
    assert(opcode == WMDC_OP_APPLY_FREQUENCY);
    assert(payload || !length);
    response_status = status;
    response_generation = generation;
    response_length = length;
    return 0;
}

NATIVE_SOURCE

static struct wmdc_frequency_link link_for(unsigned destination, int value, unsigned flags)
{
    struct wmdc_frequency_link link = {
        .source = {0x42, 0, 0, 0, 0, 0},
        .destination = {0x42, 0, 0, 0, destination >> 8, destination & 255},
        .frequency_mhz = htobe32(5180),
        .snr_db = (int16_t)htobe16((uint16_t)value),
        .flags = htobe16(flags),
    };
    return link;
}

static void seed(struct wmediumd *context, size_t slot, int destination, int value)
{
    context->frequency_overrides[slot] = (struct wmd_frequency_override){
        .source = 0, .destination = destination, .frequency_mhz = 5180,
        .snr_db = value, .active = true,
    };
}

static void submit(struct wmediumd *context, const void *payload, size_t length,
                   uint64_t requested_generation, uint32_t expected_status)
{
    size_t bytes = context->frequency_override_capacity * sizeof(*context->frequency_overrides);
    void *before = malloc(bytes);
    assert(before);
    memcpy(before, context->frequency_overrides, bytes);
    uint64_t generation = context->control_generation;
    struct wmd_control_client client = {.ctx = context};
    struct wmdc_header header = {.generation = htobe64(requested_generation)};
    response_status = UINT32_MAX;
    assert(handle_frequency_apply(&client, &header, payload, length) == 0);
    assert(response_status == expected_status);
    assert(context->control_generation == generation + (expected_status == WMDC_OK));
    assert(response_generation == context->control_generation);
    assert(response_length == (expected_status == WMDC_OK ? length : 0));
    if (expected_status != WMDC_OK)
        assert(memcmp(before, context->frequency_overrides, bytes) == 0);
    free(before);
}

static void apply(struct wmediumd *context, struct wmdc_frequency_link *links,
                  size_t count, uint32_t expected_status)
{
    submit(context, links, count * sizeof(*links), context->control_generation + 1,
           expected_status);
}

static int cold(void)
{
    const size_t count = 3060;
    struct wmd_frequency_override *entries = calloc(count, sizeof(*entries));
    struct wmdc_frequency_link *links = calloc(count, sizeof(*links));
    struct resolved_frequency_update *resolved = calloc(count, sizeof(*resolved));
    assert(entries && links && resolved);
    struct wmediumd context = {entries, count, 41};
    for (size_t index = 0; index < count; ++index)
        links[index] = link_for(index + 1, 50, WMDC_FREQUENCY_OVERRIDE);
#ifdef COUNT_ALLOCATIONS
    allocation_limit = 2 * count;
    if (setjmp(allocation_jump)) {
        for (size_t index = 0; index < count; ++index)
            assert(!entries[index].active);
        assert(context.control_generation == 41);
        printf("cold count=%zu allocation_steps=%" PRIu64 " budget=%zu exceeded\n",
               count, allocation_steps, 2 * count);
        free(resolved);
        free(links);
        free(entries);
        return 42;
    }
#endif
    struct timespec started, finished;
    assert(clock_gettime(CLOCK_MONOTONIC, &started) == 0);
    assert(resolve_frequency_links(&context, (const uint8_t *)links, count, resolved) == WMDC_OK);
    assert(clock_gettime(CLOCK_MONOTONIC, &finished) == 0);
    for (size_t index = 0; index < count; ++index) {
        assert(!entries[index].active);
        assert(resolved[index].slot == (int)index);
        assert(resolved[index].source == 0 && resolved[index].destination == (int)index + 1);
        assert(resolved[index].frequency_mhz == 5180 && resolved[index].snr_db == 50);
        assert(resolved[index].override);
    }
    assert(context.control_generation == 41);
    printf("cold count=%zu allocation_steps=%" PRIu64 " elapsed_seconds=%.6f\n",
           count, allocation_steps,
           finished.tv_sec - started.tv_sec + (finished.tv_nsec - started.tv_nsec) / 1e9);
    free(resolved);
    free(links);
    free(entries);
    return 0;
}

static void warm(void)
{
    const size_t count = 3060;
    struct wmd_frequency_override *entries = calloc(count, sizeof(*entries));
    struct wmdc_frequency_link *links = calloc(count, sizeof(*links));
    assert(entries && links);
    struct wmediumd context = {entries, count, 10};
    for (size_t index = 0; index < count; ++index) {
        seed(&context, index, index + 1, 30);
        links[index] = link_for(count - index, 45, WMDC_FREQUENCY_OVERRIDE);
    }
    apply(&context, links, count, WMDC_OK);
    for (size_t index = 0; index < count; ++index)
        assert(entries[index].active && entries[index].destination == (int)index + 1 &&
               entries[index].snr_db == 45);
    assert(allocation_steps == 0);
    free(links);
    free(entries);
}

static void holes(void)
{
    struct wmd_frequency_override entries[9] = {0};
    struct wmediumd context = {entries, 9, 20};
    const size_t occupied[] = {0, 2, 5, 8};
    const size_t vacant[] = {1, 3, 4, 6, 7};
    for (size_t index = 0; index < 4; ++index)
        seed(&context, occupied[index], 100 + index, 31);
    struct wmdc_frequency_link links[5];
    for (size_t index = 0; index < 5; ++index)
        links[index] = link_for(index + 1, 42, WMDC_FREQUENCY_OVERRIDE);
    apply(&context, links, 5, WMDC_OK);
    for (size_t index = 0; index < 4; ++index)
        assert(entries[occupied[index]].destination == (int)index + 100 &&
               entries[occupied[index]].snr_db == 31 && entries[occupied[index]].active);
    for (size_t index = 0; index < 5; ++index)
        assert(entries[vacant[index]].destination == (int)index + 1 &&
               entries[vacant[index]].active);
}

static void mixed(void)
{
    struct wmd_frequency_override entries[6] = {0};
    struct wmediumd context = {entries, 6, 30};
    seed(&context, 0, 100, 30);
    seed(&context, 2, 102, 32);
    seed(&context, 5, 105, 35);
    struct wmdc_frequency_link links[] = {
        link_for(100, 0, 0), link_for(102, 50, WMDC_FREQUENCY_OVERRIDE),
        link_for(1, 40, WMDC_FREQUENCY_OVERRIDE), link_for(2, 41, WMDC_FREQUENCY_OVERRIDE),
        link_for(999, 0, 0),
    };
    apply(&context, links, 5, WMDC_OK);
    assert(!entries[0].active && !entries[4].active);
    assert(entries[1].active && entries[1].destination == 1);
    assert(entries[3].active && entries[3].destination == 2);
    assert(entries[2].active && entries[2].destination == 102 && entries[2].snr_db == 50);
    assert(entries[5].active && entries[5].destination == 105 && entries[5].snr_db == 35);
}

static void full(void)
{
    struct wmd_frequency_override entries[4] = {0};
    struct wmediumd context = {entries, 4, 40};
    for (size_t index = 0; index < 4; ++index)
        seed(&context, index, 100 + index, 30);
    struct wmdc_frequency_link rejected[] = {
        link_for(101, 0, 0), link_for(1, 40, WMDC_FREQUENCY_OVERRIDE),
    };
    apply(&context, rejected, 2, WMDC_ERR_INTERNAL);
    struct wmdc_frequency_link accepted[] = {
        link_for(100, -20, WMDC_FREQUENCY_OVERRIDE), link_for(103, 60, WMDC_FREQUENCY_OVERRIDE),
        link_for(101, 0, 0),
    };
    apply(&context, accepted, 3, WMDC_OK);
    assert(entries[0].snr_db == -20 && entries[3].snr_db == 60 && !entries[1].active);
    apply(&context, &rejected[1], 1, WMDC_OK);
    assert(entries[1].active && entries[1].destination == 1);
}

static void invalid(void)
{
    for (unsigned scenario = 0; scenario < 11; ++scenario) {
        struct wmd_frequency_override entries[4] = {0};
        struct wmediumd context = {entries, 4, 50};
        seed(&context, 0, 100, 30);
        struct wmdc_frequency_link links[] = {
            link_for(1, 40, WMDC_FREQUENCY_OVERRIDE),
            link_for(2, 45, WMDC_FREQUENCY_OVERRIDE),
        };
        uint32_t expected = WMDC_ERR_VALUE;
        if (scenario == 0) links[1] = links[0];
        if (scenario == 1) {
            links[1].source[0] = 0x99;
            expected = WMDC_ERR_IDENTITY;
        }
        if (scenario == 2) {
            links[1].destination[0] = 0x99;
            expected = WMDC_ERR_IDENTITY;
        }
        if (scenario == 3) {
            memcpy(links[1].destination, links[1].source, 6);
            expected = WMDC_ERR_IDENTITY;
        }
        if (scenario == 4) links[1].flags = htobe16(2);
        if (scenario == 5 || scenario == 6) {
            links[1].frequency_mhz = htobe32(scenario == 5 ? 2299 : 7126);
            expected = WMDC_ERR_FREQUENCY;
        }
        if (scenario == 7 || scenario == 8)
            links[1].snr_db = (int16_t)htobe16((uint16_t)(scenario == 7 ? -21 : 61));
        if (scenario == 9) {
            links[1] = links[0];
            links[1].flags = 0;
        }
        if (scenario == 10) {
            links[0] = link_for(100, 0, 0);
            links[1] = links[0];
        }
        apply(&context, links, 2, expected);
    }
    struct wmd_frequency_override entries[4] = {0};
    struct wmediumd context = {entries, 4, 60};
    struct wmdc_frequency_link links[5];
    for (size_t index = 0; index < 5; ++index)
        links[index] = link_for(index + 1, 30, WMDC_FREQUENCY_OVERRIDE);
    apply(&context, links, 5, WMDC_ERR_LENGTH);
    apply(&context, links, 0, WMDC_ERR_LENGTH);
    submit(&context, links, sizeof(*links) - 1, 61, WMDC_ERR_LENGTH);
    submit(&context, links, sizeof(*links), 60, WMDC_ERR_GENERATION);
    submit(&context, links, sizeof(*links), 62, WMDC_ERR_GENERATION);
    struct resolved_frequency_update resolved = {0};
    context.frequency_overrides = NULL;
    assert(resolve_frequency_links(&context, (const uint8_t *)links, 1, &resolved) ==
           WMDC_ERR_INTERNAL);
    assert(context.control_generation == 60);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "cold")) return cold();
    if (!strcmp(argv[1], "warm")) warm();
    else if (!strcmp(argv[1], "holes")) holes();
    else if (!strcmp(argv[1], "mixed")) mixed();
    else if (!strcmp(argv[1], "full")) full();
    else if (!strcmp(argv[1], "invalid")) invalid();
    else return 2;
    printf("PASS %s allocation_steps=%" PRIu64 "\n", argv[1], allocation_steps);
    return 0;
}
'''


@pytest.fixture(scope="module", params=[False, True], ids=["original", "linear"])
def compiled_allocator(request, tmp_path_factory):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler required for frequency-slot allocation regression")
    directory = tmp_path_factory.mktemp("frequency-slot")
    program = directory / "allocation.c"
    program.write_text(HARNESS.replace("NATIVE_SOURCE", native_source(request.param)))
    binaries = {}
    for counted in (True, False):
        binary = directory / ("counted" if counted else "benchmark")
        result = subprocess.run(
            [compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-O2", "-Wall", "-Wextra", "-Werror",
             *(["-DCOUNT_ALLOCATIONS"] if counted else []), str(program), "-o", str(binary)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        binaries[counted] = binary
    return request.param, binaries


def test_cold_allocation_has_linear_reservation_budget(compiled_allocator):
    patched, binaries = compiled_allocator
    result = subprocess.run([str(binaries[True]), "cold"], capture_output=True, text=True, timeout=10)
    assert result.returncode == (0 if patched else 42), result.stdout + result.stderr
    assert ("budget=6120 exceeded" in result.stdout) is not patched
    print(("linear" if patched else "original negative control") + ": " + result.stdout.strip())


@pytest.mark.parametrize("scenario", ["warm", "holes", "mixed", "full", "invalid"])
def test_native_allocation_and_atomic_apply_semantics(compiled_allocator, scenario):
    _patched, binaries = compiled_allocator
    result = subprocess.run([str(binaries[True]), scenario], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cold_allocation_benchmark(compiled_allocator):
    patched, binaries = compiled_allocator
    result = subprocess.run([str(binaries[False]), "cold"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    print(("linear" if patched else "original") + " uninstrumented: " + result.stdout.strip())
