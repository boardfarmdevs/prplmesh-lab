# 0908 deployed release acceptance

Qualified on 2026-09-09 UTC (2026-09-08 Pacific), using an actual import of
the final archive on rev150, not the diagnostic or packaging VM.

## Release identity

- Branch: `codex/0908-clean`.
- Canonical checkout: `rev150:/home/rev/git/prplmesh-lab`.
- Packaged lab source: `f61eb576292dda773f88805602d1800754e1cd46`.
- Archive: `rev150:/home/rev/releases/0908/prplmesh-0908-thin.tar`.
- SHA256: `cacd6726318b93faa1aa65830aab04c7a6ae93a3af4d4d22701406471c7f977a`.
- Native prplMesh 6.0.0 base: `2e153c7e00cbcab6b8ee35082f494a364e23f018`.
- Thirteen-patch set SHA256: `d17007fbf7e7b8d22323d422124f07a1991a4c46298e1d73ea67197905eb1bf3`.
- Rebuilt runtime image: `93a72b8f608ffd6508947a49a235ab6eb4e6d05bcddc2709ddffce320678d8d3`.

The native runtime was rebuilt on rev150 from a fresh detached pinned worktree
plus all repository patches, including the independent candidate-query timer
fix. The Ubuntu appliance/dependency base is retained from 0907, not a new OS
build. The archive includes `native-build.json` and input checksums. Later
documentation commits do not change the source pinned in this archive.

## Independent browser endpoints

| View | prplMesh on rev150 | RDK EasyMesh on rev140 |
| --- | --- | --- |
| Live room | <http://192.168.2.150:18891/> | <http://192.168.2.140:48891/> |
| Network topology | <http://192.168.2.150:8091/> | <http://192.168.2.140:48889/> |
| Radio console | <http://192.168.2.150:8090/> | <http://192.168.2.140:48890/> |

Open either pair side by side. No `?mode=` is needed. Each room has its own
control lease, world, RF daemon and native stack. These are trusted-LAN/VPN
endpoints, not authenticated public Internet services.

## Fresh-import results

`prplmesh-20-0908` reconstructs from zero nested instances to twenty clients
and five physical mesh devices (six logical UI roles). First boot and expanded
native acceptance pass in 718.435 seconds, including provisioning and checks.
Both lab and room services start automatically inside the explicitly started
VM, with zero systemd restarts. Outer `boot.autostart=false` remains set.

Bounded live checks pass:

- Both fullscreen controls, embedded manual, Play/Pause, clean default URL,
  twenty rendered clients and six topology roles, with no browser JavaScript errors.
- Live probe selection and restoration through the browser's control lease;
  physical canvas Ctrl-click/drag behavior has separate deterministic coverage.
- `home-a-band-walk-small`: ten-client measured best-eligible-AP convergence
  in 65.54 seconds, including a ten-second stable observation gate. All ten
  excluded clients are also verified disconnected in their kernel namespaces.
- Return to default: twenty-client measured convergence in 39.65 seconds,
  including the stability gate. All container, native-service and medium
  process identities remain unchanged. The final default is restored.
- Final deterministic Python suite: 334 passed, one skipped, 37 subtests.

These are two-room bounded checks, not an all-room soak or an assertion of
instantaneous native roaming. The earlier corrected diagnostic import also
passes native acceptance and both room checks.

Detailed JSON, first-boot timing, browser reports/screenshots and test output:
`rev150:/home/rev/releases/0908/prplmesh-0908-acceptance/`.

## Scope and remaining boundaries

The shared viewer includes the current RDK layout, labels, signal rendering,
fullscreen, world loading, fixed-pool presence controls, probe selection,
stable optimizer presentation and manual. Backend collection and BTM use
prplMesh NBAPI. Unsupported RDK configuration pages remain explicitly unavailable.
Unreported native backhaul measurements stay unknown. The default prplMesh
backhaul remains protected at its startup topology: RDK's OneWifi-specific
adaptive parent-selection adapter is not implemented for prplMesh. See
[release operation and profiling boundaries](release-0908.md).

The obsolete prplMesh diagnostic/packaging VMs are deleted after qualification.
The stopped `prpl-build-0908` container is retained on rev150 for native builds.
No active prplMesh checkout, builder or lab is retained on rev140; rev120 is
unchanged. RDK monitoring is available at `https://192.168.2.140:48892/ui/`
and `https://192.168.2.140:48893/`; prplMesh monitoring remains opt-in.
