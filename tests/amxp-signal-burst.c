#define _GNU_SOURCE
#include <assert.h>
#include <poll.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <amxc/amxc.h>
#include <amxp/amxp.h>

static const unsigned burst_size = 100000;

static void received(const char* name, const amxc_var_t* data, void* private_data) {
    unsigned* count = private_data;
    (void) name;
    (void) data;
    ++*count;
}

static void deferred(const amxc_var_t* data, void* private_data) {
    received(NULL, data, private_data);
}

static int ready(void) {
    struct pollfd descriptor = {.fd = amxp_signal_fd(), .events = POLLIN};
    return poll(&descriptor, 1, 0);
}

static void drain(unsigned expected) {
    for(unsigned index = 0; index < expected; ++index) {
        assert(ready() == 1);
        assert(amxp_signal_read() == 0);
    }
    assert(ready() == 0);
    assert(amxp_signal_read() == -1);
}

static void* produce(void* private_data) {
    amxp_signal_mngr_t* manager = private_data;
    for(unsigned index = 0; index < burst_size; ++index) {
        assert(amxp_sigmngr_emit_signal(manager, "burst", NULL) == 0);
    }
    return NULL;
}

int main(void) {
    amxp_signal_mngr_t* manager = NULL;
    amxp_signal_mngr_t* other = NULL;
    unsigned signals = 0;
    unsigned other_signals = 0;
    unsigned deferred_calls = 0;
    pthread_t producers[2];
    assert(amxp_sigmngr_new(&manager) == 0);
    assert(amxp_sigmngr_new(&other) == 0);
    assert(amxp_sigmngr_add_signal(manager, "burst") == 0);
    assert(amxp_sigmngr_add_signal(other, "burst") == 0);
    assert(amxp_slot_connect(manager, "burst", NULL, received, &signals) == 0);
    assert(amxp_slot_connect(other, "burst", NULL, received, &other_signals) == 0);
    produce(manager);
    drain(burst_size);
    assert(signals == burst_size);

    produce(manager);
    assert(amxp_sigmngr_suspend(manager) == 0);
    assert(ready() == 0);
    produce(other);
    drain(burst_size);
    assert(other_signals == burst_size);
    assert(amxp_sigmngr_resume(manager) == 0);
    drain(burst_size);
    assert(signals == burst_size * 2);

    assert(amxp_sigmngr_suspend(manager) == 0);
    for(unsigned index = 0; index < burst_size; ++index) {
        assert(amxp_sigmngr_deferred_call(manager, deferred, NULL, &deferred_calls) == 0);
    }
    assert(ready() == 0);
    assert(amxp_sigmngr_resume(manager) == 0);
    drain(burst_size);
    assert(deferred_calls == burst_size);
    assert(amxp_sigmngr_suspend(manager) == 0);
    assert(amxp_sigmngr_resume(manager) == 0);
    assert(ready() == 0);

    for(unsigned index = 0; index < 2; ++index) {
        assert(pthread_create(&producers[index], NULL, produce, manager) == 0);
    }
    for(unsigned index = 0; index < 2; ++index) {
        assert(pthread_join(producers[index], NULL) == 0);
    }
    drain(burst_size * 2);
    assert(signals == burst_size * 4);
    produce(manager);
    produce(other);
    assert(amxp_sigmngr_delete(&manager) == 0);
    drain(burst_size);
    assert(other_signals == burst_size * 2);
    produce(other);
    assert(amxp_sigmngr_delete(&other) == 0);
    assert(ready() == 0);
    puts("PASS: lossless signal bursts, deferred calls, suspension, cleanup and concurrent producers");
    return 0;
}
