#include <chrono>
#include <bcl/beerocks_defines.h>
#include <tlvf/CmduMessageRx.h>
#include <tlvf/CmduMessageTx.h>
#include <tlvf/tlvftypes.h>
#include <tlvf/wfa_map/tlvApMetrics.h>
#include <tlvf/wfa_map/tlvApExtendedMetrics.h>
#include <tlvf/wfa_map/tlvAssociatedStaTrafficStats.h>
#include <tlvf/wfa_map/tlvAssociatedStaLinkMetrics.h>
#include <tlvf/wfa_map/tlvAssociatedStaExtendedLinkMetrics.h>
#include <tlvf/wfa_map/tlvAssociatedWiFi6StaStatusReport.h>
#include <tlvf/wfa_map/tlvProfile2RadioMetrics.h>

#include <cstdlib>
#include <iostream>
#include <set>
#include <vector>

void require(bool condition, const char *message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

bool round_trip(size_t capacity, size_t station_count, size_t bss_count)
{
    std::vector<uint8_t> buffer(capacity);
    ieee1905_1::CmduMessageTx outgoing(buffer.data(), buffer.size());
    if (!outgoing.create(42, ieee1905_1::eMessageType::AP_METRICS_RESPONSE_MESSAGE)) {
        return false;
    }
    for (size_t index = 0; index < bss_count; ++index) {
        auto ap = outgoing.addClass<wfa_map::tlvApMetrics>();
        if (!ap || !ap->alloc_estimated_service_info_field(3)) {
            return false;
        }
        ap->bssid().oct[5] = index;
        auto extended = outgoing.addClass<wfa_map::tlvApExtendedMetrics>();
        if (!extended) {
            return false;
        }
        extended->bssid() = ap->bssid();
    }
    for (size_t index = 0; index < station_count; ++index) {
        sMacAddr station{};
        station.oct[0] = 2;
        station.oct[5] = index;
        auto traffic = outgoing.addClass<wfa_map::tlvAssociatedStaTrafficStats>();
        if (!traffic) {
            return false;
        }
        traffic->sta_mac() = station;
        traffic->byte_sent() = 1000 + index;
        auto extended = outgoing.addClass<wfa_map::tlvAssociatedStaExtendedLinkMetrics>();
        if (!extended) {
            return false;
        }
        extended->associated_sta() = station;
        auto link = outgoing.addClass<wfa_map::tlvAssociatedStaLinkMetrics>();
        if (!link || !link->alloc_bssid_info_list(1)) {
            return false;
        }
        link->sta_mac() = station;
        auto &info = std::get<1>(link->bssid_info_list(0));
        info.bssid.oct[5] = index % bss_count;
        info.sta_measured_uplink_rcpi_dbm_enc = 90 + index % 20;
        auto status = outgoing.addClass<wfa_map::tlvAssociatedWiFi6StaStatusReport>();
        if (!status || !status->alloc_tid_queue_size_list(IEEE80211_QOS_TID_MAX_UP)) {
            return false;
        }
        status->sta_mac() = station;
        for (size_t tid = 0; tid < IEEE80211_QOS_TID_MAX_UP; ++tid) {
            auto &queue = std::get<1>(status->tid_queue_size_list(tid));
            queue.tid = tid;
            queue.queue_size = index + tid;
        }
    }
    for (size_t index = 0; index < 3; ++index) {
        if (!outgoing.addClass<wfa_map::tlvProfile2RadioMetrics>()) {
            return false;
        }
    }
    if (!outgoing.finalize()) {
        return false;
    }
    require(outgoing.getMessageLength() + 40 < capacity, "broker envelope exceeds capacity");
    ieee1905_1::CmduMessageRx incoming(buffer.data(), outgoing.getMessageLength());
    require(incoming.parse(), "failed to parse complete native CMDU");
    require(incoming.getMessageId() == 42, "response MID changed");
    require(incoming.getClassList<wfa_map::tlvApMetrics>().size() == bss_count, "missing BSS metrics");
    auto traffic = incoming.getClassList<wfa_map::tlvAssociatedStaTrafficStats>();
    auto links = incoming.getClassList<wfa_map::tlvAssociatedStaLinkMetrics>();
    auto statuses = incoming.getClassList<wfa_map::tlvAssociatedWiFi6StaStatusReport>();
    require(traffic.size() == station_count, "missing traffic counters");
    require(links.size() == station_count, "missing link metrics");
    require(statuses.size() == station_count, "missing TID status");
    require(incoming.getClassList<wfa_map::tlvAssociatedStaExtendedLinkMetrics>().size()
                == station_count, "missing extended link metrics");
    std::set<unsigned> identities;
    for (const auto &row : traffic) {
        identities.insert(row->sta_mac().oct[5]);
        require(row->byte_sent() == 1000U + row->sta_mac().oct[5], "changed traffic counter");
    }
    require(identities.size() == station_count, "duplicate stations");
    for (const auto &row : links) {
        auto &info = std::get<1>(row->bssid_info_list(0));
        require(info.sta_measured_uplink_rcpi_dbm_enc == 90 + row->sta_mac().oct[5] % 20,
                "changed RCPI");
    }
    for (const auto &row : statuses) {
        require(row->tid_queue_size_list_length() == IEEE80211_QOS_TID_MAX_UP, "missing TIDs");
        for (size_t tid = 0; tid < IEEE80211_QOS_TID_MAX_UP; ++tid) {
            auto &queue = std::get<1>(row->tid_queue_size_list(tid));
            require(queue.tid == tid && queue.queue_size == row->sta_mac().oct[5] + tid,
                    "changed TID counters");
        }
    }
    std::cout << "PASS stations=" << station_count << " BSS=" << bss_count
              << " capacity=" << capacity << " bytes=" << outgoing.getMessageLength() << '\n';
    return true;
}

int main()
{
    require(round_trip(8192, 20, 9), "20-client baseline failed");
    require(!round_trip(8192, 100, 9), "old buffer unexpectedly fits full roster");
    for (size_t bss_count : {1U, 9U, 15U}) {
        require(round_trip(beerocks::message::MESSAGE_BUFFER_LENGTH, 100, bss_count),
                "full-roster metrics do not fit");
    }
}
