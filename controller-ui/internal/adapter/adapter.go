package adapter

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"prplmesh-lab/controller-ui/internal/model"
)

func LoadNetworks(path string) ([]model.Network, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var file model.NetworkFile
	if err := json.Unmarshal(data, &file); err != nil {
		return nil, fmt.Errorf("decode network configuration: %w", err)
	}
	if len(file.Networks) == 0 {
		return nil, fmt.Errorf("network configuration contains no networks")
	}
	seenSSID := make(map[string]bool)
	for index := range file.Networks {
		network := &file.Networks[index]
		if network.ID == "" || network.Name == "" || network.SSID == "" || network.HaulType == "" {
			return nil, fmt.Errorf("network %d is missing id, name, ssid, or haul_type", index)
		}
		if seenSSID[network.SSID] {
			return nil, fmt.Errorf("duplicate SSID %q", network.SSID)
		}
		seenSSID[network.SSID] = true
		if network.Enforcement == "" {
			network.Enforcement = "observed"
		}
	}
	return file.Networks, nil
}

type bssLocation struct {
	band    int
	channel int
}

// Transform adapts the external prplMesh Data Elements projection to the API
// contract used by the RDK EM CLI Web application.
func Transform(source model.PrplTopology, networks []model.Network, observed time.Time) (model.Snapshot, error) {
	if len(source.Devices) == 0 {
		return model.Snapshot{}, fmt.Errorf("cannot transform an empty topology")
	}
	if observed.IsZero() {
		observed = time.Now().UTC()
	}

	networkBySSID := make(map[string]model.Network, len(networks))
	states := make(map[string]*model.NetworkState, len(networks))
	for _, network := range networks {
		networkBySSID[network.SSID] = network
		states[network.ID] = &model.NetworkState{
			Network: network, VLANConfigured: network.VLANID != nil,
		}
	}

	devices := append([]model.PrplDevice(nil), source.Devices...)
	sort.SliceStable(devices, func(i, j int) bool {
		if devices[i].Role == "controller" {
			return true
		}
		if devices[j].Role == "controller" {
			return false
		}
		return devices[i].Name < devices[j].Name
	})

	positions := layout(devices)
	bssIndex := make(map[string]bssLocation)
	for _, device := range devices {
		for _, radio := range device.Radios {
			for _, bss := range radio.BSSes {
				bssIndex[normalizeMAC(bss.BSSID)] = bssLocation{band: bandNumber(radio.Band), channel: radio.Channel}
			}
		}
	}

	snapshot := model.Snapshot{
		Topology: model.Topology{Nodes: []model.TopologyNode{}, Edges: []model.TopologyEdge{}},
		Devices:  []model.Device{}, Clients: []model.Client{}, BSSes: []model.BSSInventory{},
		GeneratedAt: observed, Source: source.Source,
	}
	for _, device := range devices {
		groups := make(map[string]*model.HaulVisual)
		staList := make([]model.STAVisual, 0)
		activeClients := 0
		for _, radio := range device.Radios {
			band := bandNumber(radio.Band)
			for _, bss := range radio.BSSes {
				network, found := networkBySSID[bss.SSID]
				if !found {
					network = model.Network{
						ID: slug(bss.SSID), Name: bss.SSID, SSID: bss.SSID,
						HaulType: "Fronthaul", Enforcement: "observed",
					}
					networkBySSID[bss.SSID] = network
					states[network.ID] = &model.NetworkState{Network: network}
				}
				vlan := 0
				if network.VLANID != nil {
					vlan = *network.VLANID
				}
				// Key by network identity rather than visual role. This permits two
				// independent fronthaul SSIDs to retain separate bubbles/colors.
				group := groups[network.ID]
				if group == nil {
					group = &model.HaulVisual{
						Name: network.HaulType, SSID: network.SSID, VLANID: vlan,
						VLANActive: network.VLANID != nil, BSSList: []model.BSSVisual{},
					}
					groups[network.ID] = group
				}
				group.BSSList = append(group.BSSList, model.BSSVisual{
					BSSID: normalizeMAC(bss.BSSID), VapMode: 0, HaulType: network.HaulType,
					VLANID: vlan, Band: band, IEEE: "802.11ax", SSID: bss.SSID,
				})
				states[network.ID].BSSCount++
				snapshot.BSSes = append(snapshot.BSSes, model.BSSInventory{
					BSSID: normalizeMAC(bss.BSSID), DeviceID: normalizeMAC(device.ID),
					RadioID: normalizeMAC(radio.ID), Band: band, Channel: radio.Channel,
					SSID: bss.SSID, HaulType: network.HaulType, VLANID: network.VLANID,
				})

				for _, station := range bss.Clients {
					activeClients++
					states[network.ID].ClientCount++
					name, kind := clientIdentity(station)
					staList = append(staList, model.STAVisual{
						STAMAC: normalizeMAC(station.ID), Name: name, ClientType: kind, Band: band,
						Channel: radio.Channel, BSSID: normalizeMAC(bss.BSSID), SSID: bss.SSID,
					})
					connected := observed.Add(-time.Duration(station.LastConnectSeconds) * time.Second)
					metricObserved := time.Time{}
					if parsed, err := time.Parse(time.RFC3339Nano, station.SignalUpdatedAt); err == nil {
						metricObserved = parsed
					}
					rssi := 0
					quality := 0
					if station.SignalRaw > 0 {
						rssi = int(station.SignalDBM)
						quality = clamp(2*(rssi+100), 0, 100)
					}
					ip := station.IPv4
					if ip == "0" {
						ip = ""
					}
					snapshot.Clients = append(snapshot.Clients, model.Client{
						MAC: normalizeMAC(station.ID), Hostname: name, IPAddress: ip,
						ConnectedAP: normalizeMAC(device.ID), ConnectedBSSID: normalizeMAC(bss.BSSID),
						Band: band, Channel: radio.Channel, ConnectionTime: connected,
						DeviceType: kind, Manufacturer: "hwsim", LastActivity: observed,
						ClientMetrics: model.ClientMetrics{
							RCPI: station.SignalRaw, RSSI: rssi, LastUpdated: metricObserved,
							LinkQuality: quality, AssociationUptime: station.LastConnectSeconds,
						},
					})
				}
			}
		}

		hauls := make([]model.HaulVisual, 0, len(groups))
		for _, group := range groups {
			hauls = append(hauls, *group)
		}
		sort.Slice(hauls, func(i, j int) bool { return hauls[i].Name < hauls[j].Name })
		sort.Slice(staList, func(i, j int) bool { return staList[i].STAMAC < staList[j].STAMAC })
		position := positions[normalizeMAC(device.ID)]
		role := "Agent"
		modelName := "prplMesh Agent"
		if device.Role == "controller" {
			role = "Controller"
			modelName = "prplMesh Controller"
		}
		nodeName := displayName(device)
		snapshot.Topology.Nodes = append(snapshot.Topology.Nodes, model.TopologyNode{
			ID: normalizeMAC(device.ID), Name: nodeName, HaulTypes: hauls,
			X: position[0], Y: position[1], Fixed: map[string]bool{"x": true, "y": true},
			STAList: staList, UpstreamBSSID: normalizeMAC(device.Backhaul.MAC),
			BackhaulMedia: mediaType(device.Backhaul.Type),
		})
		snapshot.Devices = append(snapshot.Devices, model.Device{
			MAC: normalizeMAC(device.ID), Role: role, Vendor: "prpl Foundation", Model: modelName,
			Status: "Online", LastSeen: observed, Uptime: "reported by controller",
			BackhaulType: mediaType(device.Backhaul.Type),
			Capabilities: model.Capability{
				Firmware: device.SoftwareVersion, SerialNumber: normalizeMAC(device.ID),
				MaxMeshLinks: len(device.Radios), SupportedBands: []string{"2.4 GHz", "5 GHz", "6 GHz"},
			},
			Metrics: model.DeviceMetrics{ActiveClients: activeClients, LastUpdated: observed},
		})
	}

	for _, device := range devices {
		if device.Role == "controller" || device.Backhaul.ParentID == "" {
			continue
		}
		location := bssIndex[normalizeMAC(device.Backhaul.MAC)]
		snapshot.Topology.Edges = append(snapshot.Topology.Edges, model.TopologyEdge{
			From: normalizeMAC(device.Backhaul.ParentID), To: normalizeMAC(device.ID),
			Band: location.band, Channel: location.channel,
			UpstreamBSSID: normalizeMAC(device.Backhaul.MAC), MediaType: mediaType(device.Backhaul.Type),
		})
	}
	for _, device := range devices {
		if device.Role != "controller" {
			continue
		}
		identity := "controller:" + normalizeMAC(device.ID)
		position := positions[normalizeMAC(device.ID)]
		snapshot.Topology.Nodes = append(snapshot.Topology.Nodes, model.TopologyNode{
			ID: identity, Name: "Controller", HaulTypes: []model.HaulVisual{}, STAList: []model.STAVisual{},
			X: position[0], Y: position[1] - 50, Fixed: map[string]bool{"x": true, "y": true},
			BackhaulMedia: "Colocated",
		})
		snapshot.Topology.Edges = append(snapshot.Topology.Edges, model.TopologyEdge{
			From: identity, To: normalizeMAC(device.ID), MediaType: "Colocated",
		})
	}

	for _, state := range states {
		snapshot.Networks = append(snapshot.Networks, *state)
	}
	sort.Slice(snapshot.Networks, func(i, j int) bool { return snapshot.Networks[i].ID < snapshot.Networks[j].ID })
	sort.Slice(snapshot.Clients, func(i, j int) bool { return snapshot.Clients[i].MAC < snapshot.Clients[j].MAC })
	sort.Slice(snapshot.BSSes, func(i, j int) bool { return snapshot.BSSes[i].BSSID < snapshot.BSSes[j].BSSID })
	return snapshot, nil
}

func layout(devices []model.PrplDevice) map[string][2]float64 {
	depth := make(map[string]int)
	parent := make(map[string]string)
	for _, device := range devices {
		parent[normalizeMAC(device.ID)] = normalizeMAC(device.Backhaul.ParentID)
	}
	var resolve func(string, map[string]bool) int
	resolve = func(id string, seen map[string]bool) int {
		if value, ok := depth[id]; ok {
			return value
		}
		if seen[id] || parent[id] == "" {
			depth[id] = 0
			return 0
		}
		seen[id] = true
		depth[id] = resolve(parent[id], seen) + 1
		return depth[id]
	}
	levels := make(map[int][]string)
	for _, device := range devices {
		id := normalizeMAC(device.ID)
		d := resolve(id, make(map[string]bool))
		levels[d] = append(levels[d], id)
	}
	positions := make(map[string][2]float64)
	for d, ids := range levels {
		sort.Strings(ids)
		for index, id := range ids {
			y := (float64(index) - float64(len(ids)-1)/2) * 260
			positions[id] = [2]float64{float64(d) * 300, y}
		}
	}
	return positions
}

func bandNumber(value string) int {
	switch {
	case strings.HasPrefix(value, "2.4"):
		return 0
	case strings.HasPrefix(value, "5"):
		return 1
	case strings.HasPrefix(value, "6"):
		return 3
	default:
		return -1
	}
}

func clientIdentity(client model.PrplClient) (string, string) {
	parts := strings.Split(normalizeMAC(client.ID), ":")
	if len(parts) == 6 {
		ordinal, err := strconv.ParseUint(parts[4], 16, 8)
		if err == nil {
			if parts[3] == "20" {
				return fmt.Sprintf("iot-%02d", ordinal), "IoT Device"
			}
			if parts[3] == "10" {
				return fmt.Sprintf("sta-%02d", ordinal), "WLAN Client"
			}
		}
	}
	if client.Name != "" {
		return client.Name, "WLAN Client"
	}
	return normalizeMAC(client.ID), "WLAN Client"
}

func displayName(device model.PrplDevice) string {
	if device.Role == "controller" {
		return "Agent-1"
	}
	if strings.HasPrefix(device.Name, "agent-") {
		return "Extender-" + strings.TrimPrefix(device.Name, "agent-")
	}
	if device.Name != "" {
		return device.Name
	}
	return "Extender"
}

func mediaType(value string) string {
	if strings.EqualFold(value, "Wi-Fi") || strings.Contains(strings.ToLower(value), "wireless") {
		return "Wireless LAN"
	}
	if value == "" || strings.EqualFold(value, "None") {
		return "None"
	}
	return value
}

func normalizeMAC(value string) string { return strings.ToLower(strings.TrimSpace(value)) }
func slug(value string) string         { return strings.ReplaceAll(strings.ToLower(value), "_", "-") }
func clamp(value, low, high int) int {
	if value < low {
		return low
	}
	if value > high {
		return high
	}
	return value
}
