#!/usr/bin/env python3
import argparse
from pathlib import Path
import resource
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == '{':
            depth += 1
        elif source[offset] == '}':
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise ValueError(f'incomplete function: {signature}')


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __hidden
#define container_of(pointer, type, member) ((type *)((char *)(pointer) - offsetof(type, member)))
struct list_head { struct list_head *next, *prev; };
static void list_init(struct list_head *head) { head->next = head->prev = head; }
static bool list_empty(struct list_head *head) { return head->next == head; }
static void list_add_tail(struct list_head *node, struct list_head *head) {
    node->prev = head->prev; node->next = head;
    head->prev->next = node; head->prev = node;
}
static void list_del(struct list_head *node) {
    node->prev->next = node->next; node->next->prev = node->prev;
}
#define list_first_entry(head, type, member) container_of((head)->next, type, member)
#define list_for_each_entry_safe(entry, next_entry, head, member) \
    for (entry = list_first_entry(head, __typeof__(*entry), member), \
         next_entry = list_first_entry(&entry->member, __typeof__(*entry), member); \
         &entry->member != (head); entry = next_entry, \
         next_entry = list_first_entry(&entry->member, __typeof__(*entry), member))
enum { UBUS_MSG_STATUS, UBUS_MSG_DATA, UBUS_MSG_INVOKE, UBUS_MSG_UNSUBSCRIBE,
       UBUS_MSG_NOTIFY, UBUS_MSG_MONITOR };
struct ubus_msghdr { int type, seq; };
struct ubus_msghdr_buf { struct ubus_msghdr hdr; void *data; };
struct uloop_timeout { void (*cb)(struct uloop_timeout *); };
struct uloop_fd { bool eof; };
struct ubus_context {
    int stack_depth;
    bool cancel_poll;
    struct list_head pending;
    struct uloop_timeout pending_timer;
    struct uloop_fd sock;
    struct ubus_msghdr_buf msgbuf;
    void (*monitor_cb)(struct ubus_context *, int, void *);
    void (*connection_lost)(struct ubus_context *);
};
struct ubus_pending_msg { struct list_head list; struct ubus_msghdr_buf hdr; };
static unsigned processed[4], retired[4], incoming, disconnected;
static struct ubus_pending_msg *allocated[4];
static const char *scenario;
static void ubus_process_pending_msg(struct uloop_timeout *timeout);
void ubus_process_msg(struct ubus_context *, struct ubus_msghdr_buf *, int);
static void ubus_queue_msg(struct ubus_context *context, struct ubus_msghdr_buf *message) {
    struct ubus_pending_msg *pending = calloc(1, sizeof(*pending));
    assert(pending && !allocated[message->hdr.seq]);
    allocated[message->hdr.seq] = pending;
    pending->hdr = *message;
    list_add_tail(&pending->list, &context->pending);
}
static void release_pending(void *pointer) {
    struct ubus_pending_msg *pending = pointer;
    assert(++retired[pending->hdr.hdr.seq] == 1);
}
static void ubus_process_req_msg(struct ubus_context *context, struct ubus_msghdr_buf *message, int descriptor) {
    assert(++processed[message->hdr.seq] == 1);
    if (message->hdr.seq == 1 && !strcmp(scenario, "recursive-queue"))
        ubus_process_pending_msg(&context->pending_timer);
}
static void ubus_process_obj_msg(struct ubus_context *context, struct ubus_msghdr_buf *message, int descriptor) {
    assert(++processed[message->hdr.seq] == 1);
    if (message->hdr.seq == 1 && !strcmp(scenario, "nested-dispatch")) {
        struct ubus_msghdr_buf nested = {.hdr = {UBUS_MSG_INVOKE, 2}};
        ubus_process_msg(context, &nested, -1);
        assert(processed[2] == 0 && !list_empty(&context->pending));
        context->pending_timer.cb(&context->pending_timer);
        assert(processed[2] == 0);
        context->cancel_poll = true;
    }
}
static bool get_next_msg(struct ubus_context *context, int *descriptor) {
    if (!incoming) return false;
    incoming--;
    context->msgbuf.hdr = (struct ubus_msghdr){UBUS_MSG_INVOKE, 1};
    return true;
}
static bool uloop_cancelling(void) { return false; }
static void connection_lost(struct ubus_context *context) { disconnected++; }
#define free release_pending
'''

MAIN = r'''
#undef free
int main(int count, char **arguments) {
    assert(count == 2);
    scenario = arguments[1];
    struct ubus_context context = {.pending_timer.cb = ubus_process_pending_msg,
                                   .connection_lost = connection_lost};
    list_init(&context.pending);
    if (!strcmp(scenario, "recursive-queue")) {
        for (int sequence = 1; sequence <= 3; sequence++) {
            struct ubus_msghdr_buf message = {.hdr = {UBUS_MSG_STATUS, sequence}};
            ubus_queue_msg(&context, &message);
        }
        ubus_process_pending_msg(&context.pending_timer);
        for (int sequence = 1; sequence <= 3; sequence++)
            assert(processed[sequence] == 1 && retired[sequence] == 1);
    } else if (!strcmp(scenario, "nested-dispatch")) {
        incoming = 1;
        ubus_handle_data(&context.sock, 0);
        assert(processed[1] == 1 && processed[2] == 1 && !context.stack_depth);
    } else if (!strcmp(scenario, "empty-socket") || !strcmp(scenario, "busy-context")) {
        struct ubus_msghdr_buf message = {.hdr = {UBUS_MSG_INVOKE, 1}};
        ubus_queue_msg(&context, &message);
        if (!strcmp(scenario, "busy-context")) {
            context.stack_depth = 1;
            ubus_handle_data(&context.sock, 0);
            assert(processed[1] == 0 && !list_empty(&context.pending));
            context.stack_depth = 0;
        }
        ubus_handle_data(&context.sock, 0);
        assert(processed[1] == 1 && retired[1] == 1);
    } else {
        assert(!strcmp(scenario, "disconnect"));
        context.sock.eof = true;
        ubus_handle_data(&context.sock, 0);
        assert(disconnected == 1);
    }
    assert(list_empty(&context.pending));
    for (int sequence = 1; sequence <= 3; sequence++) free(allocated[sequence]);
    printf("PASS %s\n", scenario);
}
'''


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser = argparse.ArgumentParser(description='Compile actual libubus dispatch with controlled reentrant callbacks.')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    message = (args.source / 'libubus.c').read_text()
    dispatch = (args.source / 'libubus-io.c').read_text()
    functions = '\n'.join([
        function(message, 'void __hidden\nubus_process_msg('),
        function(message, 'static void ubus_process_pending_msg('),
        function(dispatch, 'void __hidden ubus_handle_data('),
    ])
    with tempfile.TemporaryDirectory(prefix='ubus-dispatch-') as directory:
        source = Path(directory) / 'dispatch.c'
        binary = Path(directory) / 'dispatch'
        source.write_text(HARNESS + functions + MAIN)
        subprocess.run(['gcc', '-std=gnu11', '-O1', '-Wall', '-Werror', str(source), '-o', str(binary)], check=True)
        for scenario in ['recursive-queue', 'nested-dispatch', 'empty-socket', 'busy-context', 'disconnect']:
            subprocess.run([str(binary), scenario], check=True, timeout=5)


if __name__ == '__main__':
    main()
