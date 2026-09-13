# Room catalog: what to watch

[Room reference](README.md) · [Acceptance](../testing/room-acceptance.md)

These are expected features, not claims that every deployed backend passes.
The deployed golden files determine exact roles, RF values and timing. Start
paused, wait for load/roster/measurement readiness, then press Play at 1×.
Watch actual ownership in both views, not just the simulated candidate line.

| World ID | Script | Clients / expected behavior |
| --- | ---: | --- |
| `fifty-client-counter-roam` | 36 s | 50; two walkers swap Ext-1/Ext-2 regions while 48 peers stay fixed; pause at 18 s, then return |
| `band-upgrade-24-5` | 30 s | Same-AP 2.4/5 GHz upgrade/fallback; pinned client remains on 2.4 GHz |
| `band-upgrade-5-6` | 30 s | Same-AP 5/6 GHz steering; inspect native BSSID, frequency and traffic |
| `band-ap-counter-roam` | 30 s | Combined AP/band changes; consult the signed band's checkpoint expectations |
| `home-a-stationary` | 60 s | 10; fixed geometry, no sustained unnecessary AP churn |
| `home-a-one-client-handover` | 20 s | 11; one walker crosses toward another eligible AP |
| `large-room-extender-evacuation` | 20 s | 12; moving extender weakens its client links; clients should seek better APs |
| `large-room-perimeter-counter-roam` | 60 s | 12; two opposite-direction walkers; inspect distinct AP paths at 14/28/42 s |
| `home-a-asymmetric-link` | 60 s | 11; directional uplink penalties must survive load and playback |
| `home-a-band-walk-small` | 60 s | 10; moving clients retain SSID and use eligible band candidates |
| `home-a-border-hover` | 60 s | 12; boundary walkers distinguish useful roaming from ping-pong |
| `home-a-disappear-reappear` | 60 s | 12→11→10→11→12 at 16/24/32/40 s; identical returning client identities |
| `home-a-extender-loss-recovery` | 90 s | 10; extender_4 fronthaul unavailable at 20–60 s; backhaul remains connected |
| `home-a-fast-transit` | 30 s | 12; two fast walkers; report lag during motion and recovery afterward |
| `home-a-flash-crowd` | 60 s | 10→20→10 at 20/50 s; no ghost or duplicate clients |
| `home-a-private-client-room-walk` | 240 s | 20; default narrated walker with nineteen reference clients |
| `home-a-slow-walk-ten` | 60 s | 20; ten walkers plus ten static clients |
| `home-b-slow-walk-ten` | 60 s | 20; changed AP geometry; compare serving APs without assuming adaptive backhaul |

**Quick demo:** One Client Handover. **Most visible population change:** Flash
Crowd. **Most interesting guided roaming:** Perimeter Counter-Roam.
**Capacity demonstration:** Fifty Client Counter-Roam requires the 0913 pool.
The room and topology must both contain exactly 50 online clients, without
showing the other 50 provisioned stations. Its two walkers move during 6–12 s
and 24–30 s. At the 18 s pause verify eligible serving APs before resuming;
at 36 s verify the return. Reference peers may steer after load but should not
keep churning once settled. Loading Default must restore 20 online clients
without changing any container or radio identity.
Its checkpoint pauses add real waiting time; sixty seconds of scripted motion
does not promise sixty seconds to finish all verified handovers.

During presence changes, the topology roster should follow the room after the
native update, without creating/destroying containers. During movement, report
transient convergence separately from the final settled result. At every
checkpoint/end, compare physical BSSID, controller ownership, fresh candidates
and probe traffic.

Do not expect all bars green, instant simultaneous moves or a chain solely
from the drawing. With protected startup backhaul, the expected parent tree
is the actual configured connected tree, not the geometrically shortest one.
