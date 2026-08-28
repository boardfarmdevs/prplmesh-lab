package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"time"

	"prplmesh-lab/controller-ui/internal/adapter"
	"prplmesh-lab/controller-ui/internal/httpapi"
	"prplmesh-lab/controller-ui/internal/upstream"
)

func main() {
	listen := flag.String("listen", env("EASYMESH_UI_LISTEN", "0.0.0.0:8091"), "HTTP listen address")
	sourceURL := flag.String("source", env("EASYMESH_TOPOLOGY_URL", "http://192.168.2.140:8090/api/topology"), "external prplMesh topology API")
	networkPath := flag.String("networks", env("EASYMESH_NETWORKS_FILE", "config/networks-untagged.json"), "network presentation configuration")
	flag.Parse()

	logger := log.New(os.Stdout, "easymesh-controller-ui: ", log.LstdFlags|log.LUTC)
	networks, err := adapter.LoadNetworks(*networkPath)
	if err != nil {
		logger.Fatalf("load networks: %v", err)
	}
	source := upstream.New(*sourceURL, 5*time.Second, 750*time.Millisecond)
	server, err := httpapi.New(source, networks, logger)
	if err != nil {
		logger.Fatalf("create server: %v", err)
	}

	logger.Printf("listening on %s; source=%s networks=%s", *listen, *sourceURL, *networkPath)
	if err := http.ListenAndServe(*listen, server.Handler()); err != nil {
		logger.Fatal(err)
	}
}

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
