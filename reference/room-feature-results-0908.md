# 0908 room correctness and performance results — 2026-09-09

## Summary

Executed all **14 advertised rooms on each lab**, loading through the browser,
pressing Play, running the complete 1× script and inspecting actual rendered
topology membership/associations. The two sweeps overlapped. No soak was run.
See [the test plan](room-feature-acceptance-0908.md) for gates and reproduction.

| Check | RDK / rev140 | prplMesh / rev150 |
| --- | ---: | ---: |
| Rooms loaded and played completely | 14/14 | 14/14 |
| Initial strict convergence within the post-ready budget | 9/14 | 14/14 |
| Final strict convergence within 120 s after playback | 12/14 | 14/14 |
| Perimeter checkpoint convergence within 60 s | 1/3 | 3/3 |
| Golden server positions/presence followed during Play | 14/14 | 14/14 |
| Excluded-client kernel checks at final boundaries | 14/14 | 14/14 |
| Strict all-checks acceptance, including RF/visual/presence checks | **5/14** | **9/14** |
| Successful / unsuccessful handover verifications | 150 / 4 | 150 / 0 |
| Browser JavaScript errors / SSE gaps during the full sweep | 0 / 0 | 0 / 0 |
| Native services, medium and container identities unchanged | Yes | Yes |

**This is not a clean release acceptance pass.** In particular, both live
implementations lose the asymmetric room's directional RF penalties. RDK also
has candidate-coverage timeouts and an intermittent presence/reporting anomaly.
Minor sampled room-clock/pose discrepancies are separate from AP convergence.

## Versions and execution

- RDK VM: `rdkeasymesh-20-0908`, deployed source
  `c1f163c1f8f44ef68bd3d2806d54ea7a7c4cad11`.
- prplMesh VM: `prplmesh-20-0908`, deployed source
  `f61eb576292dda773f88805602d1800754e1cd46`.
- Both outer VMs have six vCPUs and 8 GiB RAM. Each retains all 25 nested
  containers: twenty clients and five physical mesh devices/six logical roles.
- RDK sweep: **18:56:00–19:49:35 UTC**, approximately 53.6 minutes.
  prplMesh sweep: **18:53:55–19:26:11 UTC**, approximately 32.3 minutes.
  Each sweep plays 940 seconds of scripted time; the remaining time is bounded
  loading, convergence waits, checkpoints, evidence capture and restoration.
- Two additional bounded reproductions cover prplMesh asymmetric RF and RDK
  disappearance/reappearance with independent kernel observations.
- These are the deployed **external-policy, unassisted-BTM profiling** modes,
  not tests of autonomous native optimizer policy. Startup backhaul is protected
  and fixed; a star is expected, not a failed adaptive-parent test.
- Observer: Node 24.18.0, Playwright-core 1.54.2, Chromium 139.0.7258.5,
  headless SwiftShader on rev150. Native software/configuration was not patched.

## Room-by-room convergence

Times are seconds. **Load** is selector-to-ready time plus the strict initial
settle time. **End** starts after the complete script finishes. Both include
the five-second stability gate. `T` is a timeout, not a successful measurement;
the initial 90-second budget starts after apply/readiness, so a successful
total Load can exceed 90 seconds. Detailed component timings remain in JSON.

| Room | RDK Load | RDK End | prpl Load | prpl End | Additional findings |
| --- | ---: | ---: | ---: | ---: | --- |
| `home-a-stationary` | T 91.4 | 5.1 | 17.2 | 5.1 | RDK initially lacks complete fresh coverage. |
| `home-a-one-client-handover` | 56.3 | 36.5 | 15.5 | 11.2 | RDK sampled clock/pose discrepancy. |
| `large-room-extender-evacuation` | T 90.5 | 83.1 | 48.3 | 40.7 | RDK has one 40-second verification timeout before recovery. |
| `large-room-perimeter-counter-roam` | T 92.4 | 36.4 | 46.9 | 19.3 | RDK misses the first two checkpoint budgets; clock/pose warning. |
| `home-a-asymmetric-link` | 99.6 | 23.3 | 34.5 | 9.4 | **Directional RF incorrect on both**; prpl clock/pose warning. |
| `home-a-band-walk-small` | T 103.4 | 104.2 | 47.4 | 27.4 | RDK verification timeout; prpl clock/pose warning. |
| `home-a-border-hover` | 97.7 | 48.6 | 44.0 | 23.5 | Both satisfy the case gates. |
| `home-a-disappear-reappear` | 51.7 | 15.2 | 22.1 | 5.1 | RDK's intermediate eleven-client identity set is wrong in the first pass. |
| `home-a-extender-loss-recovery` | 100.8 | 5.2 | 24.0 | 5.1 | No clients remain on disabled `extender_4` after the grace period; mesh remains connected. |
| `home-a-fast-transit` | 32.9 | 84.0 | 21.5 | 28.3 | RDK verification timeout followed by recovery; prpl clock/pose warning. |
| `home-a-flash-crowd` | 63.7 | 98.4 | 23.6 | 5.1 | 10→20→10 roster phases verified on both. |
| `home-a-private-client-room-walk` | 50.3 | 6.2 | 82.7 | 5.1 | Both complete the full four-minute script. |
| `home-a-slow-walk-ten` | 58.0 | T 120.1 | 31.0 | 24.3 | RDK ends with fresh candidate coverage for only 16/20 clients; both have clock/pose warnings. |
| `home-b-slow-walk-ten` | T 98.7 | T 120.2 | 50.2 | 35.4 | RDK ends with coverage for only 13/20 clients; both have clock/pose warnings. |

Perimeter pauses at 14/28/42 seconds: RDK waits **60.8 T / 60.8 T / 34.5**
seconds; prplMesh waits **20.4 / 22.4 / 25.5** seconds. Playback resumes after
each pass or timeout, so no later segment is skipped.

The two RDK final timeouts do **not** prove that those clients were on bad APs:
the expected twenty clients are present, but incomplete candidate measurements
prevent a justified best-AP verdict. Healthy topology membership is not enough.

## Measured performance

Full-pass distributions below include all rooms. Successful-handover percentiles
exclude failed handovers, which are explicitly counted rather than hidden.
World/checkpoint timeouts remain failures in the matrix, not zero-latency data.

| Measurement | RDK p50 / p95 / max | prplMesh p50 / p95 / max |
| --- | --- | --- |
| Action request → verified association and traffic, seconds | 3.786 / 11.436 / 22.491 | 2.872 / 4.151 / 4.515 |
| Command submission, seconds | 0.053 / 0.064 / 0.073 | 2.306 / 3.606 / 3.813 |
| Verification phase alone, seconds | 3.728 / 11.372 / 22.423 | 0.549 / 0.760 / 1.019 |
| Playback RF apply, milliseconds; 940 samples each | 13.976 / 60.326 / 444.930 | 17.761 / 99.419 / 686.507 |
| Reported candidate transaction duration, milliseconds | 984.695 / 3272.366 / 8166.284 | Not exposed by this backend |

The short prplMesh verification phase is **not** its complete handover latency:
command submission takes additional time. Neither handover measurement includes
all the time spent waiting for a complete candidate set or selecting a target.
Candidate transaction durations include unsuccessful transactions.

During moving samples, strict convergence holds in 366/841 RDK observations
and 514/908 prplMesh observations. These are **sample fractions, not percentages
of elapsed time**; motion can continuously change the best AP, and screenshots
interrupt the observer's sampling cadence.

### Observer and host limitations

The initial two unrestricted software-rendering GPU processes overloaded the
observer host: rev150 reaches 91.06% CPU. At **19:08:53 UTC**, only those test GPU
threads were restricted to CPUs 14–15 and niceness 19; VM/native affinity and
resources were not changed. Subsequent host samples fall to roughly 26–34%.
The targeted replays start with observer CPU restrictions. Therefore this is
**deployment feature/performance evidence, not an intrinsic stack speed ranking
or a reliable rendering/FPS benchmark**.

rev140 CPU p50/p95/max is 8.75/12.35/14.88%, but its maximum sampled temperature
is 94°C and its package throttle counter increases by 127. rev150 reaches
85.5°C; no equivalent package counter is exposed. Minimum available host memory
is 49.59 GiB and 12.87 GiB respectively. Thermal/observer conditions are retained
in the evidence and must not be silently excluded from comparisons.

Browser world-readiness delays also differ from RF application: maximum reported
server apply time is 407 ms on RDK and 837 ms on prplMesh. In the instrumented
RDK presence replay, the apply HTTP request finishes in about 429 ms, the server
reports 328 ms of work, but browser readiness takes 7.98 s under the restricted
software renderer. Do not attribute that whole browser delay to EasyMesh.

## Failures and diagnostic findings

1. **RDK candidate collection is not reliable enough for full-fleet profiling.**
   Failed collection rounds include 527 native-busy HTTP 503 results
   (`Error_Prev_Cmd_In_Progress`) and 50 HTTP 504 timeouts. Seventeen superseded
   rounds are recorded separately because world/epoch changes can legitimately
   invalidate work. prplMesh records three 30-second incomplete collections and
   thirteen superseded rounds, but reaches every initial/final convergence gate.
   Changing freshness thresholds or accepting incomplete fleets would hide,
   rather than fix, the RDK failure.
2. **Four RDK handover verifications time out at approximately 40 seconds.**
   All concern six-GHz private client `sta_static_10`, MAC
   `02:00:00:00:0e:00`, container `wlan-client-009`: evacuation, perimeter,
   band-walk and fast-transit. Later recovery does not erase those failures.
   This narrows the next investigation without assigning blame to an unproven
   layer of the implementation.
3. **Asymmetric RF is lost in both live room implementations.** At script time
   34 s on RDK and 58 s on prplMesh, read-only wmediumd queries find zero uplink
   minus downlink difference for all fifteen sampled AP/band pairs. The deployed
   golden specifies −7/−10/−12 dB uplink penalties. Each audit stays within one
   environment epoch and medium generation. The live interaction code builds
   RF nodes from layout data, while this penalty is defined in mobility-node
   metadata. Correct-looking convergence in this room does not validate the
   intended asymmetric experiment. No RF workaround was applied during testing.
4. **RDK has an intermittent presence/identity anomaly.** In the first
   disappearance pass, the 32–40 s phase never shows the required eleven-client
   identity set. At 34–37 s it instead shows still-unavailable
   `sta_mobile_02` (`02:00:00:00:10:00`) while returning `sta_mobile_01`
   (`02:00:00:00:0c:00`) is missing. Both room and topology report the same state.
   One native-instrumented replay does not reproduce that early ghost: kernel
   links remain disconnected throughout both planned absences. It does show
   reconnection/reporting delay: mobile_01 becomes available at 32 s, connects
   around 35 s, reaches the controller around 37 s and the sampled topology at
   38 s. The first failure remains recorded; its exact cause is not established.
5. **Room clock and rendered pose are briefly inconsistent.** Four RDK rooms
   contain six sampled discrepancies; five prplMesh rooms contain 21. A focused
   prplMesh replay records the 4.0 s clock with a pose already near the 5 s
   position. This is a visual/clock consistency warning, not proof of delayed
   native roaming. Server scripted position/presence checks pass throughout.
6. **Topology identity is otherwise consistent in the sampled evidence.**
   There are no duplicate MACs or wrong rendered AP owners. No sustained
   disagreement is established across consecutive, adequately spaced samples.
   The original RDK home-B report flags 5.24 s, but that is one bad sample followed
   by a screenshot sampling gap, not evidence of 5.24 s continuously wrong
   rendering. The audited report corrects this assertion and preserves the raw
   report. The measured clearance bounds are not sub-second rendering claims.
7. **RDK room-service recovery needs attention.** During preflight restart,
   shutdown raises a snapshot assertion and RF recovery detects expected
   generation 74 versus actual 78, marking ownership contaminated. Eight
   deliberately unavailable clients then prevent startup. After saving the
   journal and RF record, an explicit setup-only restoration verifies the same
   medium instance and stable generation, restores the captured 660-link
   baseline and reconnects those eight clients. No native service or wmediumd
   restart is used. These setup failures are not included in roaming timings.

## Harness corrections and evidence

Raw first-pass files are preserved. The reproducible `room-feature-report.js`
audit corrects requested/submitted action double-counting, checks rendered AP
ownership and directional RF, and avoids counting unobserved screenshot gaps
as sustained topology failures. Regression assertions cover these distinctions.

A first browser launch fails before any case because of inherited `DISPLAY`;
the harness now clears it. Original room fullscreen requests are denied while
the other tab owns focus. A focused supplemental attempt exposes a harness
selector error (the fullscreen Play button is distinct), not a product Play
failure; it is archived and rerun after correcting focus, selector and promise
handling. The completed focused replay captures genuine fullscreen operation.
The prpl RF reader also uses its actual `/run/prpl-wmediumd/control.sock`, not
the RDK socket path. None of these corrections patches deployed application code.

Working evidence on rev150:
`/home/rev/work/room-features-0908-0909/`.
Final evidence copy on **both rev140 and rev150**:
`/home/rev/releases/0908/room-feature-acceptance-20260909/`.

Each lab directory contains `results/report.json`, per-room sampled JSONL,
selected SSE events, initial/moving/final room and topology PNGs, checkpoint
screenshots, golden files, native identities and host monitoring. Use
`audited-summary.json` for corrected aggregate verdicts. Supplemental evidence
is under `prpl/recheck-asymmetric/` and `rdk/recheck-presence/`; failed preflight
and observer attempts are retained separately. Repository test/diagnostic code
is under RDK `gen/tests/` and prplMesh `tests/`.

## Cleanup and next work

The temporary 2000-action runtime drop-ins are removed and the original
100-action service configuration is restored. Both labs return to the default
twenty-client room, paused, with no test lease; all nested containers and native
services remain running. RDK's main default-restoration **strict measurement
gate times out**, despite its healthy, correct twenty-client roster; count
restoration must not be described as verified best-AP convergence.

Both targeted replay restorations subsequently pass their strict gates. The
independent final checks at approximately 19:56 UTC show **both labs healthy
and converged**, twenty clients, no lease or room fault, unchanged native
identities and the original 100-action cap. The earlier RDK restoration timeout
remains a recorded failure, not retroactively a pass. Owned test browsers and
host samplers have exited.

Priority follow-up is candidate collection/6-GHz verification on RDK,
preservation of directional mobility RF metadata on both backends, and the RDK
presence/reporting anomaly. Clock/pose atomicity follows. This task records
the defects; it does not modify the native stacks, deployment images or thin
tarballs to make the test pass.
