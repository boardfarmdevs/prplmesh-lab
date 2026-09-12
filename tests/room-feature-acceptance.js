'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {performance} = require('node:perf_hooks');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const execFileAsync = promisify(execFile);
const {startHostMonitor} = require('./room-host-monitor.js');
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const lower = value => String(value || '').toLowerCase();
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const quote = value => "'" + String(value).replaceAll("'", "'\\''") + "'";

function expectedFrame(world, timeMs) {
  const frame = world.generations.findLast(item => item.time_ms <= timeMs) || world.generations[0];
  const next = world.generations.find(item => item.time_ms > timeMs);
  const fraction = next ? (timeMs - frame.time_ms) / (next.time_ms - frame.time_ms) : 0;
  return Object.fromEntries(Object.keys(world.roles).map(role => [role, {
    present: frame.present[role],
    position: next && frame.present[role] && next.present[role]
      ? frame.positions[role].map((value, axis) => value + fraction * (next.positions[role][axis] - value))
      : frame.positions[role],
  }]));
}

function mapping(rows) {
  return rows.map(item => [lower(item.mac), lower(item.bssid), String(item.ssid || '')]).sort((left, right) => left[0].localeCompare(right[0]));
}

function evaluate(current, interactions, view, world, bindings, now = Date.now()) {
  const expected = expectedFrame(world, interactions.playback.time_ms);
  const wanted = Object.entries(bindings).filter(([role]) => expected[role]?.present).map(([, client]) => lower(client.sta_mac)).sort();
  const clients = current.network?.clients || [];
  const actual = view.stations.map(item => lower(item.mac)).sort();
  const duplicates = actual.length !== new Set(actual).size;
  const roster = !duplicates && same(actual, wanted);
  const roomRows = clients.map(client => ({mac: client.sta_mac, bssid: client.connected_bssid, ssid: client.ssid}));
  const viewMatchesRoom = same(mapping(view.stations), mapping(roomRows));
  const viewMatchesModel = same(mapping(view.stations), mapping(view.modelStations));
  const scriptErrors = Object.entries(expected).filter(([role, value]) => {
    const actualRole = interactions.roles[role];
    return !actualRole || actualRole.present !== value.present || value.position.some((coordinate, axis) => Math.abs(coordinate - actualRole.position[axis]) > 0.15);
  }).map(([role]) => role);
  const optimizer = current.optimizer || {};
  const fleet = optimizer.fleet || {};
  const decisions = optimizer.client_decisions || [];
  const currentByMac = new Map(clients.map(client => [lower(client.sta_mac), client]));
  const decisionCoverage = same(decisions.map(row => lower(row.sta_mac)).sort(), wanted) && decisions.every(row =>
    Number.isFinite(row.current_rcpi) && lower(row.source_bssid) === lower(currentByMac.get(lower(row.sta_mac))?.connected_bssid));
  const sameBandBest = decisionCoverage && decisions.every(row =>
    (row.scores || []).every(score => score.band !== row.current_band || score.gain_rcpi <= 0));
  const strongerClientGaps = decisions.flatMap(row => {
    const stronger = (row.scores || []).filter(score => score.band === row.current_band && score.gain_rcpi > 0);
    return stronger.length ? [{sta_mac: row.sta_mac, reason: row.reason, phase: row.phase,
      maximum_gain_rcpi: Math.max(...stronger.map(score => score.gain_rcpi))}] : [];
  });
  const evaluationAge = (now - Date.parse(optimizer.evaluated_at)) / 1000;
  const metricsFresh = clients.length === wanted.length && clients.every(client => {
    const age = (now - Date.parse(client.metric_observed_at)) / 1000;
    return Number.isFinite(client.rcpi) && client.rcpi > 0 && age >= -2 && age <= 30;
  });
  const parents = Object.fromEntries((current.network?.mesh?.backhaul_edges || []).map(edge => [edge.child_role, edge.parent_role]));
  const meshConnected = Object.keys(parents).length === 4 && Object.keys(parents).every(role => {
    const visited = new Set();
    while (role !== 'gateway') {
      if (!parents[role] || visited.has(role)) return false;
      visited.add(role); role = parents[role];
    }
    return true;
  });
  const meshNodes = new Map((current.network?.mesh?.nodes || []).map(node => [node.role, String(node.device_id)]));
  const meshViewMatches = Object.entries(parents).every(([child, parent]) => view.edges.some(edge =>
    edge.to === meshNodes.get(child) && edge.from === meshNodes.get(parent)));
  const healthy = current.health?.healthy === true && current.health.expected_online_clients === wanted.length;
  const epochMatches = optimizer.environment_epoch === current.environment_epoch && current.environment_epoch === interactions.environment_epoch;
  const complete = fleet.measurement_complete === true && fleet.clients_checked === wanted.length && fleet.clients_evaluated === wanted.length;
  const mediumFault = interactions.fault || current.error || null;
  const qualified = roster && viewMatchesRoom && viewMatchesModel && view.meshCount === 6 && meshConnected && meshViewMatches &&
    healthy && epochMatches && metricsFresh && complete && decisionCoverage &&
    evaluationAge >= -2 && evaluationAge <= 30 && scriptErrors.length === 0 && !mediumFault;
  const policyConverged = qualified && fleet.converged === true;
  const strongestApConverged = qualified && sameBandBest && fleet.clients_with_stronger_ap === 0;
  const converged = policyConverged;
  return {converged, roster, viewMatchesRoom, viewMatchesModel, duplicates, scriptErrors, healthy, epochMatches,
    complete, sameBandBest, metricsFresh, evaluationAge, meshConnected, meshViewMatches, meshCount: view.meshCount,
    expectedClients: wanted.length, actualClients: actual.length, candidates: fleet.candidate_measurements,
    strongerClients: fleet.clients_with_stronger_ap, policyConverged, strongestApConverged,
    optimizerPolicySatisfied: fleet.converged === true, decisionCoverage, strongerClientGaps,
    convergenceCriterion: 'configured-steering-policy',
    parents, wanted, actual, actions: optimizer.actions_used, actionLimit: optimizer.maximum_actions,
    decision: optimizer.decision?.reason, unavailable: optimizer.unavailable_cohort_reason || null,
    mediumFault};
}

function distribution(values) {
  const ordered = values.filter(Number.isFinite).sort((left, right) => left - right);
  const percentile = fraction => ordered.length ? ordered[Math.max(0, Math.ceil(ordered.length * fraction) - 1)] : null;
  return {count: ordered.length, p50: percentile(0.5), p95: percentile(0.95), max: ordered.at(-1) ?? null};
}

function recordedEventKind(kind) {
  return /^(optimizer\.(action|verification(?:\.discarded)?|collection)|rf\.generation\.applied|playback\.rf\.applied|interaction\.playback\.(paused|completed)|worker\.error|room\.world\.committed)$/.test(kind);
}

function eventPerformance(records) {
  const payloads = kind => records.filter(record => record.event.kind === kind).map(record => record.event.payload);
  const verifications = payloads('optimizer.verification');
  const discarded = payloads('optimizer.verification.discarded');
  const submitted = payloads('optimizer.action').filter(payload => payload.phase === 'submitted');
  const completedActions = new Set([...verifications, ...discarded].map(payload => payload.action_id).filter(Boolean));
  const collections = payloads('optimizer.collection');
  const completed = collections.filter(payload => payload.phase === 'completed');
  const transactions = completed.flatMap(payload => payload.transactions || []);
  const operations = [...new Set(transactions.map(transaction => transaction.operation || 'candidate_query'))];
  const pending = new Map();
  const requestToVerification = [];
  const submission = [];
  for (const {event} of records) {
    const payload = event.payload;
    const key = payload.action_id || lower(payload.subject_mac || payload.decision?.sta_mac) + '/' + lower(payload.target_bssid || payload.decision?.target_bssid);
    const timestamp = Date.parse(event.recorded_at);
    if (event.kind === 'optimizer.action' && payload.phase === 'requested') pending.set(key, timestamp);
    if (event.kind === 'optimizer.action' && payload.phase === 'submitted' && pending.has(key)) submission.push((timestamp - pending.get(key)) / 1000);
    if (event.kind === 'optimizer.verification' && pending.has(key)) {
      if (payload.success) requestToVerification.push((timestamp - pending.get(key)) / 1000);
      pending.delete(key);
    }
  }
  return {
    verifiedActions: verifications.filter(payload => payload.success).length,
    failedVerifications: verifications.filter(payload => !payload.success).length,
    submittedActions: submitted.length,
    discardedVerifications: discarded.length,
    unmatchedSubmittedActions: submitted.filter(payload => !payload.action_id || !completedActions.has(payload.action_id)).length,
    verificationSeconds: distribution(verifications.filter(payload => payload.success).map(payload => payload.elapsed_seconds)),
    requestToVerificationSeconds: distribution(requestToVerification),
    submissionSeconds: distribution(submission),
    rfApplyMs: distribution(payloads('playback.rf.applied').map(payload => payload.elapsed_ms)),
    candidateTransactionMs: distribution(completed.flatMap(payload => (payload.transactions || []).map(transaction => transaction.elapsed_ms))),
    candidatePublicationWaitMs: distribution(collections.filter(payload => payload.phase === 'published').map(payload => payload.publication_wait_ms)),
    candidateFailures: completed.filter(payload => payload.unavailable).map(payload => payload.unavailable),
    candidateUnavailableCollections: completed.filter(payload => payload.unavailable && payload.unavailable !== 'collection_superseded').length,
    candidateCancelledCollections: completed.filter(payload => payload.unavailable === 'collection_superseded').length,
    collectionOperationMs: Object.fromEntries(operations.map(operation => [operation,
      distribution(transactions.filter(transaction => (transaction.operation || 'candidate_query') === operation).map(transaction => transaction.elapsed_ms))])),
    nativeBusyRejections: transactions.filter(transaction => transaction.error?.includes('Error_Prev_Cmd_In_Progress')).length,
    nativeResponseTimeouts: transactions.filter(transaction => transaction.error?.includes('HTTP 504')).length,
    nativeBusyReadmissions: transactions.filter(transaction => transaction.native_admission_busy).length,
    correlatedVerifications: verifications.filter(payload => payload.action_id && Number.isFinite(payload.request_to_verified_ms)).length,
  };
}

function viewAgreement(samples) {
  const spans = [];
  const bounds = [];
  const intervals = samples.slice(1).map((sample, index) => (sample.monoMs - samples[index].monoMs) / 1000);
  let active = null;
  for (const sample of samples) {
    if (active && sample.monoMs - active.last > 2500) {
      spans.push((active.last - active.first) / 1000);
      active = null;
    }
    if (!sample.viewMatchesRoom || !sample.viewMatchesModel || sample.duplicates) {
      active ||= {first: sample.monoMs, last: sample.monoMs};
      active.last = sample.monoMs;
    } else if (active) {
      spans.push((active.last - active.first) / 1000);
      bounds.push((sample.monoMs - active.first) / 1000);
      active = null;
    }
  }
  if (active) spans.push((active.last - active.first) / 1000);
  return {passed: spans.every(seconds => seconds <= 5), observedBadSpanSeconds: distribution(spans),
    clearanceUpperBoundSeconds: distribution(bounds), samplingIntervalSeconds: distribution(intervals),
    badSamples: samples.filter(sample => !sample.viewMatchesRoom || !sample.viewMatchesModel || sample.duplicates).length};
}

function argumentsFrom(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index++) {
    const key = argv[index].replace(/^--/, '');
    if (key === 'yes-act') args[key] = true;
    else if (key === 'world') (args.world ||= []).push(argv[++index]);
    else args[key] = argv[++index];
  }
  for (const name of ['yes-act', 'flavor', 'host', 'vm', 'room-url', 'topology-url', 'worlds', 'output']) {
    if (!args[name]) throw new Error('Required: --' + name);
  }
  if (!['rdk', 'prpl'].includes(args.flavor)) throw new Error('--flavor must be rdk or prpl');
  return args;
}

async function run(args) {
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const directory = path.resolve(args.output);
  if (fs.existsSync(directory) && fs.readdirSync(directory).length) throw new Error('Use a new, empty output directory to preserve previous evidence');
  fs.mkdirSync(directory, {recursive: true});
  const save = (name, value) => fs.writeFileSync(path.join(directory, name), JSON.stringify(value, null, 2) + '\n');
  const report = {flavor: args.flavor, started: new Date().toISOString(), rooms: [], errors: [], eventGaps: [],
    convergenceCriterion: 'configured-steering-policy', strongestApReportedSeparately: true, temporaryActionLimit: 2000};
  const browserEnvironment = {...process.env};
  delete browserEnvironment.DISPLAY;
  const browser = await chromium.launch({headless: true, env: browserEnvironment, executablePath: process.env.CHROMIUM_PATH,
    args: ['--no-sandbox', '--ozone-platform=headless', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
      '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']});
  const context = await browser.newContext({viewport: {width: 1280, height: 900}});
  const room = await context.newPage();
  const topology = await context.newPage();
  if (args['observer-cpus']) {
    try {
      if (!/^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$/.test(args['observer-cpus'])) throw new Error('Invalid observer CPU list');
      await room.evaluate(() => Boolean(document.createElement('canvas').getContext('webgl')));
      const session = await browser.newBrowserCDPSession();
      const {processInfo} = await session.send('SystemInfo.getProcessInfo');
      const renderers = processInfo.filter(process => process.type.toLowerCase() === 'gpu');
      if (!renderers.length) throw new Error('No owned GPU process found for observer limits');
      for (const renderer of renderers) {
        await execFileAsync('taskset', ['-apc', args['observer-cpus'], String(renderer.id)]);
        await execFileAsync('renice', ['19', '-p', String(renderer.id)]);
      }
      report.observer = {gpuCpus: args['observer-cpus'], processes: renderers.map(process => process.id),
        restrictedBeforeRoomLoad: true};
      await session.detach();
    } catch (error) {
      await browser.close();
      throw error;
    }
  }
  let token;
  let phase = 'preflight';
  let activeRoom = null;
  let eventSequence = 0;
  let stopped = false;
  let eventAbort;
  let hostMonitor;
  const selectedEvents = [];
  const eventOutput = fs.createWriteStream(path.join(directory, 'events.jsonl'), {flags: 'a'});
  for (const page of [room, topology]) page.on('pageerror', error => report.errors.push({room: activeRoom?.id, phase, message: error.message}));
  room.on('response', async response => {
    if (response.url().endsWith('/api/demo/interactions/lease') && response.ok()) {
      const body = await response.json().catch(() => ({}));
      if (body.token) token = body.token;
    }
  });
  async function request(suffix) {
    const response = await fetch(new URL(suffix, args['room-url']), {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error(suffix + ': HTTP ' + response.status);
    return response.json();
  }
  async function guest(operation, payload) {
    const command = 'lxc exec ' + quote(args.vm) + ' -- python3 /tmp/room-feature-guest-audit.py ' + quote(operation) + ' ' + quote(payload);
    return JSON.parse((await execFileAsync('ssh', [args.host, command], {timeout: 45000, maxBuffer: 8 * 1024 * 1024})).stdout);
  }
  async function events() {
    while (!stopped) {
      try {
        eventAbort = new AbortController();
        const response = await fetch(new URL('/api/demo/events?after=' + eventSequence, args['room-url']), {signal: eventAbort.signal});
        if (!response.ok) throw new Error('SSE HTTP ' + response.status);
        let buffer = '';
        const decoder = new TextDecoder();
        for await (const chunk of response.body) {
          buffer += decoder.decode(chunk, {stream: true});
          let boundary;
          while ((boundary = buffer.indexOf('\n\n')) >= 0) {
            const packet = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            const data = packet.split('\n').find(line => line.startsWith('data: '));
            if (!data) continue;
            const event = JSON.parse(data.slice(6));
            if (packet.includes('event: reset')) {
              report.eventGaps.push({room: activeRoom?.id, phase, detail: event});
              eventSequence = Number(packet.match(/^id: (\d+)/m)?.[1]) || eventSequence;
              continue;
            }
            if (event.sequence <= eventSequence) continue;
            eventSequence = event.sequence;
            if (!recordedEventKind(event.kind)) continue;
            const record = {room: activeRoom?.id, phase, receivedMonoMs: performance.now(), event};
            selectedEvents.push(record);
            if (!eventOutput.write(JSON.stringify(record) + '\n')) await new Promise(resolve => eventOutput.once('drain', resolve));
          }
        }
      } catch (error) {
        if (!stopped) report.eventGaps.push({room: activeRoom?.id, phase, message: error.message});
      }
      if (!stopped) await pause(1000);
    }
  }
  let eventTask;
  let bindings;
  let lastSample;
  let sampleOutput;
  async function sample(world) {
    const started = performance.now();
    const [current, interactions, view, visibleRoom] = await Promise.all([
      request('/api/demo/current'), request('/api/demo/interactions'),
      topology.evaluate(() => {
        const instance = window.EasyMeshController;
        const nodes = instance?.topology?.nodes || [];
        return {meshCount: document.querySelectorAll('#topology-visualization .nodes .node').length,
          stations: [...document.querySelectorAll('#topology-visualization .sta-node')].map(element => ({
            mac: element.__data__?.sta?.staMAC, bssid: element.__data__?.sta?.bssid,
            ssid: element.__data__?.sta?.ssid, owner: String(element.__data__?.nodeRef?.id),
            label: element.querySelector('.sta-identity-label')?.textContent,
            visible: element.getBoundingClientRect().width > 0,
          })),
          modelStations: nodes.flatMap(node => (node.STAList || []).map(sta => ({mac: sta.staMAC, bssid: sta.bssid, ssid: sta.ssid}))),
          edges: (instance?.topology?.edges || []).map(edge => ({from: String(edge.from), to: String(edge.to)}))};
      }),
      room.evaluate(() => {
        const roles = {};
        window.__scene?.traverse(object => {
          if (object.userData?.role) roles[object.userData.role] = {position: [object.parent.position.x, -object.parent.position.z], present: object.material.opacity > 0.5};
        });
        return {clock: document.querySelector('#tnow')?.textContent, roles,
          status: document.querySelector('#optimizerStatus')?.textContent, meta: document.querySelector('#worldmeta')?.textContent,
          render: window.__viewer?.renderStats, fullscreen: Boolean(document.fullscreenElement)};
      }),
    ]);
    const checks = evaluate(current, interactions, view, world, bindings);
    const sceneExpected = expectedFrame(world, parseFloat(visibleRoom.clock) * 1000 || 0);
    const sceneErrors = Object.entries(sceneExpected).filter(([role, value]) => {
      const actual = visibleRoom.roles[role];
      return !actual || actual.present !== value.present || value.position.some((coordinate, axis) => Math.abs(coordinate - actual.position[axis]) > 0.15);
    }).map(([role]) => role);
    const result = {monoMs: performance.now(), wallTime: new Date().toISOString(), phase,
      playback: interactions.playback, epoch: interactions.environment_epoch, ...checks,
      sceneErrors, sceneErrorDetails: sceneErrors.map(role => ({role, expected: sceneExpected[role], actual: visibleRoom.roles[role]})),
      associations: view.stations, roomAssociations: current.network?.clients?.map(client => ({role: client.role, mac: client.sta_mac, bssid: client.connected_bssid, ap: client.connected_role, ssid: client.ssid})),
      visibleClock: visibleRoom.clock, requestMs: performance.now() - started};
    if (args['native-audits'] === '1' && ['playing', 'final'].includes(phase)) {
      const roles = activeRoom?.id === 'home-a-disappear-reappear' ? ['sta_mobile_01', 'sta_mobile_02'] :
        ['large-room-extender-evacuation', 'large-room-perimeter-counter-roam',
          'home-a-band-walk-small', 'home-a-fast-transit'].includes(activeRoom?.id) ? ['sta_static_10'] : [];
      if (roles.length) {
        result.nativeLinks = await guest('links', JSON.stringify(Object.fromEntries(
          roles.filter(role => bindings[role]).map(role => [role, bindings[role].container]))));
        result.nativeObservedAt = new Date().toISOString();
      }
    }
    if (sampleOutput) sampleOutput.write(JSON.stringify(result) + '\n');
    lastSample = {current, interactions, view, visibleRoom, result};
    activeRoom?.samples.push(result);
    return result;
  }
  async function settle(world, seconds, label) {
    phase = label;
    const started = performance.now();
    let stable = null;
    let firstRoster = null;
    let firstConvergence = null;
    let samples = 0;
    while (performance.now() - started < seconds * 1000) {
      try {
        const result = await sample(world); samples++;
        if (result.roster && firstRoster === null) firstRoster = (performance.now() - started) / 1000;
        if (result.converged) {
          if (firstConvergence === null) firstConvergence = (performance.now() - started) / 1000;
          stable ??= performance.now();
          if (performance.now() - stable >= 5000) return {passed: true, elapsedSeconds: (performance.now() - started) / 1000, firstRosterSeconds: firstRoster, firstConvergenceSeconds: firstConvergence, samples, final: result};
        } else stable = null;
      } catch (error) { stable = null; activeRoom?.errors.push({phase, message: error.message}); }
      await pause(1000);
    }
    return {passed: false, timeoutSeconds: seconds, elapsedSeconds: (performance.now() - started) / 1000,
      firstRosterSeconds: firstRoster, firstConvergenceSeconds: firstConvergence, samples, final: lastSample?.result};
  }
  async function screenshot(label) {
    await Promise.all([room.screenshot({path: path.join(directory, activeRoom.id + '-' + label + '-room.png')}),
      topology.screenshot({path: path.join(directory, activeRoom.id + '-' + label + '-topology.png')})]);
    save(activeRoom.id + '-' + label + '.json', lastSample);
  }
  async function loadWorld(id) {
    await room.locator('#world').waitFor({state: 'visible'});
    const started = performance.now();
    const clickedAt = Date.now();
    const [response] = await Promise.all([
      room.waitForResponse(response => response.url().endsWith('/api/demo/world/apply'), {timeout: 45000}),
      room.locator('#world').selectOption(id),
    ]);
    const body = await response.json();
    if (!response.ok()) throw new Error('World apply HTTP ' + response.status() + ': ' + JSON.stringify(body));
    await room.waitForFunction(() => !document.querySelector('#world').disabled, null, {timeout: 45000});
    const live = await request('/api/demo/world');
    const timing = response.request().timing();
    return {acknowledgementMs: performance.now() - started, clickToRequestMs: timing.startTime - clickedAt,
      requestTiming: timing, result: body, live};
  }
  async function clickPlay() {
    const button = await room.evaluate(() => document.fullscreenElement ? '#fullscreenPlay' : '#play');
    const [response] = await Promise.all([
      room.waitForResponse(response => response.url().endsWith('/api/demo/playback'), {timeout: 20000}),
      room.locator(button).click(),
    ]);
    if (!response.ok()) throw new Error('Play HTTP ' + response.status() + ': ' + await response.text());
  }
  function summarizeRoom(result) {
    const relevant = selectedEvents.filter(record => record.room === result.id);
    const verifications = relevant.filter(record => record.event.kind === 'optimizer.verification').map(record => ({phase: record.phase, ...record.event.payload}));
    const during = result.samples.filter(sample => sample.phase === 'playing');
    const agreement = viewAgreement(during);
    const changes = [];
    const previous = new Map();
    for (const sample of result.samples) for (const client of sample.associations) {
      const prior = previous.get(client.mac);
      if (prior && prior.bssid !== client.bssid) changes.push({mac: client.mac, from: prior.bssid, to: client.bssid, phase: sample.phase, timeMs: sample.playback.time_ms});
      previous.set(client.mac, client);
    }
    const observed = new Map();
    const pending = new Map();
    const viewLag = [];
    for (const sample of result.samples) {
      for (const client of sample.roomAssociations || []) {
        const previousBssid = observed.get(client.mac);
        if (previousBssid && previousBssid !== client.bssid) pending.set(client.mac, {bssid: client.bssid, since: sample.monoMs});
        observed.set(client.mac, client.bssid);
      }
      for (const client of sample.associations) {
        const update = pending.get(client.mac);
        if (update?.bssid === client.bssid) { viewLag.push((sample.monoMs - update.since) / 1000); pending.delete(client.mac); }
      }
    }
    result.performance = {
      ...eventPerformance(relevant),
      sampleRequestMs: distribution(result.samples.map(sample => sample.requestMs)),
      roomObservationToTopologySeconds: distribution(viewLag), unresolvedViewUpdates: [...pending.keys()],
      motionConvergedSamples: during.filter(sample => sample.converged).length, motionSamples: during.length,
      motionStrongestApSamples: during.filter(sample => sample.strongestApConverged).length,
      viewMismatchSeconds: agreement.observedBadSpanSeconds, viewAgreement: agreement, visibleAssociationChanges: changes,
      observedClientCounts: [...new Set(during.map(sample => sample.actualClients))].sort((left, right) => left - right),
    };
    result.verifications = verifications;
    result.scriptCorrect = during.length > 0 && during.every(sample => !sample.scriptErrors.length && !sample.mediumFault);
    result.sceneCorrect = during.length > 0 && during.every(sample => !sample.sceneErrors.length);
    result.viewCorrect = during.every(sample => !sample.duplicates && sample.meshCount === 6 && sample.associations.every(client => client.visible && client.label)) && agreement.passed;
    const golden = JSON.parse(fs.readFileSync(path.join(args.worlds, result.id + '.world.json')));
    const presencePhases = [];
    for (const frame of golden.generations) {
      const roles = Object.keys(bindings).filter(role => frame.present[role]);
      if (!presencePhases.length || !same(roles, presencePhases.at(-1).roles)) presencePhases.push({startMs: frame.time_ms, roles});
    }
    result.presencePhases = presencePhases.map((entry, index) => {
      const endMs = presencePhases[index + 1]?.startMs ?? golden.duration_ms + 1;
      const matches = result.samples.filter(sample => sample.playback.time_ms >= entry.startMs && sample.playback.time_ms < endMs && sample.roster);
      return {startMs: entry.startMs, endMs, clients: entry.roles.length, topologyVerified: matches.length > 0,
        firstVerifiedRoomTimeMs: matches[0]?.playback.time_ms ?? null};
    });
    result.passed = Boolean(result.load?.passed && result.initial?.passed && result.playback?.completed && result.final?.passed &&
      result.checkpoints.every(checkpoint => checkpoint.passed) && result.scriptCorrect && result.sceneCorrect && result.viewCorrect &&
      result.presencePhases.every(entry => entry.topologyVerified) &&
      result.kernel?.passed && !result.errors.length && !report.errors.some(error => error.room === result.id));
    result.sampleCount = result.samples.length;
    delete result.samples;
  }
  try {
    hostMonitor = await startHostMonitor(args.host, directory);
    const initial = await request('/api/demo/interactions');
    if (initial.lease?.held || initial.recording?.active) throw new Error('Refusing to steal a control lease or interrupt recording');
    report.before = await guest('identity', args.flavor);
    const current = await request('/api/demo/current');
    report.temporaryActionLimit = current.optimizer.maximum_actions;
    eventSequence = current.sequence;
    bindings = Object.fromEntries(current.network.clients.map(client => [client.role, client]));
    if (Object.keys(bindings).length !== 20) throw new Error('Preflight requires default twenty-client baseline after room-service restart');
    save('bindings.json', bindings);
    const catalog = (await request('/api/demo/worlds')).worlds;
    report.catalog = catalog;
    eventTask = events();
    await room.goto(args['room-url']);
    await room.waitForFunction(() => window.__viewer && !document.querySelector('#world').disabled, null, {timeout: 60000});
    await topology.goto(args['topology-url']);
    await topology.locator('[data-tab="topology"]').click();
    await topology.waitForSelector('.sta-node', {timeout: 30000});
    await topology.locator('#topologyFullscreen').click();
    const preferred = ['home-a-stationary', 'home-a-one-client-handover', 'large-room-extender-evacuation', 'large-room-perimeter-counter-roam'];
    const names = args.world || [...preferred.filter(name => catalog.some(item => item.id === name)), ...catalog.map(item => item.id).filter(name => !preferred.includes(name))];
    for (const id of names) {
      activeRoom = {id, started: new Date().toISOString(), samples: [], errors: [], checkpoints: []};
      sampleOutput = fs.createWriteStream(path.join(directory, id + '-samples.jsonl'));
      phase = 'loading';
      console.log(JSON.stringify({lab: args.flavor, room: id, phase}));
      try {
        const world = JSON.parse(fs.readFileSync(path.join(args.worlds, id + '.world.json')));
        const loaded = await loadWorld(id);
        activeRoom.load = {passed: loaded.live.golden_sha256 === world.golden_sha256 && loaded.live.name === world.name,
          acknowledgementMs: loaded.acknowledgementMs, clickToRequestMs: loaded.clickToRequestMs,
          requestTiming: loaded.requestTiming, server: loaded.result, goldenSha256: world.golden_sha256};
        if (!activeRoom.load.passed) throw new Error('Deployed golden identity does not match the selected room');
        activeRoom.initial = await settle(world, Number(args['initial-timeout'] || 90), 'loaded');
        await screenshot('loaded');
        await room.bringToFront();
        if (!await room.evaluate(() => Boolean(document.fullscreenElement))) await room.locator('#roomFullscreen').click();
        phase = 'playing';
        await clickPlay();
        const playStarted = performance.now();
        let checkpointMs = 0;
        let middleCaptured = false;
        let previousTime = 0;
        let completed = false;
        const visited = new Set();
        while (performance.now() - playStarted - checkpointMs < world.duration_ms * 2 + 30000) {
          phase = 'playing';
          const result = await sample(world);
          if (result.playback.time_ms < previousTime) activeRoom.errors.push({phase, message: 'Playback clock went backwards'});
          previousTime = result.playback.time_ms;
          if (!middleCaptured && previousTime >= world.duration_ms / 2) {
            if (id === 'home-a-asymmetric-link') {
              const command = 'lxc exec ' + quote(args.vm) + ' -- python3 /tmp/room-feature-rf-audit.py ' + quote(args.flavor);
              const audit = JSON.parse((await execFileAsync('ssh', [args.host, command], {timeout: 30000})).stdout);
              save('../asymmetric-rf-audit.json', audit);
            }
            await screenshot('moving'); middleCaptured = true;
          }
          if (result.playback.status === 'completed') { completed = true; break; }
          if (result.playback.status === 'paused') {
            const checkpoint = result.playback.checkpoint_ms;
            if (!(world.pause_at_ms || []).includes(checkpoint) || visited.has(checkpoint)) throw new Error('Unexpected playback pause: ' + JSON.stringify(result.playback));
            visited.add(checkpoint);
            const started = performance.now();
            const settled = await settle(world, Number(args['checkpoint-timeout'] || 60), 'checkpoint-' + checkpoint);
            activeRoom.checkpoints.push({timeMs: checkpoint, ...settled});
            await screenshot('checkpoint-' + checkpoint);
            await clickPlay(); checkpointMs += performance.now() - started;
          }
          await pause(1000);
        }
        activeRoom.playback = {completed, durationMs: world.duration_ms, wallSeconds: (performance.now() - playStarted) / 1000,
          checkpointWaitSeconds: checkpointMs / 1000, checkpointsVisited: [...visited]};
        if (!completed) throw new Error('Playback exceeded bounded wall-clock deadline');
        activeRoom.final = await settle(world, Number(args['final-timeout'] || 120), 'final');
        await screenshot('final');
        const offline = Object.fromEntries(Object.entries(bindings).filter(([, client]) => !lastSample.result.wanted.includes(lower(client.sta_mac))).map(([role, client]) => [role, client.container]));
        const links = await guest('links', JSON.stringify(offline));
        activeRoom.kernel = {offlineCount: Object.keys(offline).length, passed: Object.values(links).every(value => value.includes('Not connected')), links};
      } catch (error) {
        activeRoom.errors.push({phase, message: error.stack});
      } finally {
        if (await room.evaluate(() => Boolean(document.fullscreenElement)).catch(() => false)) await room.locator('#roomFullscreen').click().catch(() => {});
        activeRoom.finished = new Date().toISOString();
        summarizeRoom(activeRoom);
        sampleOutput.end(); sampleOutput = null;
        save(activeRoom.id + '-result.json', activeRoom);
        report.rooms.push(activeRoom);
        console.log(JSON.stringify({lab: args.flavor, room: activeRoom.id, passed: activeRoom.passed,
          loaded: activeRoom.initial?.passed, played: activeRoom.playback?.completed, final: activeRoom.final?.passed,
          verified: activeRoom.performance.verifiedActions, errors: activeRoom.errors.map(error => error.message.split('\n')[0])}));
        save('report.json', report);
      }
    }
  } catch (error) {
    report.failure = error.stack;
  } finally {
    phase = 'restore'; activeRoom = null;
    try {
      if (await room.evaluate(() => Boolean(document.fullscreenElement)).catch(() => false)) await room.locator('#roomFullscreen').click();
      if (token) {
        const [response] = await Promise.all([
          room.waitForResponse(response => response.url().endsWith('/api/demo/world/apply'), {timeout: 45000}),
          room.locator('#defaultWorld').click(),
        ]);
        report.restoration = {applied: response.ok()};
        const world = JSON.parse(fs.readFileSync(path.join(args.worlds, 'home-a-private-client-room-walk.world.json')));
        report.restoration.convergence = await settle(world, 120, 'restore');
        await room.request.delete(new URL('/api/demo/interactions/lease', args['room-url']).href,
          {data: {token, command_id: 'room-features-release-' + Date.now()}});
      }
      report.after = await guest('identity', args.flavor);
      report.nativeIdentitiesUnchanged = same(report.before, report.after);
    } catch (error) { report.restoreError = error.stack; }
    stopped = true; eventAbort?.abort();
    if (eventTask) await eventTask;
    eventOutput.end();
    if (hostMonitor) report.hostMonitor = await hostMonitor.stop();
    report.finished = new Date().toISOString();
    report.passed = !report.failure && report.rooms.length > 0 && report.rooms.every(result => result.passed) &&
      report.nativeIdentitiesUnchanged && report.restoration?.convergence?.passed && !report.errors.length && !report.eventGaps.length;
    save('report.json', report);
    await browser.close();
  }
  console.log(JSON.stringify({lab: args.flavor, finished: report.finished, passed: report.passed, rooms: report.rooms.length, failure: report.failure}));
  return report;
}

module.exports = {expectedFrame, evaluate, distribution, eventPerformance, viewAgreement, recordedEventKind};
if (require.main === module) run(argumentsFrom(process.argv.slice(2))).then(report => { process.exitCode = report.passed ? 0 : 1; })
  .catch(error => { console.error(error); process.exitCode = 2; });
