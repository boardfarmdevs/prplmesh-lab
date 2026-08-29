# Validation status

## Accepted on 2026-08-29

| Area | Accepted result |
|---|---|
| Build | Pinned prplMesh 6.0.0 NL80211 x86 release build |
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

The 20-client cold admission phase completes in about 69 seconds after all
agents are ready. Reapplying client profiles completes in about 35–44 seconds.
Associated-client metrics converge at the next reporting interval, currently
within 45 seconds. The latest measured mesh-process RSS totals were about
118 MiB in the controller container and 80–87 MiB per external agent;
wmediumd used about 3 MiB RSS. RSS includes shared mappings and is not PSS.

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

## Remaining gaps

- Deterministic client addressing, all-client reachability and a bounded
  deepest-chain latency/loss sample are accepted. Sustained and mixed traffic
  profiles, throughput thresholds and congestion testing are not yet present.
- The lab has passed a three-cycle bounded churn gate but not a long-duration
  soak. Current evidence is reconstruction, churn, steering, outage and
  metrics checks.
- Stock-hostapd raw association-frame compatibility and noisy 6 GHz channel
  classification diagnostics remain candidates for upstream-quality cleanup.
- The topology visualizer is read-only and deliberately smaller than the RDK
  EM CLI. It is an observability aid, not a policy or optimizer component.

This is now sufficient for comparative onboarding, multihop, associated and
candidate telemetry, outage, steering, dynamic-medium and reference-policy
experiments. The same optimizer/configurator source is intentionally duplicated
in both mesh repositories for this phase. The wmediumd Console and long soak
history remain RDK-only, and mixed sustained traffic/congestion work remains
open in both labs.
