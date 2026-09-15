package httpapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestRoomLayoutCoalescesReaders(test *testing.T) {
	var requests atomic.Int32
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		if request.URL.Path != "/api/demo/mesh-layout" {
			test.Error(request.URL.Path)
		}
		time.Sleep(20 * time.Millisecond)
		_, _ = writer.Write([]byte(`{"schema":"easymesh.room-layout.v1","nodes":[]}`))
	}))
	defer upstream.Close()
	proxy := newRoomLayoutProxy(upstream.URL)
	var readers sync.WaitGroup
	for index := 0; index < 20; index++ {
		readers.Add(1)
		go func() {
			defer readers.Done()
			response := httptest.NewRecorder()
			proxy.ServeHTTP(response, httptest.NewRequest("GET", "/api/v1/room-layout?url=http://untrusted", nil))
			if response.Code != 200 || response.Header().Get("Cache-Control") != "no-store" {
				test.Error(response.Code)
			}
		}()
	}
	readers.Wait()
	if requests.Load() != 1 {
		test.Fatal("not coalesced", requests.Load())
	}
}

func TestRoomLayoutBoundsAndFailures(test *testing.T) {
	for _, payload := range []string{`{}`, `not json`, strings.Repeat("x", 65537)} {
		upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) { _, _ = writer.Write([]byte(payload)) }))
		response := httptest.NewRecorder()
		newRoomLayoutProxy(upstream.URL).ServeHTTP(response, httptest.NewRequest("GET", "/", nil))
		upstream.Close()
		if response.Code != 503 {
			test.Fatal(response.Code)
		}
	}
	for _, address := range []string{"", "file:///etc/passwd", "http://user:pass@host", "http://host/?url=other"} {
		if newRoomLayoutProxy(address).endpoint != "" {
			test.Fatal(address)
		}
	}
	response := httptest.NewRecorder()
	newRoomLayoutProxy("").ServeHTTP(response, httptest.NewRequest("POST", "/", nil))
	if response.Code != 405 {
		test.Fatal(response.Code)
	}
}

func TestRoomLayoutRejectsRedirectAndTimesOut(test *testing.T) {
	redirect := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) { http.Redirect(writer, request, "/other", 302) }))
	defer redirect.Close()
	response := httptest.NewRecorder()
	newRoomLayoutProxy(redirect.URL).ServeHTTP(response, httptest.NewRequest("GET", "/", nil))
	if response.Code != 503 {
		test.Fatal(response.Code)
	}
	slow := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) { <-request.Context().Done() }))
	defer slow.Close()
	response = httptest.NewRecorder()
	started := time.Now()
	newRoomLayoutProxy(slow.URL).ServeHTTP(response, httptest.NewRequest("GET", "/", nil))
	if response.Code != 503 || time.Since(started) > time.Second {
		test.Fatal("unbounded room wait")
	}
}
