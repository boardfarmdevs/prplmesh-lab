# Release information

[Current state](current-state.md) owns deployed identity, download locations,
qualification scope and open limitations.

Each release records its exact runtime/source inputs and checksums. A source
build, a packaged candidate and an accepted fresh import are distinct states.
Dated acceptance records belong alongside immutable release artifacts, not in
a second growing chronology.

0916 is packaged as a **candidate with known issues**, at the owner's request
to stop debugging and complete distribution. Read `KNOWN-ISSUES-0916.md` and
the packaging receipt included with the artifacts. The latest combined runtime
passes its normal 100-client lifecycle but has no new complete room campaign.
Its clean medium build and original dirty native build have distinct provenance;
archive integrity does not establish exact-archive fresh-import acceptance.

For older findings, use `git log --all -- docs reference`. Old reports are
evidence of their recorded run, not instructions or proof for the current lab.
