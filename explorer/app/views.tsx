import { useState } from 'react';
import {
  Network,
  Router,
  Radio,
  Laptop,
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Check,
  Info,
  CircleCheck,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { entries, source } from './system';
export type Inspect = (
  id: string,
  extra?: { title: string; properties: [string, string][] },
) => void;

export function Topology({ inspect }: { inspect: Inspect }) {
  const [shape, setShape] = useState('star');
  const positions = [40, 305, 570, 835];
  const parents =
    shape === 'star'
      ? ['Agent-1', 'Agent-1', 'Agent-1', 'Agent-1']
      : shape === 'chain'
        ? ['Agent-1', 'Extender-1', 'Extender-2', 'Extender-3']
        : ['Agent-1', 'Extender-1', 'Extender-1', 'Extender-3'];
  function clients(group: number) {
    return (
      <div className="client-group">
        {Array.from({ length: 4 }, (_, i) => {
          const cohort = i < 2 ? 'Private' : 'IoT';
          const n = group * 2 + (i % 2) + 1;
          const name = `${i < 2 ? 'STA' : 'IoT'}-${n.toString(16).toUpperCase().padStart(2, '0')}`;
          const ap = group === 0 ? 'Agent-1' : `Extender-${group}`;
          const band = ['2.4', '5', '6'][(group + i) % 3];
          return (
            <button
              key={name}
              className={`top-client ${i < 2 ? 'private' : 'iot'}`}
              onClick={() =>
                inspect('client', {
                  title: name,
                  properties: [
                    ['Example placement', ap],
                    ['SSID', i < 2 ? 'private_ssid' : 'iot_ssid'],
                    ['Example band', `${band} GHz`],
                    ['Data status', 'Illustrative assignment; no live metrics'],
                  ],
                })
              }
            >
              <Laptop size={16} />
              <span>
                {name}
                <small>
                  {band} GHz · {cohort}
                </small>
              </span>
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <section className="topology-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">PRPLMESH CONTROLLER UI · :8091</div>
          <h2>Network Topology</h2>
          <p>An explorable example of the native topology screen.</p>
        </div>
        <button className="quiet-button" onClick={() => inspect('cli')}>
          How this screen gets its data <ArrowUpRight size={15} />
        </button>
      </div>
      <div className="topology-stats">
        {[
          ['5', 'Mesh devices'],
          ['15', 'Logical radios'],
          ['100', 'Provisioned clients'],
          ['20', 'Example active clients'],
        ].map(([v, l]) => (
          <div key={l}>
            <strong>{v}</strong>
            <span>{l}</span>
          </div>
        ))}
        <div className="model-badge">
          <Info size={17} />
          <span>
            Illustrative topology
            <br />
            <small>Example placements · no live signal values</small>
          </span>
        </div>
      </div>
      <div className="topology-controls">
        <Tabs value={shape} onValueChange={(v) => setShape(String(v))}>
          <TabsList className="segmented">
            <TabsTrigger value="star">Star</TabsTrigger>
            <TabsTrigger value="chain">Chain</TabsTrigger>
            <TabsTrigger value="branch">Branch</TabsTrigger>
          </TabsList>
        </Tabs>
        <span>
          Explore backhaul arrangements; changing this view only changes the
          diagram.
        </span>
      </div>
      <div className="topology-scroll">
        <div className="topology-canvas">
          <svg
            className="topology-wires"
            viewBox="0 0 1100 635"
            aria-hidden="true"
          >
            <path className="local" d="M550 86V124" />
            <path className="fh" d="M660 176H730" />
            {positions.map((x, i) => {
              let d;
              if (parents[i] === 'Agent-1') d = `M550 209V275H${x + 105}V330`;
              else {
                let p = Number(parents[i].slice(-1)) - 1;
                d =
                  shape === 'chain'
                    ? `M${positions[p] + 210} 366H${x}`
                    : `M${positions[p] + 105} 330V${294 - p * 15}H${x + 105}V330`;
              }
              return <path key={i} className="bh" d={d} />;
            })}
            {positions.map((x) => (
              <path key={x} className="fh" d={`M${x + 105} 410V443`} />
            ))}
          </svg>
          <button
            className="top-node controller-node"
            onClick={() => inspect('controller')}
          >
            <Network size={21} />
            <span>
              Controller<small>Control-plane identity · no WLAN BSS</small>
            </span>
          </button>
          <button
            className="top-node agent-node"
            onClick={() => inspect('gateway')}
          >
            <Router size={27} />
            <span>
              Agent-1<small>Colocated in prpl-controller</small>
            </span>
            <b>3 radios</b>
          </button>
          <span className="local-caption">local / colocated</span>
          <div className="gateway-clients">
            <div className="group-caption">Agent-1 fronthaul</div>
            {clients(0)}
          </div>
          {positions.map((x, i) => (
            <div className="extender-column" style={{ left: x }} key={i}>
              <button
                className="top-node extender-node"
                onClick={() =>
                  inspect('extender', {
                    title: `Extender-${i + 1}`,
                    properties: [
                      [
                        'Container',
                        `prpl-agent-${String(i + 1).padStart(2, '0')}`,
                      ],
                      ['Example parent', parents[i]],
                      ['Arrangement', shape],
                      ['Radio count', '3 radios / 3 PHYs'],
                    ],
                  })
                }
              >
                <Radio size={24} />
                <span>
                  Extender-{i + 1}
                  <small>3 radios · 5 GHz backhaul</small>
                </span>
              </button>
              <div className="client-branch">
                <div className="group-caption">
                  Fronthaul · 4 example clients
                </div>
                {clients(i + 1)}
              </div>
            </div>
          ))}
          <div className="topology-key">
            <span className="line-key dashed" />5 GHz backhaul{' '}
            <span className="line-key pink-line" />
            Client fronthaul <span className="line-key" />
            Local control
          </div>
        </div>
      </div>
      <div className="topology-explanation">
        <Info size={19} />
        <p>
          <strong>Five devices, not six.</strong> The Controller and Agent-1 are
          separate roles in the same gateway. The four other physical devices
          are extenders. Actual clients, BSSIDs, signal and parentage come from
          the controller model; the assignments above are examples.
        </p>
        <button onClick={() => inspect('database')}>
          Inspect the model <ArrowRight size={15} />
        </button>
      </div>
    </section>
  );
}

type Step = { title: string; body: string; ids: string[]; wire: string };
const journeys: Record<
  string,
  { title: string; result: string; steps: Step[] }
> = {
  data: {
    title: 'Client traffic',
    result:
      'A WLAN address, physical ownership and traffic through the mesh must agree.',
    steps: [
      {
        title: 'Associate and obtain an address',
        body: 'The real client supplicant selects a fronthaul BSSID. The management interface is not the Wi-Fi data path.',
        ids: ['client', 'supplicant', 'dhcpclient'],
        wire: 'wlan0 → native association → WLAN IPv4',
      },
      {
        title: 'Transmit through the medium',
        body: 'Linux sends 802.11 frames through hwsim. wmediumd applies frequency-qualified directional conditions and returns actual delivery outcomes.',
        ids: ['client', 'hwsim', 'wmediumd'],
        wire: 'hwsim → generic netlink → wmediumd → receiving PHY',
      },
      {
        title: 'Bridge upstream',
        body: 'The extender forwards traffic through br-lan and its authorized wireless backhaul. Intermediate agents add wireless hops without changing the client identity.',
        ids: ['fronthaul', 'bridge', 'backhaul'],
        wire: 'Fronthaul → br-lan → four-address backhaul',
      },
      {
        title: 'Verify the data path',
        body: 'Tests bind the probe to the WLAN interface and compare the physical BSSID with native DataElements ownership. Internet reachability is a separate network configuration.',
        ids: ['gateway', 'database', 'tests'],
        wire: 'Kernel owner + NBAPI owner + WLAN delivery',
      },
    ],
  },
  steering: {
    title: 'Commanded steering',
    result: 'A command acknowledgement alone is not a completed roam.',
    steps: [
      {
        title: 'Collect native evidence',
        body: 'The adapter reads current ownership, serving metrics and eligible candidate measurements. Missing or stale observations block unsafe action.',
        ids: ['database', 'cli', 'optimizer'],
        wire: 'NBAPI + native reports → normalized snapshot',
      },
      {
        title: 'Apply bounded policy',
        body: 'The external optimizer compares eligible targets using unchanged dwell, hold and cooldown. It names an exact BSSID; it does not command a geometry-based reassociation.',
        ids: ['optimizer', 'steer'],
        wire: 'Evidence → policy → STA + target BSSID',
      },
      {
        title: 'Request native BTM',
        body: 'The controller sends the native steering transaction over IEEE 1905. The source agent and fronthaul worker ask hostapd to issue BSS transition management.',
        ids: ['controller', 'ieee1905', 'agent', 'hostapd'],
        wire: 'Controller → agent → hostapd BSS_TM_REQ',
      },
      {
        title: 'Verify and settle',
        body: 'Record the client response, physical reassociation, model update, fresh metrics and receiver traffic. Keep policy delay separate from native convergence time.',
        ids: ['11v', 'client', 'tests'],
        wire: 'BTM + kernel link + NBAPI + traffic + settling',
      },
    ],
  },
  band: {
    title: 'Band steering',
    result:
      'Fresh client-received scans, native BTM, physical band and traffic prove the path—not an illustrated band label.',
    steps: [
      {
        title: 'Set up a supported profile',
        body: 'The live room validates actual bands and security, saves client settings and selects its starting condition. Setup is outside measured steering.',
        ids: ['room', 'band', 'supplicant'],
        wire: 'Capabilities + SSID + security → explicit profile',
      },
      {
        title: 'Receive candidate beacons',
        body: 'Passive scans use real home and temporary receive channels. The collector reads the correlated kernel BSS cache; world geometry is not a hidden observation oracle.',
        ids: ['hwsim', 'wmediumd', 'band'],
        wire: 'Receive context → beacons → BSS cache',
      },
      {
        title: 'Act and restore',
        body: 'A fresh eligible target passes the configured policy. Native BTM and WLAN traffic are verified; leaving the room restores the saved supplicant configuration.',
        ids: ['optimizer', '11v', 'tests'],
        wire: 'Fresh signal → bounded policy → native roam → restoration',
      },
    ],
  },
  onboarding: {
    title: 'Mesh onboarding',
    result:
      'Native inventory, rooted wireless parentage, AP service and traffic must converge together.',
    steps: [
      {
        title: 'Assign the device radios',
        body: 'The guest assigns three PHYs to each prpl mesh container. Native fronthaul workers and hostapd configure the separate bands.',
        ids: ['radios', 'hwsim', 'fronthaul'],
        wire: 'PHY ownership → wlan0 / wlan2 / wlan4',
      },
      {
        title: 'Authorize wireless backhaul',
        body: 'The backhaul station associates to a parent, completes security and joins br-lan through four-address forwarding.',
        ids: ['backhaul', 'hostapd', 'bridge'],
        wire: 'Association → authorization → forwarding',
      },
      {
        title: 'Discover and configure',
        body: 'IEEE 1905 autoconfiguration and WSC exchange establish native agent/radio/BSS configuration. Reports populate the DataElements model.',
        ids: ['ieee1905', 'controller', 'database'],
        wire: 'Autoconfiguration → WSC M1/M2 → native reports',
      },
    ],
  },
  rf: {
    title: 'RF feedback loop',
    result:
      'Configured stimulus, measured native evidence and optimizer decisions remain separate.',
    steps: [
      {
        title: 'Apply a world',
        body: 'Positions, walls, motion and presence compile into frequency-qualified RF controls. Unused clients remain provisioned but their radio paths are isolated.',
        ids: ['room', 'configurator', 'client'],
        wire: 'Geometry / presence → atomic RF changes + readback',
      },
      {
        title: 'Observe actual effects',
        body: 'The medium records real frame outcomes and modeled airtime. Native counters, survey and AP reports expose their provenance and freshness; unavailable is not zero.',
        ids: ['wmediumd', 'hwsim', 'console'],
        wire: 'Frame outcomes → counters / survey → native reports',
      },
      {
        title: 'Check pressure and rescue',
        body: 'Real counter pressure can veto a quieter-AP load action. A non-actuating guard-disabled shadow proves the held opportunity; weak-signal rescue is a separate native-BTM case.',
        ids: ['optimizer', 'tests', '11v'],
        wire: 'Fresh load + counters + signal → guarded decision',
      },
    ],
  },
};

export function ProtocolPaths({ inspect }: { inspect: Inspect }) {
  const [journey, setJourney] = useState('data');
  const [step, setStep] = useState(0);
  const j = journeys[journey];
  const s = j.steps[step];
  return (
    <section className="flows-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">FOLLOW THE BOUNDARIES</div>
          <h2>One system. Several paths.</h2>
          <p>
            Step through traffic, steering, a band change, onboarding, or RF
            feedback.
          </p>
        </div>
      </div>
      <Tabs
        value={journey}
        onValueChange={(v) => {
          setJourney(String(v));
          setStep(0);
        }}
      >
        <TabsList className="journey-tabs">
          <TabsTrigger value="data">Client traffic</TabsTrigger>
          <TabsTrigger value="steering">Commanded steering</TabsTrigger>
          <TabsTrigger value="band">Band steering</TabsTrigger>
          <TabsTrigger value="onboarding">Mesh onboarding</TabsTrigger>
          <TabsTrigger value="rf">RF feedback loop</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="journey-layout">
        <div className="step-list" aria-label="Steps">
          {j.steps.map((v, i) => (
            <button
              key={v.title}
              className={i === step ? 'current' : ''}
              aria-current={i === step ? 'step' : undefined}
              onClick={() => setStep(i)}
            >
              <span>
                {i < step ? (
                  <Check size={16} />
                ) : (
                  String(i + 1).padStart(2, '0')
                )}
              </span>
              {v.title}
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <article className="step-detail" aria-live="polite">
          <div className="eyebrow">
            {j.title} · {step + 1} / {j.steps.length}
          </div>
          <h3>{s.title}</h3>
          <p>{s.body}</p>
          <div className="path-blocks">
            {s.ids.map((id, i) => (
              <div className="path-block-wrap" key={id}>
                {i > 0 && <ArrowRight className="path-arrow" size={22} />}
                <button
                  className={`path-block ${entries[id].color}`}
                  onClick={() => inspect(id)}
                >
                  <span className="dot" />
                  {entries[id].title}
                  <ArrowUpRight size={14} />
                </button>
              </div>
            ))}
          </div>
          <div className="protocol-strip">{s.wire}</div>
          <div className="step-actions">
            <button
              className="quiet-button"
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
            >
              <ChevronLeft size={16} />
              Previous
            </button>
            <button
              className="action-button"
              onClick={() =>
                setStep(step === j.steps.length - 1 ? 0 : step + 1)
              }
            >
              {step === j.steps.length - 1 ? 'Start again' : 'Next boundary'}
              <ChevronRight size={16} />
            </button>
          </div>
        </article>
      </div>
      <div className="acceptance-note">
        <CircleCheck size={22} />
        <div>
          <strong>What proves this path works</strong>
          <p>{j.result}</p>
        </div>
      </div>
    </section>
  );
}

export function CurrentState({ inspect }: { inspect: Inspect }) {
  return (
    <section className="state-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">PINNED DOCUMENTATION · NOT LIVE STATUS</div>
          <h2>Evidence and qualification boundaries</h2>
          <p>
            Capabilities, observed results and remaining gates are deliberately
            separate.
          </p>
        </div>
      </div>
      <div className="state-grid">
        <article className="state-card">
          <div className="state-icon green">
            <CircleCheck />
          </div>
          <h3>Native foundation</h3>
          <ul>
            <li>
              Five mesh devices, fifteen radios, 100 provisioned client
              containers.
            </li>
            <li>
              The default room uses twenty clients; other rooms select their own
              active subset.
            </li>
            <li>
              Real prplMesh, hostapd, supplicant, IEEE 1905, BTM and wireless
              forwarding.
            </li>
            <li>
              Room geometry and RF delivery are simulated, not measured physical
              propagation.
            </li>
          </ul>
          <button onClick={() => inspect('gateway')}>
            Inspect the native stack <ArrowRight size={16} />
          </button>
        </article>
        <article className="state-card">
          <div className="state-icon purple">
            <Radio />
          </div>
          <h3>RF and policy</h3>
          <ul>
            <li>
              Directional signal/loss, receive contexts, native counters and
              modeled survey/load.
            </li>
            <li>
              Received-scan band steering with explicit capability and security
              checks.
            </li>
            <li>
              Bounded pressure veto and weak-signal rescue pass with unchanged
              policy.
            </li>
            <li>
              The pinned rescue run verifies the native target in 1.918 seconds;
              not a universal latency guarantee.
            </li>
          </ul>
          <button onClick={() => inspect('optimizer')}>
            Inspect decision boundaries <ArrowRight size={16} />
          </button>
        </article>
        <article className="state-card">
          <div className="state-icon amber">
            <Info />
          </div>
          <h3>No overclaims</h3>
          <ul>
            <li>
              No new all-green full suite or long-duration soak is claimed.
            </li>
            <li>
              Repeatability and clean-source acceptance remain separate gates.
            </li>
            <li>
              Modeled busy time is not calibrated physical channel capacity.
            </li>
            <li>BTM does not prove 802.11k or 802.11r qualification.</li>
          </ul>
          <button onClick={() => inspect('tests')}>
            Inspect acceptance evidence <ArrowRight size={16} />
          </button>
        </article>
        <article className="state-card">
          <div className="state-icon blue">
            <Laptop />
          </div>
          <h3>Try it safely</h3>
          <p>
            Every diagram here is illustrative. The sibling room sandbox plays
            scenarios locally, without live measurements, native steering or lab
            API access.
          </p>
          <p>
            Use the VM’s own URLs for live experiments; Pages does not proxy
            private HTTP services.
          </p>
          <a className="quiet-button" href="../viewer/">
            Open the room sandbox <ArrowUpRight size={16} />
          </a>
          <a
            className="detail-source"
            href={source('reference/radio/rf-property-coverage.md')}
            target="_blank"
            rel="noreferrer"
          >
            Pinned RF evidence <ArrowUpRight size={16} />
          </a>
        </article>
      </div>
    </section>
  );
}
