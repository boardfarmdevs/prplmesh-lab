#!/bin/sh
set -eu

pattern=${1:?value to find in the EasyMesh NBAPI model}
root=Device.WiFi.DataElements.Network

case "$pattern" in
    02:00:00:27:*) relative=Device. ;;
    *) relative='Device.*.Radio.*.BSS.*.STA.' ;;
esac

instances=$(timeout -k 1 8 ubus call "$root" _get_instances \
    "{\"rel_path\":\"$relative\",\"depth\":1}")
objects=$(printf '%s\n' "$instances" | \
    sed -n 's/^[[:space:]]*"\([^"]*\)\.":.*/\1/p')
for object in $objects; do
    value=$(timeout -k 1 5 ubus call "$object" _get \
        '{"rel_path":"","depth":0}' 2>/dev/null || true)
    if printf '%s\n' "$value" | grep -F "$pattern" >/dev/null; then
        exit 0
    fi
done
exit 1
