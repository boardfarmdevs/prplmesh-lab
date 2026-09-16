'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const url = process.argv[2];
const output = process.argv[3];
const expectedRows = 6;

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}),
    args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1500, height: 1100}});
  const errors = [], mutations = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (!['GET', 'HEAD'].includes(request.method())) mutations.push(request.url());
  });
  try {
    await page.goto(url, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => window.EasyMeshController?.refreshIntervals.topology);
    await page.evaluate(() => window.EasyMeshController.showTab('topology'));
    await page.waitForFunction(() => window.EasyMeshController?.roomLayout?.snapshot?.rf_observations?.bss_loads?.length >= 30,
      null, {timeout: 120000});
    await page.waitForFunction(() => document.querySelectorAll('.nodes .node > image').length >= 5);
    const snapshot = await page.evaluate(() => window.EasyMeshController.roomLayout.snapshot);
    assert.equal(snapshot.rf_observations.enabled, true);
    assert.equal(snapshot.rf_observations.policy_enabled, false);
    assert.equal(snapshot.rf_observations.error, '');
    await page.locator('.nodes .node > image').evaluateAll(images => {
      for (const image of images) image.dataset.rfDevice = image.__data__.id;
    });
    const results = [];
    for (const node of snapshot.nodes) {
      const icon = page.locator('.nodes .node > image[data-rf-device="' + node.device_id + '"]');
      await icon.hover({force: true});
      await page.waitForFunction(() => /[0-9]+[.][0-9]+%/.test(document.querySelector('#custom-tooltip')?.textContent || ''));
      const text = await page.locator('#custom-tooltip').innerText();
      assert.match(text, /AP-reported BSS load/);
      assert.match(text, /2.4 GHz/);
      assert.match(text, /5 GHz/);
      assert.match(text, /6 GHz/);
      assert.ok(await page.locator('#custom-tooltip tbody tr').count() >= expectedRows);
      results.push({role: node.role, device_id: node.device_id, text});
    }
    await page.locator('#follow-room-layout').uncheck();
    await page.locator('.nodes .node > image[data-rf-device="' + snapshot.nodes[0].device_id + '"]').hover({force: true});
    await page.waitForFunction(() => /[0-9]+[.][0-9]+%/.test(document.querySelector('#custom-tooltip')?.textContent || ''));
    await page.waitForTimeout(2200);
    assert.match(await page.locator('#custom-tooltip').innerText(), /[0-9]+\.[0-9]+%/);
    if (output) await page.screenshot({path: output + '.png'});
    await page.route('**/api/v1/room-layout', async route => {
      const response = await route.fetch();
      const body = await response.json();
      for (const row of body.rf_observations.bss_loads) row.observed_at = new Date(Date.now() - 60000).toISOString();
      await route.fulfill({response, json: body});
    });
    await page.waitForFunction(() => /stale/.test(document.querySelector('#custom-tooltip')?.textContent || ''), null, {timeout: 15000});
    assert.doesNotMatch(await page.locator('#custom-tooltip').innerText(), /[0-9]+\.[0-9]+%/);
    await page.unroute('**/api/v1/room-layout');
    await page.route('**/api/v1/room-layout', route => route.fulfill({status: 503, json: {error: 'fixture'}}));
    await page.waitForFunction(() => /Room telemetry unavailable/.test(document.querySelector('#custom-tooltip')?.textContent || ''), null, {timeout: 15000});
    assert.doesNotMatch(await page.locator('#custom-tooltip').innerText(), /[0-9]+\.[0-9]+%/);
    await page.unroute('**/api/v1/room-layout');
    await page.locator('#follow-room-layout').check();
    assert.deepEqual(errors, []);
    assert.deepEqual(mutations, []);
    const result = {passed: true, url, nodes: results, cases: ['live load, stations and three bands',
      'stationary hover refresh', 'manual layout', 'stale telemetry hidden', 'unavailable telemetry hidden', 'GET-only']};
    if (output) fs.writeFileSync(output + '.json', JSON.stringify(result, null, 2) + '\n');
    console.log('PASS: live AP RF hover, passive collection, stationary updates and unavailable/stale handling: ' + url);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
