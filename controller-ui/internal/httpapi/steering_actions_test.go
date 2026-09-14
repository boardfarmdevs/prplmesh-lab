package httpapi

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"prplmesh-lab/controller-ui/internal/model"
)

func TestExplicitSteeringMethodReports(test *testing.T) {
	server, err := New(fakeSource{}, nil, log.New(io.Discard, "", 0))
	if err != nil {
		test.Fatal(err)
	}
	submit := func(method, phase, source, target string) int {
		body, err := json.Marshal(map[string]string{"sta_mac": "02:00:00:10:01:00",
			"client_name": "sta-01", "target_name": "Extender-1", "phase": phase,
			"method": method, "source_bssid": source, "target_bssid": target})
		if err != nil {
			test.Fatal(err)
		}
		response := httptest.NewRecorder()
		server.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/api/v1/steering-event", bytes.NewReader(body)))
		return response.Code
	}
	source, target := "02:00:00:00:01:00", "02:00:00:00:04:00"
	for _, input := range [][4]string{
		{"btm-request", "completed", source, target},
		{"non-btm", "planned", source, target},
		{"non-btm", "completed", "invalid", target},
		{"non-btm", "completed", source, source},
	} {
		if status := submit(input[0], input[1], input[2], input[3]); status != 400 {
			test.Fatal(input, status)
		}
	}
	if status := submit("", "completed", source, target); status != 202 || len(server.currentSteeringActions(time.Now())) != 0 {
		test.Fatal("unspecified methods must remain unknown", status)
	}
	for index := 0; index < 101; index++ {
		if status := submit("non-btm", "completed", source, target); status != 202 {
			test.Fatal(status)
		}
	}
	actions := server.currentSteeringActions(time.Now())
	if len(actions) != 100 || actions[0].Evidence != "operator-report" {
		test.Fatal("invalid bounded report history", actions)
	}
	if len(server.currentSteeringActions(time.Now().Add(31*time.Second))) != 0 {
		test.Fatal("reports failed to expire")
	}
}

func TestRoomLayoutRouteUsesConfiguredRoomNotTopology(test *testing.T) {
	room := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/api/demo/mesh-layout" {
			test.Error(request.URL.Path)
		}
		_, _ = writer.Write([]byte(`{"schema":"easymesh.room-layout.v1","world":"room-name"}`))
	}))
	defer room.Close()
	test.Setenv("EASYMESH_ROOM_URL", room.URL)
	server, err := New(fakeSource{value: model.PrplTopology{}}, nil, log.New(io.Discard, "", 0))
	if err != nil {
		test.Fatal(err)
	}
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/v1/room-layout", nil))
	if response.Code != 200 || !bytes.Contains(response.Body.Bytes(), []byte("room-name")) {
		test.Fatal(response.Code, response.Body.String())
	}
}
