import { useRef, useState } from 'react';
import {
  Network,
  Router,
  Radio,
  Laptop,
  Globe,
  Cpu,
  FlaskConical,
  ChevronRight,
  ArrowUpRight,
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { entries, revision, source } from './system';
import { Topology, ProtocolPaths, CurrentState, type Inspect } from './views';

const groups = [
  { id: 'wan', where: 'wan', icon: Globe, children: ['bridge', 'wan'] },
  {
    id: 'optimizer',
    where: 'tooling',
    icon: FlaskConical,
    children: [
      'optimizer',
      'steer',
      'configurator',
      'console',
      'room',
      'tests',
    ],
  },
  {
    id: 'gateway',
    where: 'gateway',
    icon: Router,
    children: [
      'cli',
      'controller',
      'database',
      'agent',
      'ieee1905',
      'hostapd',
      'hal',
      'radios',
    ],
  },
  {
    id: 'extender',
    where: 'extenders',
    icon: Radio,
    children: ['agent', 'fronthaul', 'backhaul'],
  },
  {
    id: 'client',
    where: 'clients',
    icon: Laptop,
    children: ['supplicant', '11v', 'band', 'dhcpclient'],
  },
  { id: 'medium', where: 'medium', icon: Cpu, children: ['hwsim', 'wmediumd'] },
];

export default function Explorer() {
  const [selected, setSelected] = useState<string | null>(null);
  const [extra, setExtra] = useState<{
    title: string;
    properties: [string, string][];
  }>();
  const [view, setView] = useState('architecture');
  const inspect: Inspect = (identifier, context) => {
    setSelected(identifier);
    setExtra(context);
  };
  const base = selected ? entries[selected] : null;
  const item =
    base && extra
      ? {
          ...base,
          title: extra.title,
          properties: [...extra.properties, ...base.properties],
        }
      : base;
  // While the drawer animates closed, keep showing what it showed: clearing its
  // content and colour mid-exit starts new transitions and can leave it stuck
  // half-closed over the page.
  const shownRef = useRef(item);
  if (item) shownRef.current = item;
  const shown = item ?? shownRef.current;
  return (
    <main>
      <header className="masthead">
        <div className="brand">
          <span className="brand-icon">
            <Network />
          </span>
          <strong>
            prplMesh <span>LAB</span>
          </strong>
          <span className="divider" />
          <span className="app-name">System explorer</span>
        </div>
        <a
          className="source-link"
          href={source('docs/README.md')}
          target="_blank"
          rel="noreferrer"
        >
          Source guide <ArrowUpRight size={16} />
        </a>
      </header>
      <section className="page-intro">
        <div>
          <div className="eyebrow">REAL SOFTWARE. SIMULATED RADIO.</div>
          <h1>Inside the prplMesh lab</h1>
          <p>
            Explore the architecture, follow a packet, understand the evidence.
          </p>
        </div>
        <div className="version">
          <span className="version-dot" />
          <span>Pinned documentation</span>
          <span className="branch">
            {revision.slice(0, 7)} · not live telemetry
          </span>
        </div>
      </section>
      <Tabs
        className="workspace"
        value={view}
        onValueChange={(value) => setView(String(value))}
      >
        <div className="toolbar">
          <TabsList className="view-tabs">
            <TabsTrigger value="architecture">Architecture</TabsTrigger>
            <TabsTrigger value="topology">Network topology</TabsTrigger>
            <TabsTrigger value="flows">Protocol paths</TabsTrigger>
            <TabsTrigger value="state">Evidence & limits</TabsTrigger>
          </TabsList>
          <span className="offline-label">DISCONNECTED EXPLORER</span>
        </div>
        <TabsContent value="architecture">
          <div className="map-toolbar">
            <div className="legend">
              <span className="blue">Native control</span>
              <span className="cyan">Mesh agents</span>
              <span className="pink">Clients</span>
              <span className="purple">RF plane</span>
              <span className="green">Experiment tooling</span>
            </div>
            <span className="map-hint">Click any component</span>
          </div>
          <div className="map-scroll">
            <div className="system-map">
              <svg className="wiring" viewBox="0 0 1200 915" aria-hidden="true">
                <path className="amber" d="M264 125H326" />
                <path className="blue wireless" d="M746 180H822" />
                <path className="cyan wireless" d="M992 320V362" />
                <path className="purple" d="M536 634V664" />
                <path className="purple" d="M1162 170H1184V790H746" />
                <path className="purple" d="M1162 545H1184" />
                <path className="green" d="M264 425H296V260H326" />
              </svg>
              {groups.map((group) => {
                const component = entries[group.id];
                const Icon = group.icon;
                return (
                  <article
                    key={group.id}
                    className={`system-card ${component.color} ${group.where}`}
                  >
                    <button
                      className="card-heading"
                      onClick={() => inspect(group.id)}
                    >
                      <Icon />
                      <div>
                        <span className="overline">{component.kind}</span>
                        <h2>{component.title}</h2>
                      </div>
                      <ArrowUpRight size={17} />
                    </button>
                    <div className="card-body">
                      {group.children.map((identifier) => (
                        <button
                          key={identifier}
                          className="inner-block"
                          onClick={() => inspect(identifier)}
                        >
                          <span>{entries[identifier].title}</span>
                          <small>{entries[identifier].kind}</small>
                          <ChevronRight size={14} />
                        </button>
                      ))}
                    </div>
                  </article>
                );
              })}
              <div className="map-note">
                <span className="line-key" /> Control / wired{' '}
                <span className="line-key dashed" /> Wireless{' '}
                <span className="note-spacer" /> Diagram only · no live API
              </div>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="topology">
          <Topology inspect={inspect} />
        </TabsContent>
        <TabsContent value="flows">
          <ProtocolPaths inspect={inspect} />
        </TabsContent>
        <TabsContent value="state">
          <CurrentState inspect={inspect} />
        </TabsContent>
      </Tabs>
      <footer>
        <span>
          Real Wi-Fi & EasyMesh protocols. Simulated radios & propagation.
        </span>
        <a
          href={source('reference/radio/rf-property-coverage.md')}
          target="_blank"
          rel="noreferrer"
        >
          RF qualification boundaries <ArrowUpRight size={13} />
        </a>
      </footer>
      <Sheet
        open={Boolean(item)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className={`detail-sheet ${shown?.color || 'blue'}`}>
          <SheetHeader>
            <span className="eyebrow">COMPONENT INSPECTOR</span>
            <SheetTitle>{shown?.title}</SheetTitle>
            <SheetDescription>{shown?.summary}</SheetDescription>
          </SheetHeader>
          {shown && (
            <div className="detail-body">
              <div className="detail-tag">{shown.kind}</div>
              <h3>Inside this block</h3>
              <p>{shown.description}</p>
              <dl>
                {shown.properties.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              {shown.note && <div className="detail-note">{shown.note}</div>}
              {selected === 'cli' && (
                <button
                  className="action-button"
                  onClick={() => {
                    setSelected(null);
                    setView('topology');
                  }}
                >
                  Explore network topology <Network size={16} />
                </button>
              )}
              <h3>Connected components</h3>
              <div className="related">
                {shown.related.map((identifier) => (
                  <button key={identifier} onClick={() => inspect(identifier)}>
                    {entries[identifier].title}
                    <ChevronRight size={15} />
                  </button>
                ))}
              </div>
              <h3>Source references</h3>
              {shown.sources.map((path) => (
                <a
                  className="detail-source"
                  key={path}
                  href={source(path)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {path}
                  <ArrowUpRight size={15} />
                </a>
              ))}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </main>
  );
}
