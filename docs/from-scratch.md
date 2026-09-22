# Build from source

Start with the [build guide](build/README.md). It separates:

1. Ubuntu 22.04 native artifact compilation from the pinned manifest;
2. an independently named LXD VM, reusable pool and per-VM ports; and
3. [offline, browser, room, native and bounded churn tests](test/README.md).

Run those instructions on the outer host, not inside an existing radio VM.
The runtime VM remains Ubuntu 24.04 with the supported pinned Linux 7 kernel.

The advanced [bare-metal deployment](../deploy/bare-metal/README.md) owns the
machine's radios and kernel modules. It is not the default developer build path.
