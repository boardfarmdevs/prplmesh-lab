nbapi_btm_request()
{
    local station=$1 request=$2 root=Device.WiFi.DataElements.Network payload response
    [[ "$station" =~ ^Device\.WiFi\.DataElements\.Network\.Device\.[0-9]+\.Radio\.[0-9]+\.BSS\.[0-9]+\.STA\.[0-9]+$ ]] || {
        echo "invalid native station object: $station" >&2
        return 2
    }
    payload=$(jq -cn --arg path "${station#"$root".}.MultiAPSTA." --argjson args "$request" \
        '{rel_path:$path, method:"BTMRequest", args:$args}') || return
    response=$(lxc exec --mode non-interactive "$CONTROLLER" -- timeout -k 1 8 \
        ubus -t 5 call "$root" _exec "$payload" </dev/null) || return
    if ! printf '%s\n' "$response" | jq -es '
        length > 0 and all(.[]; type == "object") and
        ([.[] | select(has("amxd-error-code")) | .["amxd-error-code"]] == [0])
        ' >/dev/null; then
        printf 'Native BTM acknowledgement missing or failed: %s\n' "$response" >&2
        return 1
    fi
}
