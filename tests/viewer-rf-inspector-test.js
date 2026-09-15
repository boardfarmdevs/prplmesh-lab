'use strict';
const assert = require('node:assert/strict');
const {describe, render} = require('../wmediumd/configurator/worlds/viewer/rf-inspector.js');
const now = Date.parse('2026-09-14T12:00:00Z');
const observation = {role: 'gateway', bssid: 'ap', radio_id: 'radio', channel: 36, utilization: 0,
  station_count: 0, observed_at: new Date(now - 100).toISOString(), source: 'native_ap_metrics',
  transport: 'ieee1905-ethernet', epoch: 'provider-1'};
const input = {now, selected: 'gateway', view: 'native',
  optimizer: {rf_observations: {enabled: true, maximum_age_seconds: 5, bss_loads: [observation]}}};
assert.match(describe(input), /Utilization \(0–255\): 0 · received/);
assert.match(describe(input), /Associated stations: 0 · received/);
assert.match(describe(input), /Sample window: unknown/);
assert.match(describe({...input, now: now + 6000}), /Utilization \(0–255\): — unavailable\/stale/);
assert.doesNotMatch(describe({...input, selected: 'other'}), /BSSID ap/);
assert.match(describe({...input, optimizer: {}, world: {utilization: 255}}), /collector inactive/);
assert.match(describe({...input, view: 'configured', world: {traffic_experiment: {}}}), /not native measurements/);
const decision = {role: 'client', sta_mac: 'client-mac', reason: 'native_load_no_safe_quieter_target',
  action: 'none', load_evidence: {candidate_assessments: [{bssid: '<ap>', state: 'excluded', reasons: ['same_channel']}]}};
const decisionInput = {...input, selected: 'client', view: 'decision', optimizer: {client_decisions: [decision]}};
assert.match(describe(decisionInput), /<ap>: excluded · same_channel/);
const element = {textContent: ''};
render(element, decisionInput);
assert.match(element.textContent, /<ap>/);
assert.equal(element.innerHTML, undefined);
assert.match(describe({...input, view: 'traffic', traffic: {state: 'completed', history: [
  {state: 'completed', transmitted_packets: 10, received_echo_replies: 0}]}}), /Delivered echo replies: 0/);
assert.match(describe({...input, view: 'traffic', traffic: {state: 'failed', history: [
  {state: 'failed', transmitted_packets: null, received_echo_replies: null}]}}), /Generated: unknown/);
console.log('PASS: RF inspector provenance, zero, freshness, exclusions and traffic accounting');
