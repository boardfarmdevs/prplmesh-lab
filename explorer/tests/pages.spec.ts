import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { entries, revision } from '../app/system';

test('component references are real prpl sources at the pinned revision', () => {
  for (const component of Object.values(entries)) {
    for (const related of component.related)
      expect(entries[related]).toBeDefined();
    for (const reference of component.sources) {
      execFileSync('git', ['cat-file', '-e', `${revision}:${reference}`], {
        cwd: '..',
      });
    }
  }
});

for (const prefix of ['', '/prplmesh-lab']) {
  test(`static navigation and assets at ${prefix || '/'}`, async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    const badRequests: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.hostname !== '127.0.0.1' || url.pathname.includes('/api/'))
        badRequests.push(request.url());
    });
    page.on('response', (response) => {
      if (response.status() >= 400) badRequests.push(response.url());
    });
    await page.goto(`${prefix}/`);
    await page.getByRole('link', { name: /System explorer/ }).click();
    await expect(
      page.getByRole('heading', { name: 'Inside the prplMesh lab' }),
    ).toBeVisible();
    await expect(page.locator('.offline-label')).toContainText('DISCONNECTED');
    await page.reload();
    await expect(page.locator('.system-card')).toHaveCount(6);
    await page.goto(`${prefix}/explorer/index.html`);
    await expect(page.locator('.system-card')).toHaveCount(6);
    expect(
      (await request.get(`${prefix}/explorer/missing-route`)).status(),
    ).toBe(404);
    const slashless = await request.get(`${prefix}/explorer`, {
      maxRedirects: 0,
    });
    expect(slashless.status()).toBe(301);
    expect(errors).toEqual([]);
    expect(badRequests).toEqual([]);
  });
}

test('architecture drawers, related components and keyboard closing', async ({
  page,
}) => {
  await page.goto('/prplmesh-lab/explorer/');
  await page.locator('.gateway .card-heading').click();
  const dialog = page.getByRole('dialog');
  await expect(
    dialog.getByRole('heading', { name: 'prpl-controller', exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole('button', { name: 'beerocks_controller', exact: true })
    .click();
  await expect(dialog).toContainText('Native in-memory model; no RDK MariaDB');
  await expect(dialog.locator('a.detail-source').first()).toHaveAttribute(
    'href',
    new RegExp(`/prplmesh-lab/blob/${revision}/`),
  );
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await page
    .locator('.gateway .inner-block')
    .filter({ hasText: 'Controller UI + adapter' })
    .click();
  await dialog
    .getByRole('button', { name: 'Explore network topology' })
    .click();
  await expect(page.locator('.topology-view')).toBeVisible();
});

test('three illustrative topology arrangements and every protocol walkthrough', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/prplmesh-lab/explorer/');
  await page
    .getByRole('tab', { name: 'Network topology', exact: true })
    .click();
  for (const name of ['Star', 'Chain', 'Branch']) {
    await page.getByRole('tab', { name, exact: true }).click();
    await expect(page.locator('.top-client')).toHaveCount(20);
    await page.locator('.top-client').first().click();
    await expect(page.getByRole('dialog')).toContainText(
      'Illustrative assignment; no live metrics',
    );
    await page.keyboard.press('Escape');
  }
  await page.getByRole('tab', { name: 'Protocol paths' }).click();
  for (const name of [
    'Client traffic',
    'Commanded steering',
    'Band steering',
    'Mesh onboarding',
    'RF feedback loop',
  ]) {
    await page.getByRole('tab', { name, exact: true }).click();
    const steps = page.locator('.step-list button');
    for (let index = 0; index < (await steps.count()); index++) {
      await steps.nth(index).click();
      await expect(page.locator('.step-detail h3')).not.toBeEmpty();
      await page.locator('.path-block').first().click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await page.keyboard.press('Escape');
    }
  }
  await page.getByRole('tab', { name: 'Evidence & limits' }).click();
  await expect(page.locator('.state-view')).toContainText(
    'No new all-green full suite',
  );
  expect(errors).toEqual([]);
});

test('all room files ship and representative previews remain disconnected', async ({
  page,
  request,
}) => {
  const unexpected: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1' || url.pathname.includes('/api/'))
      unexpected.push(request.url());
  });
  const manifest = await (await request.get('/prplmesh-lab/build.json')).json();
  expect(manifest.mode).toBe('disconnected');
  const names = readdirSync(
    path.resolve('../wmediumd/configurator/worlds/golden'),
  )
    .filter((name) => name.endsWith('.world.json'))
    .sort();
  expect(manifest.rooms).toEqual(names);
  for (const filename of names) {
    const response = await request.get(`/prplmesh-lab/golden/${filename}`);
    expect(response.ok()).toBe(true);
    expect(await response.json()).toEqual(
      JSON.parse(
        readFileSync(
          path.resolve('../wmediumd/configurator/worlds/golden', filename),
          'utf8',
        ),
      ),
    );
  }
  await page.goto('/prplmesh-lab/viewer/');
  await expect(page.locator('#worldmeta')).not.toContainText('Loading');
  for (const name of [
    'band-upgrade-24-5',
    'rf-asymmetric-ack',
    'rf-packet-size-counters',
    'fifty-client-counter-roam',
    'backhaul-branch-formation',
  ]) {
    await page.locator('#world').selectOption(name);
    await expect(page.locator('#worldmeta')).toContainText(name);
    await expect(page.locator('#play')).toBeEnabled();
  }
  const initial = await page.locator('#tnow').textContent();
  await page.locator('#play').click();
  await expect(page.locator('#tnow')).not.toHaveText(initial || '0.0 s');
  await page.locator('#play').click();
  await page.locator('#openManual').click();
  await expect(page.locator('#viewerManual')).toBeVisible();
  await expect(
    page.frameLocator('#viewerManual iframe').locator('h1'),
  ).toBeVisible();
  await expect(
    page
      .frameLocator('#viewerManual iframe')
      .getByRole('link', { name: 'public sandbox', exact: true }),
  ).toHaveAttribute(
    'href',
    'https://boardfarmdevs.github.io/prplmesh-lab/viewer/?world=home-a-private-client-room-walk',
  );
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});

test('mobile layout contains the explorer and preserves navigation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/prplmesh-lab/explorer/');
  await expect(
    page.getByRole('heading', { name: 'Inside the prplMesh lab' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole('link', { name: 'Manual', exact: true }).click();
  await expect(page.locator('h1')).toBeVisible();
});
