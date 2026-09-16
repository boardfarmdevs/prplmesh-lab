#include "netlink_socket.h"

#include <cassert>
#include <cerrno>
#include <chrono>
#include <iostream>
#include <linux/genetlink.h>
#include <netlink/errno.h>
#include <netlink/genl/genl.h>
#include <netlink/msg.h>
#include <netlink/netlink.h>

static int receive_failure = 0;
static int send_failure = 0;

extern "C" int __real_nl_recvmsgs(struct nl_sock *, struct nl_cb *);
extern "C" int __wrap_nl_recvmsgs(struct nl_sock *socket, struct nl_cb *callbacks)
{
    if (receive_failure != 0) {
        const int failure = receive_failure;
        receive_failure = 0;
        return failure;
    }
    return __real_nl_recvmsgs(socket, callbacks);
}

extern "C" int __real_nl_send_auto_complete(struct nl_sock *, struct nl_msg *);
extern "C" int __wrap_nl_send_auto_complete(struct nl_sock *socket, struct nl_msg *message)
{
    if (send_failure != 0) {
        const int failure = send_failure;
        send_failure = 0;
        return failure;
    }
    return __real_nl_send_auto_complete(socket, message);
}

static bool query(bwl::netlink_socket &socket, const char *family, int &responses)
{
    return socket.send_receive_msg(
        [&](struct nl_msg *message) {
            return genlmsg_put(message, NL_AUTO_PORT, NL_AUTO_SEQ, GENL_ID_CTRL, 0, 0,
                               CTRL_CMD_GETFAMILY, 1) != nullptr &&
                   nla_put_string(message, CTRL_ATTR_FAMILY_NAME, family) == 0;
        },
        [&](struct nl_msg *) { responses++; });
}

int main()
{
    bwl::netlink_socket socket(NETLINK_GENERIC);
    assert(socket.connect());
    int responses = 0;
    assert(query(socket, "nlctrl", responses) && responses > 0);
    for (const int failure : {-NLE_SEQ_MISMATCH, -NLE_NOMEM, -NLE_DUMP_INTR, -NLE_AGAIN}) {
        responses = 0;
        receive_failure = failure;
        assert(!query(socket, "nlctrl", responses));
        assert(responses == 0);
        assert(query(socket, "nlctrl", responses) && responses > 0);
        std::cout << "PASS: receive fault " << failure << " rejects sample and recovers\n";
    }
    responses = 0;
    send_failure = -NLE_BAD_SOCK;
    assert(!query(socket, "nlctrl", responses));
    assert(query(socket, "nlctrl", responses) && responses > 0);
    std::cout << "PASS: send failure recovers\n";
    responses = 0;
    assert(!query(socket, "absent-rf-test", responses));
    assert(responses == 0);
    assert(query(socket, "nlctrl", responses) && responses > 0);
    std::cout << "PASS: kernel rejection recovers\n";
    for (int index = 0; index < 100; index++) {
        responses = 0;
        assert(query(socket, "nlctrl", responses) && responses > 0);
    }
    std::cout << "PASS: 100 consecutive real netlink transactions\n";
}
