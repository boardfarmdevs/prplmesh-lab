package upstream

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestFreshResponsesAndFailuresAreNotCached(t *testing.T) {
	var requests atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		count := requests.Add(1)
		if count == 2 {
			http.Error(writer, "unavailable", http.StatusServiceUnavailable)
			return
		}
		writer.Write([]byte("{\"devices\":[{\"id\":\"02:00:00:00:00:01\"}]}"))
	}))
	defer server.Close()
	client := New(server.URL, time.Second)
	if _, err := client.Get(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Get(context.Background()); err == nil {
		t.Fatal("a failed fresh request must not silently become a successful cached response")
	}
	if _, err := client.Get(context.Background()); err != nil {
		t.Fatal(err)
	}
	if requests.Load() != 3 {
		t.Fatalf("requests=%d", requests.Load())
	}
}

func TestConcurrentReadersShareAnInFlightRequest(t *testing.T) {
	var requests atomic.Int64
	started := make(chan struct{}, 32)
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		started <- struct{}{}
		<-release
		writer.Write([]byte("{\"devices\":[{\"id\":\"02:00:00:00:00:01\"}]}"))
	}))
	defer server.Close()
	client := New(server.URL, time.Second)
	var readers sync.WaitGroup
	errors := make(chan error, 20)
	readers.Add(1)
	go func() {
		defer readers.Done()
		_, err := client.Get(context.Background())
		errors <- err
	}()
	<-started
	for index := 0; index < 19; index++ {
		ctx, cancel := context.WithTimeout(context.Background(), time.Millisecond)
		_, err := client.Get(ctx)
		cancel()
		if err != context.DeadlineExceeded {
			t.Fatalf("cancelled waiter: %v", err)
		}
	}
	if requests.Load() != 1 {
		t.Fatalf("simultaneous callers duplicated the request: %d", requests.Load())
	}
	close(release)
	readers.Wait()
	if err := <-errors; err != nil {
		t.Fatal(err)
	}
}

func TestInvalidInventoryAndTimeoutFailClosed(t *testing.T) {
	for _, body := range []string{"{}", "not-json", "{\"devices\":[]}"} {
		server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			writer.Write([]byte(body))
		}))
		client := New(server.URL, time.Second)
		if _, err := client.Get(context.Background()); err == nil {
			t.Fatalf("accepted %q", body)
		}
		server.Close()
	}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		<-request.Context().Done()
	}))
	defer server.Close()
	client := New(server.URL, 20*time.Millisecond)
	if _, err := client.Get(context.Background()); err == nil {
		t.Fatal("unbounded source request")
	}
}
