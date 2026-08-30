package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"testing"

	"prplmesh-lab/controller-ui/internal/model"
)

type fakeSource struct{ value model.PrplTopology }

func (f fakeSource) Get(context.Context) (model.PrplTopology, error) { return f.value, nil }
func (f fakeSource) URL() string                                     { return "http://example.test/topology" }

func TestLiveAndStubRoutes(t *testing.T) {
	source := fakeSource{value: model.PrplTopology{Source: "test", Devices: []model.PrplDevice{{
		ID: "02:00:00:27:01:01", Name: "controller", Role: "controller",
	}}}}
	server, err := New(source, []model.Network{{ID: "private", Name: "Private", SSID: "private_ssid", HaulType: "Fronthaul"}}, log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatal(err)
	}

	for _, path := range []string{"/", "/health", "/api/v1/topology", "/api/v1/networks"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		server.Handler().ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s returned %d: %s", path, response.Code, response.Body.String())
		}
	}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/firmware/status", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusNotImplemented {
		t.Fatalf("stub returned %d", response.Code)
	}
}

func TestSteeringEventAppearsInTopology(t *testing.T) {
	source := fakeSource{value: model.PrplTopology{Source: "test", Devices: []model.PrplDevice{{
		ID: "02:00:00:27:01:01", Name: "controller", Role: "controller",
	}}}}
	server, err := New(source, nil, log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatal(err)
	}
	body := bytes.NewBufferString(`{"sta_mac":"02:00:00:10:01:00","client_name":"sta-01","target_name":"agent-1","phase":"planned"}`)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/steering-event", body)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("event returned %d: %s", response.Code, response.Body.String())
	}

	request = httptest.NewRequest(http.MethodGet, "/api/v1/topology", nil)
	response = httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	var topology model.Topology
	if err := json.NewDecoder(response.Body).Decode(&topology); err != nil {
		t.Fatal(err)
	}
	if topology.SteeringEvent == nil || topology.SteeringEvent.Phase != "planned" ||
		topology.SteeringEvent.STAMAC != "02:00:00:10:01:00" {
		t.Fatalf("topology steering event=%+v", topology.SteeringEvent)
	}
}
