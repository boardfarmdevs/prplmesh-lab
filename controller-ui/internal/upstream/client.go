package upstream

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"prplmesh-lab/controller-ui/internal/model"
)

type flight struct {
	done  chan struct{}
	value model.PrplTopology
	err   error
}

type Client struct {
	url     string
	http    *http.Client
	mu      sync.Mutex
	pending *flight
}

func New(url string, timeout time.Duration) *Client {
	return &Client{url: url, http: &http.Client{Timeout: timeout}}
}

func (client *Client) URL() string { return client.url }

func (client *Client) Get(ctx context.Context) (model.PrplTopology, error) {
	if err := ctx.Err(); err != nil {
		return model.PrplTopology{}, err
	}
	client.mu.Lock()
	call := client.pending
	if call == nil {
		call = &flight{done: make(chan struct{})}
		client.pending = call
		go func() {
			call.value, call.err = client.fetch()
			client.mu.Lock()
			client.pending = nil
			close(call.done)
			client.mu.Unlock()
		}()
	}
	client.mu.Unlock()
	select {
	case <-ctx.Done():
		return model.PrplTopology{}, ctx.Err()
	case <-call.done:
		return call.value, call.err
	}
}

func (client *Client) fetch() (model.PrplTopology, error) {
	request, err := http.NewRequest(http.MethodGet, client.url, nil)
	if err != nil {
		return model.PrplTopology{}, err
	}
	request.Header.Set("Accept", "application/json")
	response, err := client.http.Do(request)
	if err != nil {
		return model.PrplTopology{}, fmt.Errorf("prplMesh topology API: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return model.PrplTopology{}, fmt.Errorf("prplMesh topology API returned %s", response.Status)
	}
	var value model.PrplTopology
	if err := json.NewDecoder(response.Body).Decode(&value); err != nil {
		return model.PrplTopology{}, fmt.Errorf("decode prplMesh topology: %w", err)
	}
	if len(value.Devices) == 0 {
		return model.PrplTopology{}, fmt.Errorf("prplMesh topology contains no devices")
	}
	return value, nil
}
