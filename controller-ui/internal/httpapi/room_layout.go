package httpapi

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

type roomLayoutProxy struct {
	endpoint string
	client   *http.Client
	mutex    sync.Mutex
	pending  chan struct{}
	updated  time.Time
	body     []byte
	status   int
}

func newRoomLayoutProxy(base string) *roomLayoutProxy {
	parsed, err := url.Parse(base)
	endpoint := ""
	if err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") && parsed.Host != "" && parsed.User == nil && parsed.RawQuery == "" && parsed.Fragment == "" {
		endpoint = strings.TrimRight(base, "/") + "/api/demo/mesh-layout"
	}
	return &roomLayoutProxy{endpoint: endpoint, client: &http.Client{
		Timeout:       750 * time.Millisecond,
		CheckRedirect: func(request *http.Request, via []*http.Request) error { return http.ErrUseLastResponse },
	}}
}

func (proxy *roomLayoutProxy) collect() {
	body, status := []byte(`{"available":false,"error":"Room coordinates unavailable; diagram positions retained"}`), http.StatusServiceUnavailable
	if proxy.endpoint != "" {
		response, err := proxy.client.Get(proxy.endpoint)
		if err == nil {
			defer response.Body.Close()
			candidate, readError := io.ReadAll(io.LimitReader(response.Body, 65537))
			var envelope struct {
				Schema string `json:"schema"`
			}
			if readError == nil && response.StatusCode == http.StatusOK && len(candidate) <= 65536 && json.Unmarshal(candidate, &envelope) == nil && envelope.Schema == "easymesh.room-layout.v1" {
				body, status = candidate, http.StatusOK
			}
		}
	}
	proxy.mutex.Lock()
	proxy.body, proxy.status, proxy.updated = body, status, time.Now()
	close(proxy.pending)
	proxy.pending = nil
	proxy.mutex.Unlock()
}

func (proxy *roomLayoutProxy) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		writer.Header().Set("Allow", http.MethodGet)
		http.Error(writer, "read-only endpoint", http.StatusMethodNotAllowed)
		return
	}
	proxy.mutex.Lock()
	if time.Since(proxy.updated) >= 200*time.Millisecond && proxy.pending == nil {
		proxy.pending = make(chan struct{})
		go proxy.collect()
	}
	pending := proxy.pending
	proxy.mutex.Unlock()
	if pending != nil {
		select {
		case <-pending:
		case <-request.Context().Done():
			return
		}
	}
	proxy.mutex.Lock()
	body, status := proxy.body, proxy.status
	proxy.mutex.Unlock()
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("Cache-Control", "no-store")
	writer.WriteHeader(status)
	_, _ = writer.Write(body)
}

func configuredRoomLayoutProxy() *roomLayoutProxy {
	base, configured := os.LookupEnv("EASYMESH_ROOM_URL")
	if !configured {
		base = "http://127.0.0.1:8891"
	}
	proxy := newRoomLayoutProxy(base)
	if proxy.endpoint == "" {
		fmt.Fprintln(os.Stderr, "Room layout following disabled: EASYMESH_ROOM_URL is empty or invalid")
	}
	return proxy
}
