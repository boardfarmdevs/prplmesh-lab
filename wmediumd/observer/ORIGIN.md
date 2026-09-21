# Shared presentation source

Console NG is backported from `gen/wmediumd/observer` in the RDK layer through
`f0bac18` plus its working-tree RF catalog/passive-observation integration.
The core Go implementation and NG assets are shared. prpl-specific installation,
service socket isolation, generated documentation, defaults and packaging tests
remain local adapters. This identifies source ancestry, not live acceptance.

Refresh Go and browser sources together, regenerate embedded manuals/catalogs,
and rebuild the checked-in static binary. Run short contract/model tests in
both repositories; native acceptance requires their separate lab runs.
The matching prpl daemon extensions are `0033-wmediumd-console-ng-detail.patch`
and `0034-wmediumd-expose-rf-model-profile.patch` after its existing patch series.
Opcode 17 / capability bit 16 belongs to explorer detail, not a future RF setter.
