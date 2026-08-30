package web

import "embed"

// Files is the patched RDK EM CLI Web frontend and its original assets.
//
//go:embed static
var Files embed.FS
