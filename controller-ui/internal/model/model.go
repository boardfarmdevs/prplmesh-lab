package model

import "time"

// Network declares how an SSID is presented. VLANID is nil for an untagged
// network. A non-nil VLAN is descriptive until the underlying EasyMesh stack
// has independently proven traffic-separation enforcement.
type Network struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	SSID        string `json:"ssid"`
	HaulType    string `json:"haul_type"`
	VLANID      *int   `json:"vlan_id"`
	Enforcement string `json:"enforcement"`
}

type NetworkFile struct {
	Networks []Network `json:"networks"`
}

type PrplTopology struct {
	GeneratedAt string       `json:"generated_at"`
	Source      string       `json:"source"`
	Devices     []PrplDevice `json:"devices"`
}

type PrplDevice struct {
	ID              string       `json:"id"`
	Name            string       `json:"name"`
	Role            string       `json:"role"`
	Profile         int          `json:"profile"`
	SoftwareVersion string       `json:"software_version"`
	Backhaul        PrplBackhaul `json:"backhaul"`
	Radios          []PrplRadio  `json:"radios"`
}

type PrplBackhaul struct {
	ParentID string `json:"parent_id"`
	Type     string `json:"type"`
	MAC      string `json:"mac"`
}

type PrplRadio struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Band        string    `json:"band"`
	OpClass     int       `json:"opclass"`
	Channel     int       `json:"channel"`
	Utilization int       `json:"utilization"`
	BSSes       []PrplBSS `json:"bsses"`
}

type PrplBSS struct {
	BSSID     string       `json:"bssid"`
	SSID      string       `json:"ssid"`
	Fronthaul bool         `json:"fronthaul"`
	Backhaul  bool         `json:"backhaul"`
	Clients   []PrplClient `json:"clients"`
}

type PrplClient struct {
	ID                 string  `json:"id"`
	Name               string  `json:"name"`
	Cohort             string  `json:"cohort"`
	SignalRaw          int     `json:"signal_raw"`
	SignalDBM          float64 `json:"signal_dbm"`
	SignalUpdatedAt    string  `json:"signal_updated_at"`
	IPv4               string  `json:"ipv4"`
	LastConnectSeconds int64   `json:"last_connect_seconds"`
}

type Snapshot struct {
	Topology    Topology       `json:"topology"`
	Devices     []Device       `json:"devices"`
	Clients     []Client       `json:"clients"`
	BSSes       []BSSInventory `json:"bsses"`
	Networks    []NetworkState `json:"networks"`
	GeneratedAt time.Time      `json:"generated_at"`
	Source      string         `json:"source"`
}

type Topology struct {
	Nodes           []TopologyNode   `json:"nodes"`
	Edges           []TopologyEdge   `json:"edges"`
	SteeringEvent   *SteeringEvent   `json:"steeringEvent,omitempty"`
	SteeringActions []SteeringAction `json:"steeringActions,omitempty"`
}

type SteeringAction struct {
	Station     string    `json:"sta_mac"`
	Source      string    `json:"source_bssid"`
	Target      string    `json:"target_bssid"`
	Method      string    `json:"method"`
	RequestedAt time.Time `json:"requested_at"`
	Evidence    string    `json:"evidence"`
}

// SteeringEvent is an operator intent hint for the topology renderer. The
// controller model can only report a roam after it happens, so steering tools
// publish this short-lived event before issuing BTM. It does not alter the
// EasyMesh model or perform the steer itself.
type SteeringEvent struct {
	ID         string    `json:"id"`
	STAMAC     string    `json:"sta_mac"`
	ClientName string    `json:"client_name"`
	TargetName string    `json:"target_name"`
	Phase      string    `json:"phase"`
	ReceivedAt time.Time `json:"received_at"`
	ExpiresAt  time.Time `json:"expires_at"`
}

type TopologyNode struct {
	ID            string          `json:"id"`
	Name          string          `json:"name"`
	HaulTypes     []HaulVisual    `json:"haulTypes"`
	X             float64         `json:"x"`
	Y             float64         `json:"y"`
	Fixed         map[string]bool `json:"fixed"`
	STAList       []STAVisual     `json:"STAList"`
	UpstreamBSSID string          `json:"upstreamBSSID"`
	BackhaulMedia string          `json:"backhaulMedia"`
}

type TopologyEdge struct {
	From          string `json:"from"`
	To            string `json:"to"`
	Band          int    `json:"band"`
	Channel       int    `json:"channel"`
	UpstreamBSSID string `json:"upstreamBSSID"`
	BackhaulSTA   string `json:"backhaulSTA,omitempty"`
	MediaType     string `json:"mediaType"`
}

type HaulVisual struct {
	Name       string      `json:"name"`
	SSID       string      `json:"ssid"`
	VLANID     int         `json:"VlanId"`
	VLANActive bool        `json:"vlanConfigured"`
	BSSList    []BSSVisual `json:"BSSList"`
}

type BSSVisual struct {
	BSSID    string `json:"BSSID"`
	MLDAddr  string `json:"MLDAddr"`
	VapMode  int    `json:"vapMode"`
	HaulType string `json:"haulType"`
	VLANID   int    `json:"VlanId"`
	Band     int    `json:"Band"`
	IEEE     string `json:"IEEE"`
	SSID     string `json:"ssid"`
}

type STAVisual struct {
	STAMAC     string `json:"staMAC"`
	Name       string `json:"name,omitempty"`
	ClientType string `json:"clientType"`
	MLDAddr    string `json:"MLDAddr"`
	Band       int    `json:"band"`
	Channel    int    `json:"channel"`
	BSSID      string `json:"bssid"`
	SSID       string `json:"ssid"`
}

type Device struct {
	MAC          string        `json:"mac"`
	Role         string        `json:"role"`
	Vendor       string        `json:"vendor"`
	Model        string        `json:"model"`
	IPAddress    string        `json:"ip_address"`
	Status       string        `json:"status"`
	LastSeen     time.Time     `json:"last_seen"`
	Uptime       string        `json:"uptime"`
	BackhaulType string        `json:"backhaul_type,omitempty"`
	Capabilities Capability    `json:"capabilities"`
	Metrics      DeviceMetrics `json:"metrics"`
}

type Capability struct {
	WiFi7Support   bool     `json:"wifi7_support"`
	MaxMeshLinks   int      `json:"max_mesh_links"`
	Firmware       string   `json:"firmware"`
	SerialNumber   string   `json:"serial_number"`
	SupportedBands []string `json:"supported_bands"`
}

type DeviceMetrics struct {
	ActiveClients int       `json:"active_clients"`
	LastUpdated   time.Time `json:"last_updated"`
}

type Client struct {
	MAC            string        `json:"mac"`
	Hostname       string        `json:"hostname"`
	IPAddress      string        `json:"ip_address"`
	ConnectedAP    string        `json:"connected_ap_mac"`
	ConnectedBSSID string        `json:"connected_bssid"`
	Band           int           `json:"band"`
	Channel        int           `json:"channel"`
	ConnectionTime time.Time     `json:"connection_time"`
	DeviceType     string        `json:"device_type"`
	Manufacturer   string        `json:"manufacturer"`
	LastActivity   time.Time     `json:"last_activity"`
	ClientMetrics  ClientMetrics `json:"client_metrics"`
}

type ClientMetrics struct {
	RCPI              int       `json:"rcpi"`
	RSSI              int       `json:"rssi_dbm"`
	SNR               int       `json:"snr_db"`
	LastUpdated       time.Time `json:"last_updated"`
	LinkQuality       int       `json:"link_quality_percent"`
	AssociationUptime int64     `json:"association_uptime_seconds"`
}

type BSSInventory struct {
	BSSID    string `json:"bssid"`
	DeviceID string `json:"device_id"`
	RadioID  string `json:"radio_id"`
	Band     int    `json:"band"`
	Channel  int    `json:"channel"`
	SSID     string `json:"ssid"`
	HaulType string `json:"haul_type"`
	VLANID   *int   `json:"vlan_id"`
}

type NetworkState struct {
	Network
	VLANConfigured bool `json:"vlan_configured"`
	BSSCount       int  `json:"bss_count"`
	ClientCount    int  `json:"client_count"`
}
