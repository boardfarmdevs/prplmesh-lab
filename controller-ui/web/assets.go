package web

import "embed"

// Files is the topology page (easymesh-medium topology-ui, assembled for prplMesh by
// prepare-web-assets.sh) and its offline libraries.
//
//go:embed static
var Files embed.FS
