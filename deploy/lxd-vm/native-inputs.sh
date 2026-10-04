# shellcheck shell=bash
# What the lab's archives are built from, as artifact-store.sh keys: the native archives
# (prplMesh, its dependencies, hostap 2.10; build-artifacts.sh) and the Alpine clients'
# supplicant (scripts/build-client-artifact.sh). artifacts/*.key records the key of what
# artifacts/ holds. Needs ROOT and artifact-store.sh.

# shellcheck disable=SC2034 # for the scripts that source this
PRPLMESH_NATIVE_ARCHIVES=(hostap-runtime-2.10.tar.gz prpl-install-nl80211-6.0.0.tar.gz
    prpl-runtime-deps-6.0.0.tar.gz)
# shellcheck disable=SC2034
PRPLMESH_CLIENT_ARCHIVE=hostap-client-2.10-alpine.tar.gz
PRPLMESH_CLIENT_ALPINE_IMAGE=${PRPL_CLIENT_ALPINE_IMAGE:-images:alpine/3.22/amd64}

prplmesh_input_blobs() {    # prplmesh_input_blobs PATH...: NAME=BLOB per file
    local file
    for file in "$@"; do
        printf '%s=%s\n' "$file" "$(git -C "$ROOT" hash-object "$ROOT/$file")"
    done
}

prplmesh_native_key() (
    # shellcheck source-path=SCRIPTDIR source=../../manifests/lab.env
    source "$ROOT/manifests/lab.env"
    cd "$ROOT" || exit
    mapfile -t blobs < <(prplmesh_input_blobs scripts/create-build-container.sh \
        scripts/build-prplmesh.sh scripts/package-build-artifacts.sh \
        scripts/container/build-inside.sh scripts/container/build-hostap-inside.sh \
        scripts/container/package-artifacts-inside.sh tests/amxp-signal-burst.sh \
        tests/amxp-signal-burst.c patches/*/*.patch)
    artifact_key "release=$PRPL_RELEASE" "prplmesh=$PRPL_COMMIT" "hostap=$HOSTAP_COMMIT" \
        "bwl=nl80211" "${blobs[@]}"
)

prplmesh_client_key() (
    # shellcheck source-path=SCRIPTDIR source=../../manifests/lab.env
    source "$ROOT/manifests/lab.env"
    cd "$ROOT" || exit
    mapfile -t blobs < <(prplmesh_input_blobs scripts/container/build-hostap-client-inside.sh \
        patches/hostap/*.patch)
    artifact_key "hostap=$HOSTAP_COMMIT" "alpine=$PRPLMESH_CLIENT_ALPINE_IMAGE" "${blobs[@]}"
)

prplmesh_artifact_sums() {  # SHA256SUMS over every archive in artifacts/
    (cd "$ROOT/artifacts" && find . -maxdepth 1 -name '*.tar.gz' -printf '%P\0' | sort -z \
        | xargs -0 sha256sum > SHA256SUMS && sha256sum -c --quiet SHA256SUMS)
}
