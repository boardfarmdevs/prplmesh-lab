# RDK Unified EasyMesh and prplMesh comparison

## Executive conclusion

The work to date supports a real architectural conclusion, but not the simple
conclusion that one implementation is mature and the other is not.

prplMesh 6.0.0 now reaches the same basic radio scale: a controller/colocated
Agent, four external tri-band Agents, 20 clients, two SSIDs, wireless star,
branch and four-hop chain backhaul, live RCPI, outage/rejoin and a 30-cell BTM
matrix. It required five focused prplMesh native-NL80211 patches plus separate
lab/runtime corrections. The equivalent path was still much harder to reach
with RDK Unified EasyMesh. prplMesh has a clearer EasyMesh model, narrower
native-Linux platform boundary, direct NL80211 backend and standardized
northbound model. Those choices make it much easier to place over hwsim.

The RDK patch volume cannot, however, be attributed only to OneWifi or only to
virtual radios. The largest concentration is in the Unified EasyMesh
controller/Agent/CLI implementation. The most fragile integration boundary is
the complete path from Wi-Fi HAL through OneWifi and libwebconfig/RBUS into the
EasyMesh Agent. Virtual radios exposed assumptions at that boundary, but many
of the resulting failures are generic state, memory, concurrency, protocol,
and ownership defects that can also affect physical systems.

The radio/onboarding/associated-telemetry/steering results are now comparable
at five devices and 20 clients. The total research environments are not yet
equivalent: RDK additionally has policy deployment, candidate-link telemetry,
traffic/scenario generation, wmediumd control and Console, optimizer replay,
VM packaging and longer memory/soak history. prplMesh still needs those shared
research facilities before end-to-end optimizer behavior can be compared.

## Evidence baseline

| Area | RDK Unified EasyMesh | prplMesh 6.0.0 |
| --- | --- | --- |
| Tested topology | Controller plus colocated Agent, four external Agents, 20 clients | Controller plus colocated Agent, four external Agents, 20 clients |
| Radios | Tri-band hwsim, 15 modeled Agent radios | Tri-band hwsim, 15 modeled Agent radios |
| Backhaul | Four wireless backhaul STAs; star and multihop exercised | Four wireless backhaul STAs; star, branch and four-hop chain accepted |
| Steering | Named steering, matrix, ownership and delayed-regression tests | 30-cell NBAPI BTM matrix across two SSIDs, three bands and five targets |
| Metrics | Policy deployment, periodic STA/BSS/radio metrics, candidate and backhaul RCPI | 20/20 associated-client RCPI; global medium step accepted; candidate metrics open |
| Northbound | Product-specific em_cli REST/WebUI plus controller database | `Device.WiFi.DataElements` NBAPI over Ambiorix/ubus |
| Persistence | MariaDB and retained `/nvram` identity | Primarily an in-memory controller model |
| Virtual-radio product patches so far | Large, distributed series | Five focused native Linux/NL80211 corrections |
| Lab infrastructure | Mature lifecycle, configurator, Console, optimizer, tests and VM packaging | LXD lifecycle, stable inventory, scale tests and read-only topology visualizer |

The RDK `codex/0824-clean` patch inventory currently contains 126 patch files
under Unified EasyMesh, 30 under Wi-Fi HAL, 20 under OneWifi, 12 under
libwebconfig, six under `ieee1905-em`, and four under the hostap integration.
This count includes adaptations, generic fixes, presentation changes and
features; it must not be read as 198 independent product defects. The content
and ownership of those changes are more informative than the raw count.

## Why the difference is so large

### 1. The original platform fit is different

prplMesh has a native Linux build with a Beerocks Wireless Library NL80211
backend that directly uses hostapd, wpa_supplicant and nl80211. hwsim presents
the same kernel API, so the initial AP and station integration follows an
already supported path.

The RDK image is an embedded gateway stack whose Wi-Fi path was developed
around a physical MediaTek platform. Its HAL, OneWifi data model, RBUS
providers, platform radio inventory, VAP rules, persistent state, service
ordering and EasyMesh translation all participate in presenting a radio. A
single hwsim wiphy projected as three logical radios violates several original
assumptions. Containerization also removes platform services and timing that a
complete device image normally supplies.

This explains the hwsim-specific work: radio discovery, single-wiphy
projection, 6 GHz regulatory setup, non-MLO guards, management-frame
registration refresh, retained hwsim station aging, and concurrent-frequency
wmediumd integration. These adaptations do not by themselves imply that the
physical MediaTek product is unstable.

### 2. RDK crosses more independently owned boundaries

The important RDK path is:

```text
nl80211 / hostapd
        |
        v
RDK Wi-Fi HAL
        |
        v
OneWifi state and callbacks
        |
        v
libwebconfig + RBUS subdocuments
        |
        v
Unified EasyMesh Agent
        |
        v
ieee1905-em / AL-SAP
        |
        v
Unified EasyMesh Controller + MariaDB
        |
        v
em_cli REST / WebUI / optimizer consumer
```

Each boundary has its own object lifetime, threading, FULL-versus-DELTA
semantics, timeout, retry and identity rules. Several observed faults were not
local algorithm mistakes but disagreement between boundaries: an event was
treated as a snapshot, a snapshot as a delta, a transient map as authoritative,
an asynchronous callback as synchronous, or a stale database row as current
radio truth.

prplMesh is narrower:

```text
hostapd / wpa_supplicant / nl80211
        |
        v
BWL NL80211
        |
        v
beerocks_agent + per-radio fronthaul
        |
        v
ieee1905_transport
        |
        v
beerocks_controller in-memory model
        |
        v
NBAPI / BML
```

There are still boundaries, but topology and steering ownership remain much
closer to the controller model and the standardized NBAPI is already a useful
external integration point.

### 3. The RDK evaluation exercised much more behavior

RDK was not stopped after initial onboarding. The work added and repeatedly
tested scale, tri-band operation, two SSIDs, wireless and multihop backhaul,
manual steering, ownership consistency after steering, AP loss and return,
metrics policies, candidate-link observations, live UI refresh, process
memory, host reboot, VM reconstruction, RF scenarios and optimizer replay.

Deeper testing found deeper defects. prplMesh has now passed the same basic
device/client scale, wireless multihop, associated metrics, steering matrix,
leaf-outage and basic multi-hop data-plane gates, but not traffic-profile
replay, optimizer replay or long soak. The
correct comparison remains the number and severity of defects at the same
acceptance gate, not the total patches present today.

### 4. The RDK branch also contains a research product

Many RDK commits are not fixes to EasyMesh. Container lifecycle, hwsim pool
management, multichannel wmediumd, its control plane, the configurator,
wmediumd Console, scenario tests, optimizer framework, WebUI presentation and
VM packaging are research-lab infrastructure or new features. They should be
excluded when judging the supplied EasyMesh implementation.

Even inside the Unified EasyMesh patch directory, some changes add UI export,
live topology presentation, naming, layout, metrics views and testability.
The patch count therefore overstates the defect count, although the remaining
generic defect series is still unusually large.

## Component assessment

### Unified EasyMesh controller, Agent and CLI: greatest concern

This is the largest and most consequential defect concentration. Demonstrated
generic fixes include:

- WSC crypto and registrar-key correctness;
- complete steering-request serialization, source-VAP selection, ACK routing
  and BTM transaction completion;
- single current-association and single backhaul-owner invariants;
- AL-SAP stream message framing;
- AP Metrics Response capacity;
- controller and Agent object ownership and database result lifetime;
- command cancellation, timer servicing under load, result-session
  serialization and bounded transport;
- association publication before optional capability enrichment;
- authoritative Associated Clients snapshot reconciliation;
- multi-radio WSC subdocument serialization, callback recovery and retry; and
- topology, backhaul-parent, policy and metrics state convergence.

These are not all consequences of hwsim. Buffer sizing, crypto output,
transport framing, stale model ownership, timer starvation, database-result
draining and command lifetime are ordinary product-quality concerns.

The controller/Agent implementation is therefore the first component that
should undergo upstream ownership review. Carrying the complete downstream
series indefinitely is a maintenance and upgrade risk even when the patched
lab is stable.

### Wi-Fi HAL, OneWifi and libwebconfig: most fragile boundary

It is misleading to identify OneWifi alone as the bad component. The observed
association and telemetry failures arise across three layers:

- Wi-Fi HAL owns nl80211 encoding, management-frame registration, WDS timing,
  station liveness and edge-correct association callbacks;
- OneWifi owns radio/VAP indexing, live associated-client state, async RBUS
  provider behavior and conversion to EasyMesh inputs;
- libwebconfig owns subdocument decoding, FULL snapshot semantics, identity
  translation and allocation lifetime.

Some fixes are clearly virtual-platform adaptations, such as projecting one
wiphy into three radios and aging hwsim station objects that physical firmware
would normally remove. Others are generic, including incorrect ACL encoding,
WDS creation before authorization, callbacks emitted from retained state,
radio configuration stored by request position instead of RUID, inconsistent
field spelling, lost async apply completion, and leaked encoded/decoded event
data.

This boundary needs an explicit contract: which producer supplies an event,
which supplies a complete snapshot, who owns each allocation, how a radio is
identified, and when an asynchronous operation is complete. Without that
contract, fixes at one layer can be defeated by stale state in the next.

### ieee1905-em: smaller scope, important generic fixes

The IEEE1905 series is comparatively small. Its major corrections—preserving
length-delimited AL-SAP frames and publishing neighbor expiry/reappearance
through normal Topology Notifications—are generic correctness work. They are
not evidence that IEEE1905 is the dominant source of instability, but they are
important because all higher topology convergence depends on them.

### RDK-B platform services: incidental but costly

MariaDB, journald, log4c, SNMP self-heal, persistent NVRAM, Boardfarm WAN and
systemd/LXD ordering are not EasyMesh algorithms. They increased bring-up and
soak complexity and produced real failures such as unbounded logs and repeated
SNMP processes. They should remain classified as device integration or lab
infrastructure rather than evidence against a steering implementation.

### prplMesh: cleaner architecture, core radio acceptance complete

The positive evidence is strong:

- a pinned native x86 build runs unchanged in ordinary LXD containers;
- the NL80211 abstraction operates on patched Linux 7 hwsim with a focused
  five-patch native-platform set;
- controller and external-Agent onboarding converge without a database repair
  or service nudge;
- dynamic Device/Radio/BSS/STA instances are available through a standardized
  NBAPI;
- two-SSID BTM requests on all three bands produce consistent physical and
  controller ownership across all five targets;
- four wireless backhaul STAs support star, branch and four-hop chain;
- 20 clients report associated RCPI and follow a live wmediumd SNR step;
- leaf outage, topology aging, client roam and stable-identity rejoin pass; and
- the external topology visualizer can remain a read-only NBAPI client rather
  than becoming controller code.

There was also material negative evidence in the stock native NL80211 wireless
backhaul path:

- the generated Linux platform database maps a radio's wpa_supplicant control
  path to the same interface name already owned by hostapd;
- the NL80211 `get_scan_results()` backhaul method returns zero;
- preconnected-backhaul detection in the state machine is disabled, with a
  source comment that the earlier change broke wireless backhaul;
- upstream wireless-onboarding acceptance contains a TODO instead of
  completing the WPS peer and data path; and
- the supplicant reply helper rejected the normal `ADD_NETWORK` call, delivered
  WSC BSSID was misused as a parent target, and dynamic networks lacked the
  Multi-AP backhaul-STA flag.

The experiment fixed these as five bounded native-platform/NL80211 patches and
then passed repeated wireless-backhaul reconstruction. This is substantially
better evidence than the earlier wired result, but stock 6.0.0 should not be
described as passing this profile without those patches.

## Is RDK merely a bad fit for virtual radios?

Partly, but not entirely.

The following should be considered expected adaptation cost:

- mapping hwsim identities into the physical platform's radio/VAP model;
- creating a strict Linux 7 6 GHz regulatory environment;
- supporting three concurrent frequencies on one simulated medium;
- compensating for hwsim station-object retention; and
- replacing absent embedded services in containers.

The following cannot reasonably be blamed on virtual radios:

- incorrect AES output and stale WSC registrar crypto;
- undersized protocol buffers;
- malformed or incomplete steering transactions;
- incorrect AL-SAP stream framing;
- timer starvation under load;
- leaked trees, JSON, event buffers and database results;
- overlapping unbounded controller command sessions;
- topology ownership overwritten by older evidence; and
- policy/Profile state rejected or lost inside the controller.

hwsim was useful precisely because it made these failures reproducible. It is
an observability multiplier, not only a source of incompatibility.

## Readiness for optimizer research

### Patched RDK stack

The accepted patched RDK lab is currently the more complete optimizer research
environment. It has scale, wireless backhaul, RF control, metrics, an external
optimizer framework, steering scripts, a WebUI, scenarios and acceptance
tests. It is usable for experiments if its exact image and patch baseline are
pinned.

It is not a low-maintenance representation of the supplied upstream stack.
Results should clearly state that they come from the patched research baseline.
Upgrades require replaying and requalifying a large component-spanning series.

### Unpatched RDK stack

The unpatched baseline is not suitable for dependable optimizer conclusions.
Onboarding, association ownership, metrics, liveness and steering can be wrong
or incomplete, so the optimizer would learn from contradictory observations
and actions whose completion is uncertain.

### prplMesh stack

prplMesh is now a credible second optimizer backend because NBAPI provides a
structured observation/action boundary and wireless onboarding, multihop,
20 clients, associated RCPI, AP loss/recovery, repeated steering, restart
convergence and bounded process cardinality all pass. It is not yet a complete
replacement for the RDK research lab: candidate-link telemetry, traffic
generation/profiles, dynamic scenarios, optimizer adapter, long soak and
packaging remain.

## Recommendations

1. Keep both implementations and run identical golden wmediumd scenarios
   against them. A second implementation is valuable precisely because it
   separates optimizer behavior from one stack's defects.
2. Use acceptance parity, not patch count, as the comparison metric. Require
   the same topology size, backhaul mode, traffic, observation cadence,
   steering matrix, churn and soak duration.
3. Treat the RDK Unified EasyMesh core as the primary upstreaming priority.
   Split its series into generic correctness, hwsim-gated adaptation and lab/UI
   features, and require an owning upstream issue and regression test for every
   generic patch.
4. Define a formal contract across Wi-Fi HAL, OneWifi, libwebconfig and the
   EasyMesh Agent for identities, snapshots, deltas, memory ownership and
   asynchronous completion.
5. Do not add optimizer policy logic inside either EasyMesh implementation.
   Keep the optimizer external and adapt its observation/action ports to RDK
   REST/controller data and prplMesh NBAPI.
6. For prplMesh, retain the focused native NL80211 fixes and next qualify the
   shared optimizer adapter, candidate metrics and traffic profiles. Keep the
   visualizer read-only rather than creating another controller policy plane.
7. Retain hwsim/wmediumd as a fault-finding platform even for product fixes
   intended for physical hardware. Every generic fix should also be validated
   on the physical MediaTek target before upstreaming.

## Bottom line

The extreme difference remains real even after matching the basic radio scale.
prplMesh is a better fit for native Linux virtual radios and its software
boundaries are cleaner. RDK also contains an unusually large body of genuine
EasyMesh core and cross-layer correctness defects that cannot be dismissed as
virtualization artifacts.

The fairest current judgment is:

- **RDK patched lab:** feature-rich and experimentally useful, but expensive to
  maintain and too far from the supplied baseline;
- **RDK unpatched stack:** not reliable enough for optimizer evaluation;
- **prplMesh patched native stack:** wireless backhaul, scale, associated
  metrics, steering and recovery are now accepted with a much smaller focused
  patch set;
- **prplMesh research environment:** still lacks the RDK lab's optimizer,
  configurator, traffic generation, candidate telemetry, packaging and soak
  breadth.

The next fair comparison is not more basic onboarding. It is to feed identical
traffic and golden RF scenarios into both stacks through a common optimizer
adapter, then compare decisions, completion, recovery and resource stability.
