# Validation status

## Accepted through 2026-09-02

| Area | Accepted result |
|---|---|
| Build | Pinned prplMesh 6.0.0 NL80211 x86 release build with verified patch-set provenance |
| Inventory | 40 stable hwsim identities; no PHY swaps across reconstruction |
| Mesh | Controller/colocated agent plus four external wireless agents |
| Backhaul | Star, branch and four-hop chain physically and logically verified |
| Fronthaul | 20 clients, split 10 private and 10 IoT |
| Bands | Each SSID independently has 2.4, 5 and 6 GHz clients |
| Security | WPA2 on 2.4/5 GHz; SAE/PMF on 6 GHz |
| Model | 5 devices, 15 radios, 45 BSSs and 20 unique client owners in NBAPI |
| Metrics | 20/20 associated-client RCPI values after the reporting interval |
| Candidate metrics | 80/80 same-band STA/alternate-AP measurements complete and fresh: 16 on 2.4, 40 on 5, 24 on 6 GHz |
| Steering | 30/30 matrix cells: 6 clients × 5 targets across both SSIDs and all bands |
| Medium step | 20/20 RCPI 118 → 88 → 118 without a container restart |
| Per-link scenario | Associated RCPI followed 45 → 25 → 45 dB SNR as 128 → 88 → 128 RCPI; exact restore passed |
| Optimizer recommend | Five-node crossover selected only the independently designated target from NBAPI metrics |
| Optimizer act | Target BSSID recommendation, BTM action, ownership verification and medium restore all passed |
| Data plane | 20/20 clients reached the controller; deepest-chain sample lost 0/10 packets |
| Outage | Leaf aged from active topology within 10 s; client roamed; same agent identity rejoined |
| Bounded churn | Three leaf restart/steering cycles; inventory hash and wmediumd PID unchanged |
| Resources | Fixed process cardinality; no snapd/unattended-upgrade runtime processes |
| Medium backends | Full 20-client acceptance passed with default userspace wmediumd and opt-in kernel medium |
| Medium Console | Same source and static binary as RDK; 20/20 authoritative client-owner edges with stable private/IoT labels |

In the current 25-container star profile, the full readiness-gated cold start
completed in 199 seconds with userspace wmediumd and 189 seconds with the
kernel medium. The client phase was 31 and 20 seconds respectively; clean stop
took 15 seconds. Reapplying client profiles normally completes in about 35–44 seconds.
Associated-client metrics converge at the next reporting interval, currently
within 45 seconds. The latest measured mesh-process RSS totals were about
118 MiB in the controller container and 80–87 MiB per external agent;
wmediumd used 4.0 MiB RSS; the experimental kernel metrics proxy used 18.8 MiB.
RSS includes shared mappings and is not PSS.

The final `0829` clean-image verification rebuilt prplMesh and hostapd from the
pinned sources, recreated all 25 nested containers, and repeated the expanded
acceptance gate. Under simultaneous RDK appliance reconstruction on the same
outer host, gated mesh startup took 424.51 seconds and client admission took
34.03 seconds. This deliberately contended run proves artifact correctness; it
does not replace the isolated timings above.

## 50-client appliance validation

The universal thin appliance was imported on rev120 with the 50-client profile
and default userspace wmediumd. Its 55 nested containers comprise one
controller, four agents, 25 private clients and 25 IoT clients. The accepted
band distribution was 10 clients on 2.4 GHz, 26 on 5 GHz and 14 on 6 GHz.

The following gates passed on the same imported instance:

| Gate | 50-client result |
|---|---|
| Topology | Star, branch and four-hop chain passed physical and NBAPI parent checks |
| Model and metrics | 5 devices, 15 radios, 45 BSSs, 50 unique owners and 50/50 RCPI values |
| Steering demo | 30/30 moves across both SSIDs, all three bands and all five mesh targets |
| Global RF step | 50/50 clients followed RCPI 118 → 88 → 118 without a container restart |
| Optimizer | Both recommend and act selected the designated crossover BSSID from NBAPI candidate metrics and restored the medium |
| Agent recovery | Leaf aged out, its client moved, and the same agent identity rejoined |
| Churn | One complete leaf restart/steering cycle preserved inventory hash and wmediumd PID |
| Data plane | 50/50 clients reached the controller; chain and star samples each lost 0/10 packets |
| Processes | Eight expected mesh processes per controller/agent; no duplicate runtime daemons |

After the outer LXD archive import, which took about nine minutes, first-boot
provisioning and acceptance took 1,538 seconds. Its logged subphases were 722
seconds nested provisioning, 451 seconds mesh readiness, 82 seconds client
admission and 279 seconds final acceptance. A subsequent complete runtime
restart took 513 seconds including teardown; its reconstructed start was 480
seconds (426 seconds mesh, 49 seconds clients, and two seconds each for Console
and topology adapter).

After final star reconstruction, measured RSS was 121,208 KiB for the
controller, 85,484–88,472 KiB per external agent, and 5,672 KiB for wmediumd.
The representative star path had 0% loss and 17.478 ms average RTT. These are
RSS values and therefore include shared mappings.

The scale run exposed and fixed four harness defects rather than stack
failures: the RCPI scenario selected an obsolete fixed inventory; optimizer
candidate collection retained a 20-client timeout; agent aging had only a
30-second test deadline despite a measured 36.7-second transition; and the
data-plane helper assumed agent 4 always owned a client in star mode. The
tests now derive profile cardinality and medium configuration from the
immutable appliance environment, scale the bounded candidate deadline, use a
60-second aging gate, and select a populated deepest agent for each topology.

## Repeatable gates

The normal gate is:

```sh
PRPL_AGENT_COUNT=4 PRPL_CLIENT_COUNT=20 PRPL_TOPOLOGY=chain \
  tests/run-acceptance.sh
```

The destructive reconstruction and scenario tests are documented in
`tests/README.md`. They validate physical state, NBAPI state and permanent
identity rather than treating CLI acknowledgement or Web rendering as proof.

## Defects found and fixed in the experiment

- Native Linux mapped only two of the configured three radios.
- A stock-hostapd association event lacked the raw frame prplMesh expected,
  leaving station BSSID ownership unresolved.
- All radio backhaul supplicant paths mapped to one AP interface.
- Stock hostapd rejected an unchanged-channel update that prplMesh treated as
  fatal.
- The NL80211 supplicant helper rejected a null output buffer before
  `ADD_NETWORK`, so WSC-delivered credentials were never applied.
- The WSC BSSID field contains the enrollee RUID in this controller path; using
  it as a parent selection target broke a working wireless backhaul.
- Dynamically created networks lacked `multi_ap_backhaul_sta=1`, causing
  backhaul-only AP rejection.
- LXD physical devices addressed by transient `wlanN` names could exchange
  controller and agent PHYs. Host-only names now derive from permanent hwsim
  MAC identity.
- Ubuntu snap seed and unattended-upgrade services activated inside every
  runtime node and exhausted the nested VM at scale. The runtime image now
  excludes them and shrank from 744 MiB to 357 MiB.
- BML `bml_conn_map` can wait indefinitely once wireless backhaul and multiple
  fronthaul clients coexist. Readiness tests now use bounded NBAPI instance
  queries; BML remains a diagnostic debt.
- Reapplying a different band profile could retain the existing association.
  Client setup now explicitly disconnects and applies both scan and allowed
  frequency constraints.
- The controller accumulated query TLVs across Agents and treated the
  EasyMesh measurement-age delta as an epoch timestamp. Queries now use a
  fresh CMDU per Agent/opclass and reconstruct measurement time as
  `receipt time - age`, keeping all candidate facts current and correctly
  attributed.
- The host topology adapter initially stamped associated RCPI with HTTP poll
  time. It now carries the NBAPI STA `TimeStamp` through both Web APIs and the
  optimizer, so freshness reflects the controller metric record.
- Unversioned local prplMesh and wmediumd build outputs allowed stale binaries
  to satisfy deployment. Runtime archives and wmediumd now carry patch-set
  provenance, and acceptance/startup reject mismatches.
- The appliance initially probed the Controller UI immediately after process
  launch. Cold start now waits on bounded endpoint health and no longer fails
  on the listener-bind race.
- Linux 7 exposes NL80211 band entries without usable channels. The attach path
  dereferenced the first entry before validating it; empty candidates are now
  skipped.
- Nested NL80211 interface-type parsing reused the outer band iterator and
  could corrupt the tri-band inventory. The nested parser now has its own
  iterator.
- Stock hostapd uses `hw_mode=a` for both 5 and 6 GHz. The Linux HAL now uses
  the unambiguous 6 GHz global operating class when classifying that radio.
- The 5 GHz hwsim inventory includes extended frequencies such as 5920 MHz.
  Selecting an arbitrary first channel classified the entire band as unknown
  and restarted its fronthaul every ten seconds. Both reporting and matching
  now scan the complete band for a recognized channel.
- The RCPI gradient test retained an obsolete wmediumd PID path and could
  mistake a rejected second daemon for an active test medium. It now owns the
  canonical runtime PID plus control, metrics and observer sockets, and proves
  the 20-client 118 → 88 → 118 transition.
- Private clients were emitted with a prpl-only `client` role, and multicast
  packet fan-out made every active pair look non-authoritative. The inventory
  now uses the shared `wlan-client` role, while wmediumd exposes ownership only
  from ACKed association responses or infrastructure data. The identical RDK
  and prpl Console binary therefore renders 20 current edges and treats event
  ring overwrite counters as informational unless the observer reports a real
  history gap.

## Remaining gaps

- Deterministic client addressing, all-client reachability and a bounded
  deepest-chain latency/loss sample are accepted. Sustained and mixed traffic
  profiles, throughput thresholds and congestion testing are not yet present.
- The lab has passed a three-cycle bounded churn gate but not a long-duration
  soak. Current evidence is reconstruction, churn, steering, outage and
  metrics checks.
- Stock-hostapd raw association-frame compatibility remains a candidate for
  upstream-quality cleanup.
- The internal topology adapter is read-only and deliberately smaller than the RDK
  EM CLI. It is an observability aid, not a policy or optimizer component.

This is now sufficient for comparative onboarding, multihop, associated and
candidate telemetry, outage, steering, dynamic-medium and reference-policy
experiments. The same optimizer/configurator and wmediumd Console source are
intentionally duplicated in both mesh repositories for this phase. Long soak
history and mixed sustained traffic/congestion work remain open in both labs.
