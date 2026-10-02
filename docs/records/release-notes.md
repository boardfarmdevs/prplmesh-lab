# Release information

[Documents](../README.md)

A lab VM is built from a clean checkout of this repository at a commit, with the
medium and the optimizer at the commits it pins and native artifacts built from the
pinned upstream sources and this repository's patches, each carrying its provenance.
A packaged VM carries this note.

[Current state](../project/current-state.md) is the single source for the
last-tested VM, its qualification and its open limitations. A source build, a
built VM and a qualified VM are distinct states: only a passed suite qualifies a
VM. For older releases, use Git history; an old report is evidence of its own run,
not instructions or proof for the current lab.
