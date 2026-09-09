package adapter

import (
	"testing"
	"time"

	"prplmesh-lab/controller-ui/internal/model"
)

func TestTransformDualSSIDTriBandTopology(t *testing.T) {
	vlan := 200
	networks := []model.Network{
		{ID: "private", Name: "Private", SSID: "private_ssid", HaulType: "Fronthaul"},
		{ID: "iot", Name: "IoT", SSID: "iot_ssid", HaulType: "Iot", VLANID: &vlan},
		{ID: "backhaul", Name: "Backhaul", SSID: "mesh_backhaul", HaulType: "Backhaul"},
	}
	source := model.PrplTopology{Source: "test", Devices: []model.PrplDevice{
		{
			ID: "02:00:00:27:01:01", Name: "controller", Role: "controller", SoftwareVersion: "6.0.0",
			Radios: []model.PrplRadio{{
				ID: "02:00:00:00:01:00", Band: "5 GHz", Channel: 36,
				BSSes: []model.PrplBSS{
					{BSSID: "02:00:00:00:01:00", SSID: "private_ssid", Clients: []model.PrplClient{{ID: "02:00:00:10:0a:00", SignalRaw: 118, SignalDBM: -51}}},
					{BSSID: "02:00:00:00:01:01", SSID: "iot_ssid"},
					{BSSID: "02:00:00:00:01:02", SSID: "mesh_backhaul"},
				},
			}},
		},
		{
			ID: "02:00:00:27:02:01", Name: "agent-1", Role: "agent", SoftwareVersion: "6.0.0",
			Backhaul: model.PrplBackhaul{ParentID: "02:00:00:27:01:01", Type: "Wi-Fi", MAC: "02:00:00:00:01:02"},
			Radios: []model.PrplRadio{{
				ID: "02:00:00:00:05:00", Band: "6 GHz", Channel: 5,
				BSSes: []model.PrplBSS{
					{BSSID: "02:00:00:00:05:00", SSID: "private_ssid"},
					{BSSID: "02:00:00:00:05:01", SSID: "iot_ssid", Clients: []model.PrplClient{{ID: "02:00:00:20:0a:00", SignalRaw: 88, SignalDBM: -66}}},
					{BSSID: "02:00:00:00:05:02", SSID: "mesh_backhaul"},
				},
			}},
		},
	}}

	snapshot, err := Transform(source, networks, time.Unix(1000, 0).UTC())
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Topology.Nodes) != 3 || len(snapshot.Topology.Edges) != 2 {
		t.Fatalf("topology=%+v", snapshot.Topology)
	}
	if len(snapshot.Clients) != 2 {
		t.Fatalf("clients=%d", len(snapshot.Clients))
	}
	if snapshot.Clients[0].Hostname != "sta-10" || snapshot.Clients[1].Hostname != "iot-10" {
		t.Fatalf("client names=%q,%q", snapshot.Clients[0].Hostname, snapshot.Clients[1].Hostname)
	}
	if snapshot.Topology.Nodes[0].STAList[0].Name != "sta-10" ||
		snapshot.Topology.Nodes[1].STAList[0].Name != "iot-10" {
		t.Fatalf("topology client names=%q,%q", snapshot.Topology.Nodes[0].STAList[0].Name,
			snapshot.Topology.Nodes[1].STAList[0].Name)
	}
	if snapshot.Topology.Edges[0].Band != 1 || snapshot.Topology.Edges[0].Channel != 36 {
		t.Fatalf("backhaul edge=%+v", snapshot.Topology.Edges[0])
	}
	if snapshot.Topology.Nodes[1].Name != "Extender-1" {
		t.Fatalf("node name=%q", snapshot.Topology.Nodes[1].Name)
	}
	if len(snapshot.Topology.Nodes[1].HaulTypes) != 3 {
		t.Fatalf("hauls=%+v", snapshot.Topology.Nodes[1].HaulTypes)
	}
	var foundIoT bool
	for _, network := range snapshot.Networks {
		if network.ID == "iot" {
			foundIoT = network.VLANConfigured && network.VLANID != nil && *network.VLANID == 200
		}
	}
	if !foundIoT {
		t.Fatalf("IoT VLAN state=%+v", snapshot.Networks)
	}
}

func TestTransformKeepsSameRoleSSIDsSeparate(t *testing.T) {
	networks := []model.Network{
		{ID: "private", Name: "Private", SSID: "private_ssid", HaulType: "Fronthaul"},
		{ID: "guest", Name: "Guest", SSID: "guest_ssid", HaulType: "Fronthaul"},
	}
	source := model.PrplTopology{Devices: []model.PrplDevice{{
		ID: "02:00:00:27:01:01", Role: "controller",
		Radios: []model.PrplRadio{{Band: "5 GHz", Channel: 36, BSSes: []model.PrplBSS{
			{BSSID: "02:00:00:00:01:00", SSID: "private_ssid"},
			{BSSID: "02:00:00:00:01:03", SSID: "guest_ssid"},
		}}},
	}}}
	snapshot, err := Transform(source, networks, time.Unix(1000, 0).UTC())
	if err != nil {
		t.Fatal(err)
	}
	hauls := snapshot.Topology.Nodes[0].HaulTypes
	if len(hauls) != 2 || hauls[0].SSID == hauls[1].SSID {
		t.Fatalf("same-role SSIDs collapsed: %+v", hauls)
	}
}
