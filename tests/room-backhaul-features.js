'use strict';

const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const {execFile} = require('child_process');
const {promisify} = require('util');
const {kernelClientAudit} = require('./room-feature-acceptance.js');
const execute = promisify(execFile);
const rooms = ['backhaul-branch-formation', 'backhaul-parent-handover', 'backhaul-isolation-recovery'];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function stackProfile(flavor) {
  assert.ok(['rdk', 'prpl'].includes(flavor), 'Unknown stack');
  return flavor === 'rdk' ?
    {containers: {gateway: 'bpibroadband', extender_1: 'bpiap', extender_2: 'bpiap-001', extender_3: 'bpiap-002', extender_4: 'bpiap-003'},
      ap: 'wifi1.1', station: 'wifi1.3', bridge: 'brlan0', gateway: '10.0.0.1', healthNodes: 6} :
    {containers: {gateway: 'prpl-controller', extender_1: 'prpl-agent-01', extender_2: 'prpl-agent-02', extender_3: 'prpl-agent-03', extender_4: 'prpl-agent-04'},
      ap: 'wlan2.1', station: 'wlan3', bridge: 'br-lan', gateway: '192.168.77.1', healthNodes: 5};
}

function ready(entry, healthNodes, clients = 10) {
  return Object.keys(entry.native.nodes).length === 5 && Object.keys(entry.native.parents).length === 4 &&
    Object.values(entry.native.parents).every(Boolean) &&
    Object.values(entry.native.nodes).every(node => node.pingOk && node.fronthaulAps === 6 && node.apOperating) &&
    entry.health?.healthy && entry.health.topology_nodes === healthNodes && entry.health.api_active === clients &&
    entry.optimizer?.fleet?.converged === true && entry.topology.nodes.length === 6 &&
    new Set(entry.topology.stations.map(station => station.mac)).size === clients;
}

function interfaceState(raw) {
  const apInfo = raw.split(/Connected to|Not connected/)[0];
  return {apBssid: apInfo.match(/\baddr ([0-9a-f:]{17})/i)?.[1]?.toLowerCase(),
    apOperating: /\bssid mesh_backhaul\b/.test(apInfo) && /\bchannel 36 \(5180 MHz\)/.test(apInfo),
    fronthaulAps: Number(raw.match(/FRONTHAUL_APS=(\d+)/)?.[1] ?? NaN),
    parentBssid: raw.match(/Connected to ([0-9a-f:]{17})/i)?.[1]?.toLowerCase() || null,
    pingOk: /PROBE_EXIT=0\b/.test(raw)};
}

function summarizeNative(samples, room) {
  const parents = samples.map(sample => sample.native?.parents || {});
  const isolated = samples.some(sample => sample.native?.parents.extender_4 === null && sample.native?.nodes.extender_4?.pingOk === false);
  return room === 'backhaul-branch-formation'
    ? {branchObserved: parents.some(value => value.extender_3 === 'extender_1' && value.extender_4 === 'extender_2')}
    : room === 'backhaul-parent-handover'
      ? {lowerRelayObserved: parents.some(value => value.extender_3 === 'extender_2')}
      : {upstreamOutageObserved: isolated};
}

async function run(options) {
  for (const key of ['host', 'vm']) assert.match(options[key], /^[a-zA-Z0-9_.-]+$/);
  assert.equal(options['yes-act'], 'true', 'Explicit --yes-act true is required; these rooms change live RF and can interrupt service');
  const selectedRooms = options.room ? [options.room] : rooms;
  const flavor = options.flavor || 'rdk';
  const profile = stackProfile(flavor);
  const containers = profile.containers;
  assert.ok(selectedRooms.every(id => rooms.includes(id)), 'Unknown geometry room');
  const directory = path.resolve(options.output);
  assert.ok(!fs.existsSync(directory), 'Use a new output directory');
  fs.mkdirSync(directory, {recursive: true});
  const save = (name, value) => fs.writeFileSync(path.join(directory, name), JSON.stringify(value, null, 2) + '\n');
  const report = {flavor, started: new Date().toISOString(), scope: 'Geometry-room playback, native parent/traffic convergence and restoration; bounded, not a soak',
    rooms: [], errors: [], featureChecksPassed: false, recoveryPassed: false};
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
  const environment = {...process.env};
  delete environment.DISPLAY;
  const renderer = options.renderer || 'swiftshader';
  assert.ok(['swiftshader', 'vulkan'].includes(renderer));
  const browser = await chromium.launch({headless: true, env: environment, executablePath: process.env.CHROMIUM_PATH,
    args: ['--no-sandbox', '--ozone-platform=headless', '--use-gl=angle',
      ...(renderer === 'vulkan' ? ['--use-angle=vulkan', '--disable-software-rasterizer'] :
        ['--enable-unsafe-swiftshader', '--use-angle=swiftshader']),
      '--disable-background-timer-throttling', '--disable-renderer-backgrounding']});
  const context = await browser.newContext({viewport: {width: 1280, height: 900}});
  context.setDefaultTimeout(45000);
  const roomPage = await context.newPage();
  const topologyPage = await context.newPage();
  const base = options['room-url'].replace(/\/$/, '');
  let leaseToken = null;
  let changed = false;
  let baseline = null;
  let currentRoom = null;
  let bindings = {};
  const request = async endpoint => {
    const response = await context.request.get(base + endpoint, {timeout: 15000});
    if (!response.ok()) throw new Error(endpoint + ': HTTP ' + response.status());
    return response.json();
  };
  roomPage.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/api/demo/world/apply')) {
      leaseToken = request.postDataJSON()?.token || leaseToken;
    }
  });
  for (const page of [roomPage, topologyPage]) page.on('pageerror', error => report.errors.push(error.message));

  async function identity() {
    const result = await execute('ssh', [options.host, 'lxc exec ' + options.vm +
      ' -- python3 /tmp/room-feature-guest-audit.py identity ' + flavor], {timeout: 45000, maxBuffer: 1048576});
    return JSON.parse(result.stdout);
  }

  async function native() {
    if (flavor === 'prpl') {
      const result = await execute('ssh', [options.host, 'lxc exec ' + options.vm +
        ' -- python3 /tmp/backhaul-native-probe.py'], {timeout: 25000, maxBuffer: 1048576});
      const nodes = Object.fromEntries(Object.entries(JSON.parse(result.stdout)).map(([role, value]) =>
        [role, {...value, ...interfaceState(value.raw)}]));
      const owners = Object.fromEntries(Object.entries(nodes).map(([role, value]) => [value.apBssid, role]));
      return {nodes, parents: Object.fromEntries(Object.entries(nodes).filter(([role]) => role !== 'gateway')
        .map(([role, value]) => [role, owners[value.parentBssid] || null]))};
    }
    const readings = await Promise.all(Object.entries(containers).map(async ([role, container]) => {
      const script = 'iw dev wifi1.1 info; iw dev wifi1.3 link 2>/dev/null; ping -I brlan0 -q -c 1 -W 1 10.0.0.1 >/dev/null 2>&1; printf "\\nPROBE_EXIT=%s\\n" "$?"; printf "FRONTHAUL_APS=%s\\n" "$(iw dev | grep -Ec \"ssid (private_ssid|iot_ssid)$\")"';
      try {
        const result = await execute('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', options.host,
          'lxc exec ' + options.vm + ' -- lxc exec ' + container + " -- sh -c '" + script.replace('wifi1.1', profile.ap).replace('wifi1.3', profile.station).replace('brlan0', profile.bridge).replace('10.0.0.1', profile.gateway) + "'"],
        {timeout: 12000, maxBuffer: 65536});
        return [role, {...interfaceState(result.stdout), raw: result.stdout}];
      } catch (error) { return [role, {error: error.message, pingOk: null}]; }
    }));
    const nodes = Object.fromEntries(readings);
    const owners = Object.fromEntries(readings.filter(([, value]) => value.apBssid).map(([role, value]) => [value.apBssid, role]));
    return {nodes, parents: Object.fromEntries(readings.filter(([role]) => role !== 'gateway')
      .map(([role, value]) => [role, owners[value.parentBssid] || null]))};
  }

  async function auditClients(observation) {
    const mapping = Object.fromEntries(Object.entries(bindings).map(([role, client]) => [role, client.container]));
    assert.ok(Object.values(mapping).every(value => /^(?:prpl-client-[0-9]{2,3}|wlan-client(?:-[0-9]{3})?)$/.test(value)));
    const wanted = Object.entries(observation.interactions.roles)
      .filter(([role, value]) => value.present && bindings[role]).map(([role]) => bindings[role].sta_mac);
    const model = observation.clients.map(client => ({mac: client.sta_mac, bssid: client.connected_bssid}));
    const response = await execute('ssh', [options.host, 'lxc exec ' + options.vm +
      " -- python3 /tmp/room-feature-guest-audit.py links '" + JSON.stringify(mapping) + "'"],
      {timeout: 45000, maxBuffer: 1048576});
    const result = kernelClientAudit(bindings, wanted, model, JSON.parse(response.stdout));
    assert.equal(result.passed, true, JSON.stringify(result.errors));
    return result;
  }

  async function sample(label, includeNative = false) {
    const [state, interactions, topology, visible] = await Promise.all([
      request('/api/demo/current'), request('/api/demo/interactions'),
      topologyPage.evaluate(() => {
        const instance = window.EasyMeshController;
        return {nodes: (instance?.topology?.nodes || []).map(node => ({id: node.id, name: node.name})),
          edges: (instance?.topology?.edges || []).map(edge => ({from: String(edge.from), to: String(edge.to)})),
          stations: [...document.querySelectorAll('#topology-visualization .sta-node')].map(element => ({
            mac: element.__data__?.sta?.staMAC, bssid: element.__data__?.sta?.bssid}))};
      }),
      roomPage.evaluate(() => ({policy: document.getElementById('backhaulPolicyTitle').textContent,
        clock: document.getElementById('tnow').textContent, meta: document.getElementById('worldmeta').textContent,
        optimizer: document.getElementById('optimizerStatus').textContent})),
    ]);
    const result = {at: new Date().toISOString(), label, interactions, visible, topology,
      health: state.health, mesh: state.network?.mesh, clients: state.network?.clients, optimizer: state.optimizer,
      native: includeNative ? await native() : undefined};
    if (currentRoom) currentRoom.samples.push(result);
    return result;
  }

  async function load(id) {
    await roomPage.bringToFront();
    if (await roomPage.evaluate(() => Boolean(document.fullscreenElement))) await roomPage.locator('#roomFullscreen').click();
    changed = true;
    const [response] = await Promise.all([
      roomPage.waitForResponse(response => response.url().endsWith('/api/demo/world/apply') && response.request().method() === 'POST', {timeout: 60000}),
      id === 'default' ? roomPage.locator('#defaultWorld').click() : roomPage.locator('#world').selectOption(id),
    ]);
    const result = await response.json();
    assert.ok(response.ok(), JSON.stringify(result));
    assert.equal(result.backhaul_rf_verified, true);
    await roomPage.waitForFunction(() => !document.getElementById('world').disabled, null, {timeout: 60000});
    await roomPage.locator('#roomFullscreen').click();
    return result;
  }

  async function playTo(time) {
    await roomPage.bringToFront();
    const button = await roomPage.evaluate(() => document.fullscreenElement ? '#fullscreenPlay' : '#play');
    await roomPage.locator(button).click();
    const deadline = Date.now() + 35000;
    while (Date.now() < deadline) {
      const state = await request('/api/demo/interactions');
      if (state.playback.time_ms === time && state.playback.status !== 'playing') return state;
      assert.ok(!state.fault, 'Room fault: ' + state.fault);
      await delay(500);
    }
    throw new Error('Playback did not reach ' + time + ' within the short-test deadline');
  }

  try {
    report.before = await identity();
    report.renderer = {requested: renderer, actual: await roomPage.evaluate(() => {
      const context = document.createElement('canvas').getContext('webgl');
      const extension = context?.getExtension('WEBGL_debug_renderer_info');
      return extension ? context.getParameter(extension.UNMASKED_RENDERER_WEBGL) : null;
    })};
    assert.ok(report.renderer.actual && (renderer !== 'vulkan' || !/swiftshader|llvmpipe|software/i.test(report.renderer.actual)));
    const before = await request('/api/demo/current');
    baseline = await request('/api/demo/interactions');
    assert.equal(before.health.healthy, true, 'Start with a healthy default lab');
    assert.equal(before.health.api_active, 20);
    assert.equal(baseline.backhaul_policy, 'fixed-startup-mesh');
    assert.equal(baseline.lease.held, false, 'Do not take another operator’s lease');
    save('baseline.json', {health: before.health, mesh: before.network.mesh, backhaul: baseline.backhaul_links, daemon: baseline.daemon});
    const catalog = await request('/api/demo/worlds');
    bindings = catalog.client_bindings;
    assert.equal(Object.keys(bindings).length, 100);
    for (const id of rooms) assert.equal(catalog.worlds.find(entry => entry.id === id)?.backhaul_rf, 'geometry');
    await roomPage.goto(base + '/');
    await roomPage.waitForFunction(() => window.__viewer && !document.getElementById('world').disabled, null, {timeout: 60000});
    await topologyPage.goto(options['topology-url']);
    await topologyPage.locator('[data-tab="topology"]').click();
    await topologyPage.waitForSelector('.sta-node', {timeout: 30000});
    await topologyPage.locator('#topologyFullscreen').click();
    await roomPage.bringToFront();
    await roomPage.locator('#roomFullscreen').click();
    for (const id of selectedRooms) {
      currentRoom = {id, samples: []};
      report.rooms.push(currentRoom);
      console.log(id + ': loading geometry RF');
      currentRoom.load = await load(id);
      let loaded = await sample('loaded', true);
      {
        const deadline = Date.now() + 60000;
        while (!ready(loaded, profile.healthNodes) && Date.now() < deadline) {
          await delay(1000);
          loaded = await sample('initial-client-convergence', true);
        }
        assert.equal(ready(loaded, profile.healthNodes), true,
          'The loaded ten-client room must converge before testing its movement');
        currentRoom.initialConvergenceVerified = true;
        currentRoom.initialKernel = await auditClients(loaded);
      }
      if (id === 'backhaul-isolation-recovery') {
        const deadline = Date.now() + 15000;
        while (loaded.native.nodes.extender_4.pingOk !== true && Date.now() < deadline) {
          await delay(1000);
          loaded = await sample('initial-reachability', true);
        }
        assert.equal(loaded.native.nodes.extender_4.pingOk, true, 'Isolation requires a verified working upstream link before movement');
        currentRoom.initialUpstreamVerified = true;
      }
      assert.ok(Object.values(loaded.native.nodes).every(node => !node.error), 'Missing out-of-band native observations');
      assert.ok(Object.values(loaded.native.nodes).every(node => node.apOperating && node.fronthaulAps === 6),
        'Geometry rooms require operating backhaul and client-facing APs, not only configured BSS records');
      assert.equal(loaded.interactions.backhaul_policy, 'modeled');
      assert.equal(loaded.interactions.backhaul_authority, 'native');
      assert.equal(loaded.interactions.expected_online_clients, 10);
      assert.match(loaded.visible.policy, /Geometry-driven backhaul · native parent selection/);
      assert.equal(loaded.interactions.daemon.instance_id, baseline.daemon.instance_id);
      currentRoom.midpoint = await playTo(12000);
      assert.notDeepEqual(currentRoom.midpoint.backhaul_links, loaded.interactions.backhaul_links);
      for (let index = 0; index < 3; index++) {
        const observation = await sample('midpoint-' + index, true);
        assert.ok(Object.values(observation.native.nodes).every(node => !node.error), 'Missing native midpoint observations');
        if (index < 2) await delay(1500);
      }
      if (id === 'backhaul-isolation-recovery') {
        const links = currentRoom.midpoint.backhaul_links.filter(link => [link.source_role, link.destination_role].includes('extender_4'));
        assert.ok(links.length > 0 && links.every(link => link.snr_db === -20), 'Isolation must affect real mesh RF');
        assert.equal(currentRoom.midpoint.roles.extender_4.present, true, 'This must not be a fronthaul-disable shortcut');
      }
      currentRoom.nativeOutcome = summarizeNative(currentRoom.samples.filter(entry => entry.label.startsWith('midpoint')), id);
      if (id === 'backhaul-branch-formation') {
        const deadline = Date.now() + 60000;
        let observation = currentRoom.samples.at(-1);
        const converged = entry => summarizeNative([entry], id).branchObserved && ready(entry, profile.healthNodes) &&
          entry.mesh?.backhaul_edges?.some(edge => edge.child_role === 'extender_3' && edge.parent_role === 'extender_1') &&
          entry.mesh?.backhaul_edges?.some(edge => edge.child_role === 'extender_4' && edge.parent_role === 'extender_2');
        while (!converged(observation) && Date.now() < deadline) {
          await delay(1000);
          observation = await sample('midpoint-branch-convergence', true);
        }
        currentRoom.nativeOutcome = {...summarizeNative([observation], id), convergenceVerified: converged(observation)};
        assert.equal(currentRoom.nativeOutcome.convergenceVerified, true,
          'Branch must recover native uplinks, traffic, both topology views and all ten client decisions');
      }
      if (id !== 'backhaul-branch-formation') {
        const deadline = Date.now() + 60000;
        let observation = currentRoom.samples.at(-1);
        const verified = entry => id === 'backhaul-parent-handover' ?
          summarizeNative([entry], id).lowerRelayObserved && ready(entry, profile.healthNodes) &&
            entry.mesh?.backhaul_edges?.some(edge => edge.child_role === 'extender_3' && edge.parent_role === 'extender_2') :
          summarizeNative([entry], id).upstreamOutageObserved && entry.native.nodes.extender_4.apOperating &&
            entry.native.nodes.extender_4.fronthaulAps === 6;
        while (!verified(observation) && Date.now() < deadline) {
          await delay(1000);
          observation = await sample('midpoint-native-convergence', true);
        }
        currentRoom.nativeOutcome = {...summarizeNative([observation], id), convergenceVerified: verified(observation)};
        assert.equal(currentRoom.nativeOutcome.convergenceVerified, true, 'Native handover/isolation was not verified');
      }
      currentRoom.relayApOperating = Object.fromEntries(Object.entries(currentRoom.samples.at(-1).native.nodes)
        .filter(([role]) => role !== 'gateway').map(([role, value]) => [role, value.apOperating]));
      await roomPage.bringToFront();
      await roomPage.screenshot({path: path.join(directory, id + '-room.png')});
      await topologyPage.bringToFront();
      await topologyPage.screenshot({path: path.join(directory, id + '-topology.png')});
      currentRoom.finish = await playTo(24000);
      assert.deepEqual(currentRoom.finish.backhaul_links, loaded.interactions.backhaul_links);
      currentRoom.returnObservation = await sample('returned', true);
      {
        const deadline = Date.now() + 60000;
        while (!ready(currentRoom.returnObservation, profile.healthNodes) && Date.now() < deadline) {
          await delay(1000);
          currentRoom.returnObservation = await sample('return-recovery', true);
        }
        currentRoom.nativeOutcome.returnRecoveryObserved = ready(currentRoom.returnObservation, profile.healthNodes);
        assert.equal(currentRoom.nativeOutcome.returnRecoveryObserved, true, 'Ten-client native recovery must converge after return');
        currentRoom.returnKernel = await auditClients(currentRoom.returnObservation);
      }
      currentRoom.featureChecksPassed = true;
      save(id + '.json', currentRoom);
      console.log(JSON.stringify({room: id, featureChecksPassed: true, native: currentRoom.nativeOutcome}));
    }
    report.featureChecksPassed = report.rooms.every(entry => entry.featureChecksPassed) && report.errors.length === 0;
  } catch (error) {
    report.failure = error.stack;
    console.error(error.message);
  } finally {
    if (changed && baseline) {
      try {
        console.log('Restoring default RF and checking native recovery (at most 60 s)');
        await load('default');
        currentRoom = null;
        const restored = await request('/api/demo/interactions');
        assert.equal(restored.backhaul_policy, 'fixed-startup-mesh');
        assert.deepEqual(restored.backhaul_links, baseline.backhaul_links);
        const deadline = Date.now() + 60000;
        while (Date.now() < deadline) {
          const recovery = await sample('default-recovery', true);
          report.recovery = recovery;
          if (ready(recovery, profile.healthNodes, 20)) {
            report.recoveryPassed = true;
            break;
          }
          await delay(1500);
        }
        if (!report.recoveryPassed) report.recoveryFailure = 'Fixed RF restored, but native recovery not verified within 60 seconds; no forced parent changes or native restarts attempted';
      } catch (error) { report.recoveryFailure = error.stack; }
    }
    if (leaseToken) {
      try { await context.request.delete(base + '/api/demo/interactions/lease', {data: {token: leaseToken, command_id: 'backhaul-short-release-' + Date.now()}}); }
      catch (error) { report.errors.push('Lease release: ' + error.message); }
    }
    report.finished = new Date().toISOString();
    try {
      report.after = await identity();
      assert.deepEqual(report.after, report.before, 'Native process identities changed');
      report.nativeIdentitiesUnchanged = true;
    } catch (error) { report.errors.push(error.message); report.nativeIdentitiesUnchanged = false; }
    report.featureChecksPassed = report.featureChecksPassed && report.errors.length === 0;
    save('report.json', report);
    await browser.close();
  }
  return report;
}

module.exports = {summarizeNative, interfaceState, stackProfile, ready};
if (require.main === module) {
  const options = {};
  for (let index = 2; index < process.argv.length; index += 2) options[process.argv[index].replace(/^--/, '')] = process.argv[index + 1];
  run(options).then(report => {
    console.log(JSON.stringify({featureChecksPassed: report.featureChecksPassed, recoveryPassed: report.recoveryPassed, output: options.output}));
    process.exitCode = report.featureChecksPassed && report.recoveryPassed ? 0 : 1;
  }).catch(error => { console.error(error); process.exitCode = 2; });
}
