# shellcheck shell=bash
# The labs' artifact store: what takes long to build, kept by the inputs it was built
# from, so that a build on any host fetches what any host already built. Sourced by
# build-artifacts.sh, scripts/build-client-artifact.sh and build.sh; the same library as
# the RDK lab's gen/build/artifact-store.sh. The store's layout and server are described in
# the umbrella (easymesh-labs, docs/reference/artifact-store.md).
#
#   EASYMESH_ARTIFACT_STORE    where to fetch from: http://HOST:PORT, or a directory
#   EASYMESH_ARTIFACT_PUBLISH  where to publish to: a directory, or HOST:/DIRECTORY (rsync
#                              over ssh); unset, nothing is published
#
# An entry is store/COMPONENT/KEY/: its files, SHA256SUMS over them and provenance.env
# (what it was built from). KEY is a digest of every input, from artifact_key.

artifact_key() {        # artifact_key LINE...: 16 hex digits naming these inputs
    printf '%s\n' "$@" | sha256sum | cut -c1-16
}

artifact_fetch() {      # artifact_fetch COMPONENT KEY DEST: 0 when fetched and verified
    local component=$1 key=$2 dest=$3 store=${EASYMESH_ARTIFACT_STORE:-} base file
    [ -n "$store" ] || return 1
    base=${store%/}/store/$component/$key
    mkdir -p "$dest"
    case "$store" in
        http://*|https://*)
            curl -fsS "$base/SHA256SUMS" -o "$dest/SHA256SUMS" 2>/dev/null || return 1
            while read -r _ file; do
                curl -fsS --retry 3 "$base/$file" -o "$dest/$file" || return 1
            done < "$dest/SHA256SUMS"
            curl -fsS "$base/provenance.env" -o "$dest/provenance.env" 2>/dev/null || true
            ;;
        *)
            [ -f "$base/SHA256SUMS" ] || return 1
            cp --reflink=auto -- "$base"/* "$dest/"
            ;;
    esac
    (cd "$dest" && sha256sum -c --quiet SHA256SUMS) || return 1
    printf 'fetched %s/%s from %s\n' "$component" "$key" "$store" >&2
}

artifact_publish() {    # artifact_publish COMPONENT KEY DIR: DIR's files as one entry
    local component=$1 key=$2 dir=$3 target=${EASYMESH_ARTIFACT_PUBLISH:-}
    local host path partial sums
    [ -n "$target" ] || return 0
    sums=$(mktemp)
    (
        cd "$dir" || exit 1
        find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name provenance.env -printf '%P\0' \
            | sort -z | xargs -0 sha256sum > "$sums"
    )
    mv "$sums" "$dir/SHA256SUMS"
    chmod 0644 "$dir/SHA256SUMS"
    partial=.$key.partial-$$
    case "$target" in
        *:/*)
            host=${target%%:*}
            path=${target#*:}/store/$component
            # shellcheck disable=SC2029 # the paths are this side's, by design
            ssh "$host" "mkdir -p '$path'"
            rsync -a "$dir/" "$host:$path/$partial/"
            # shellcheck disable=SC2029
            ssh "$host" "rm -rf '$path/$key' && mv '$path/$partial' '$path/$key'"
            ;;
        *)
            path=$target/store/$component
            mkdir -p "$path/$partial"
            cp --reflink=auto -- "$dir"/* "$path/$partial/"
            rm -rf "${path:?}/$key"
            mv "$path/$partial" "$path/$key"
            ;;
    esac
    printf 'published %s/%s to %s\n' "$component" "$key" "$target" >&2
}
