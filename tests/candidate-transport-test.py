#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


def harness(source):
    function = source[source.index('bool mon_wlan_hal_nl80211::sta_unassoc_rssi_measurement('):]
    definitions = function[function.index('    enum {'):function.index('    if (new_list.empty())')]
    reader = function[function.index('    auto read_snr ='):function.index('    auto now =')]
    exchange = function[function.index('    auto exchange ='):function.index('    request.header.magic =')]
    failure = function[function.index('        if (!read_snr('):function.index('        stats.push_back(')]
    assert 'close(fd);' in failure and 'return false;' in failure and 'continue;' not in failure
    return r'''
#include <arpa/inet.h>
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <iostream>
#include <pthread.h>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <thread>
#include <unistd.h>
#include <vector>
#define LOG(level) std::cerr
''' + definitions + r'''
std::string mode;
std::deque<std::vector<uint8_t>> replies;
std::vector<long> budgets;
int sends = 0;
int receives = 0;
int delivered = 0;
bool real_socket = false;
auto system_send = &::send;
auto system_recv = &::recv;
auto system_setsockopt = &::setsockopt;
std::string get_iface_name() { return "test-radio"; }
int candidate_setsockopt(int descriptor, int level, int option, const void *value, size_t length)
{
    const auto *budget = static_cast<const timeval *>(value);
    budgets.push_back(budget->tv_sec * 1000000 + budget->tv_usec);
    if (real_socket) return system_setsockopt(descriptor, level, option, value, length);
    return 0;
}
ssize_t candidate_send(int descriptor, const void *buffer, size_t length, int flags)
{
    assert(flags & MSG_NOSIGNAL);
    sends++;
    if (real_socket) {
        auto result = system_send(descriptor, buffer, length, flags);
        if (result == static_cast<ssize_t>(length)) delivered++;
        return result;
    }
    if (mode == "send-interrupt" && sends == 1) { errno = EINTR; return -1; }
    if (mode == "short-send") return length - 1;
    const auto *request = static_cast<const wmdc_request *>(buffer);
    auto response = *request;
    response.header.status = htonl(WMDC_OK);
    response.link.snr_db = htons(request->link.source[5] * 20);
    const auto *bytes = reinterpret_cast<const uint8_t *>(&response);
    replies.emplace_back(bytes, bytes + sizeof(response));
    delivered++;
    return length;
}
ssize_t candidate_recv(int descriptor, void *buffer, size_t capacity, int flags)
{
    receives++;
    if (real_socket) return system_recv(descriptor, buffer, capacity, flags);
    if (mode == "recv-interrupt" && receives == 1) { errno = EINTR; return -1; }
    if (mode == "signal-storm") {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
        errno = EINTR;
        return -1;
    }
    if (mode == "late-reply") { errno = EAGAIN; return -1; }
    assert(!replies.empty() && capacity >= replies.front().size());
    auto response = replies.front();
    replies.pop_front();
    auto *message = reinterpret_cast<wmdc_request *>(response.data());
    if (mode == "wrong-source") message->link.source[5]++;
    if (mode == "wrong-destination") message->link.destination[5]++;
    if (mode == "wrong-frequency") message->link.frequency_mhz = htonl(2412);
    if (mode == "wrong-opcode") message->header.opcode = htons(WMDC_OP_HELLO);
    if (mode == "wrong-status") message->header.status = htonl(1);
    if (mode == "short-reply") response.pop_back();
    std::memcpy(buffer, response.data(), response.size());
    return response.size();
}
#define setsockopt candidate_setsockopt
#define send candidate_send
#define recv candidate_recv
int main()
{
    int fd = 42;
    unsigned int destination_octets[6] = {2, 0, 0, 0, 0, 1};
    wmdc_request request{};
    uint8_t response[sizeof(wmdc_header) + sizeof(wmdc_info)]{};
    auto header = reinterpret_cast<wmdc_header *>(response);
    auto link = reinterpret_cast<wmdc_frequency_link *>(response + sizeof(*header));
''' + exchange + reader + r'''
    for (const auto &scenario : {"normal", "send-interrupt", "recv-interrupt", "wrong-source",
         "wrong-destination", "wrong-frequency", "wrong-opcode", "wrong-status", "short-reply",
         "short-send", "late-reply", "signal-storm", "real-interrupt", "real-timeout"}) {
        mode = scenario;
        replies.clear();
        budgets.clear();
        sends = receives = delivered = 0;
        real_socket = mode == "real-interrupt" || mode == "real-timeout";
        int descriptors[2] = {-1, -1};
        std::thread server;
        if (real_socket) {
            assert(socketpair(AF_UNIX, SOCK_SEQPACKET, 0, descriptors) == 0);
            fd = descriptors[0];
            struct sigaction action{};
            action.sa_handler = [](int) {};
            sigemptyset(&action.sa_mask);
            assert(sigaction(SIGUSR1, &action, nullptr) == 0);
            auto client_thread = pthread_self();
            server = std::thread([&] {
                for (int attempt = 0; attempt < (mode == "real-interrupt" ? 2 : 1); attempt++) {
                    wmdc_request request{};
                    assert(system_recv(descriptors[1], &request, sizeof(request), 0) == sizeof(request));
                    if (mode == "real-timeout") {
                        std::this_thread::sleep_for(std::chrono::milliseconds(1200));
                        return;
                    }
                    if (attempt == 0) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(20));
                        assert(pthread_kill(client_thread, SIGUSR1) == 0);
                        std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    }
                    request.link.snr_db = htons(request.link.source[5] * 20);
                    assert(system_send(descriptors[1], &request, sizeof(request), MSG_NOSIGNAL) == sizeof(request));
                }
            });
        }
        int16_t first_snr = -1;
        int16_t second_snr = -1;
        auto started = std::chrono::steady_clock::now();
        bool first_ok = read_snr("02:00:00:00:00:01", 5180, first_snr);
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - started).count();
        bool success = mode == "normal" || mode == "send-interrupt" || mode == "recv-interrupt" || mode == "real-interrupt";
        assert(first_ok == success);
        if (success) {
            assert(first_snr == 20);
            assert(read_snr("02:00:00:00:00:02", 5180, second_snr) && second_snr == 40);
            assert(delivered == 2 && replies.empty());
        } else {
            assert(first_snr == -1 && delivered <= 1);
        }
        if (mode == "signal-storm") {
            assert(errno == ETIMEDOUT && elapsed >= 990 && elapsed < 1500 && delivered == 1);
            assert(std::is_sorted(budgets.rbegin(), budgets.rend()));
        }
        if (mode == "real-timeout") assert(elapsed >= 990 && elapsed < 1500 && delivered == 1);
        if (mode == "real-interrupt") assert(receives >= 3);
        if (server.joinable()) {
            server.join();
            close(descriptors[0]);
            close(descriptors[1]);
        }
        std::cout << "PASS " << mode << "\n";
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description='Compile the assembled HAL transaction with deterministic syscall faults')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='prpl-candidate-transport-') as directory:
        root = Path(directory)
        source = root / 'test.cpp'
        source.write_text(harness(args.source.read_text()))
        binary = root / 'test'
        subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O2', '-pthread',
                        str(source), '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
