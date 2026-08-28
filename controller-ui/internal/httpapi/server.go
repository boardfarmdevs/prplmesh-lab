package httpapi

import (
	"context"
	"encoding/json"
	"io/fs"
	"log"
	"net/http"
	"strings"
	"time"

	"prplmesh-lab/controller-ui/internal/adapter"
	"prplmesh-lab/controller-ui/internal/model"
	"prplmesh-lab/controller-ui/web"
)

type Source interface {
	Get(context.Context) (model.PrplTopology, error)
	URL() string
}

type Server struct {
	source   Source
	networks []model.Network
	logger   *log.Logger
	handler  http.Handler
}

func New(source Source, networks []model.Network, logger *log.Logger) (*Server, error) {
	staticFS, err := fs.Sub(web.Files, "static")
	if err != nil {
		return nil, err
	}
	s := &Server{source: source, networks: networks, logger: logger}
	mux := http.NewServeMux()
	mux.Handle("/static/", http.StripPrefix("/static/", http.FileServer(http.FS(staticFS))))
	mux.HandleFunc("/health", s.health)
	mux.HandleFunc("/api/v1/topology", s.topology)
	mux.HandleFunc("/api/v1/devices", s.devices)
	mux.HandleFunc("/api/v1/clients", s.clients)
	mux.HandleFunc("/api/v1/bsses", s.bsses)
	mux.HandleFunc("/api/v1/networks", s.networkList)
	mux.HandleFunc("/api/v1/config", s.config)
	mux.HandleFunc("/api/v1/system/status", s.systemStatus)
	mux.HandleFunc("/api/v1/controllerIPConfig", s.controllerConfig)
	mux.HandleFunc("/api/v1/", s.stub)
	mux.HandleFunc("/", s.index)
	s.handler = requestLog(mux, logger)
	return s, nil
}

func (s *Server) Handler() http.Handler { return s.handler }

func (s *Server) snapshot(r *http.Request) (model.Snapshot, error) {
	value, err := s.source.Get(r.Context())
	if err != nil {
		return model.Snapshot{}, err
	}
	return adapter.Transform(value, s.networks, time.Now().UTC())
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"status": "unavailable", "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok", "source": s.source.URL(),
		"devices": len(value.Devices), "clients": len(value.Clients), "networks": len(value.Networks),
	})
}

func (s *Server) topology(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, value.Topology)
}

func (s *Server) devices(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"devices": value.Devices, "total": len(value.Devices), "online": len(value.Devices), "updated": value.GeneratedAt,
	})
}

func (s *Server) clients(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"clients": value.Clients, "total": len(value.Clients), "active": len(value.Clients), "updated": value.GeneratedAt,
	})
}

func (s *Server) bsses(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"bsses": value.BSSes, "total": len(value.BSSes), "updated": value.GeneratedAt})
}

func (s *Server) networkList(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"networks": value.Networks, "total": len(value.Networks), "updated": value.GeneratedAt,
		"note": "VLAN IDs describe the selected presentation profile; traffic enforcement is separately qualified.",
	})
}

func (s *Server) config(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"system_name": "prplMesh EasyMesh Controller", "mode": "read-only-host-port",
		"source": s.source.URL(), "features": map[string]bool{
			"topology": true, "devices": true, "clients": true, "networks": true,
			"policy": false, "firmware": false, "security": false,
		},
	})
}

func (s *Server) systemStatus(w http.ResponseWriter, r *http.Request) {
	value, err := s.snapshot(r)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "operational", "devices": len(value.Devices), "clients": len(value.Clients),
		"source": value.Source, "updated": value.GeneratedAt,
	})
}

func (s *Server) controllerConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		s.stub(w, r)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"ip": "external-prplmesh-api", "port": s.source.URL()})
}

func (s *Server) stub(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusNotImplemented, map[string]any{
		"status": "not_implemented", "implemented": false,
		"path": r.URL.Path, "message": "This host port currently implements live topology, devices, clients, BSS and network inventory only.",
	})
}

func (s *Server) index(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	data, err := web.Files.ReadFile("static/index.html")
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write(data)
}

func writeError(w http.ResponseWriter, err error) {
	writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "unavailable", "error": err.Error()})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func requestLog(next http.Handler, logger *log.Logger) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/static/") {
			logger.Printf("%s %s", r.Method, r.URL.Path)
		}
		next.ServeHTTP(w, r)
	})
}
