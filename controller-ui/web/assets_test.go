package web

import (
	"bytes"
	"testing"
)

func TestOfflineDependencies(t *testing.T) {
	index, err := Files.ReadFile("static/index.html")
	if err != nil {
		t.Fatal(err)
	}
	for _, external := range [][]byte{[]byte("https://cdn"), []byte("https://cdnjs")} {
		if bytes.Contains(index, external) {
			t.Fatalf("index depends on a remote asset: %s", external)
		}
	}
	for _, asset := range []string{
		"d3-7.9.0.min.js", "chart-3.9.1.min.js", "animate-4.1.1.min.css",
		"fontawesome/css/all.min.css", "fontawesome/webfonts/fa-solid-900.woff2",
	} {
		content, err := Files.ReadFile("static/vendor/" + asset)
		if err != nil || len(content) == 0 {
			t.Fatalf("missing embedded dependency %s; run prepare-web-assets.sh: %v", asset, err)
		}
	}
}
