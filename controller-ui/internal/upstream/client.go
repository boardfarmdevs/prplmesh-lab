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

// Client reads the external, read-only prplMesh topology API. It retains the
// last valid response across a short source outage so a two-second UI refresh
// cannot replace a valid topology with an empty diagram.
type Client struct {
	url    string
	http   *http.Client
	ttl    time.Duration
	mu     sync.RWMutex
	value  model.PrplTopology
	loaded time.Time
}

func New(url string, timeout, ttl time.Duration) *Client {
	return &Client{
		url:  url,
		http: &http.Client{Timeout: timeout},
		ttl:  ttl,
	}
}

func (c *Client) URL() string { return c.url }

func (c *Client) Get(ctx context.Context) (model.PrplTopology, error) {
	c.mu.RLock()
	if !c.loaded.IsZero() && time.Since(c.loaded) < c.ttl {
		value := c.value
		c.mu.RUnlock()
		return value, nil
	}
	c.mu.RUnlock()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.url, nil)
	if err != nil {
		return model.PrplTopology{}, err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return c.staleOrError(fmt.Errorf("prplMesh topology API: %w", err))
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return c.staleOrError(fmt.Errorf("prplMesh topology API returned %s", resp.Status))
	}

	var value model.PrplTopology
	if err := json.NewDecoder(resp.Body).Decode(&value); err != nil {
		return c.staleOrError(fmt.Errorf("decode prplMesh topology: %w", err))
	}
	if len(value.Devices) == 0 {
		return c.staleOrError(fmt.Errorf("prplMesh topology contains no devices"))
	}

	c.mu.Lock()
	c.value = value
	c.loaded = time.Now()
	c.mu.Unlock()
	return value, nil
}

func (c *Client) staleOrError(cause error) (model.PrplTopology, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if !c.loaded.IsZero() {
		return c.value, nil
	}
	return model.PrplTopology{}, cause
}
