# prplMesh interactive Pages

The RDK explorer’s visual components, colors, typography and interaction model
are reused here with prpl-specific native processes and source references.
The landing page links to the architecture explorer, disconnected room sandbox
and room manual. The topology diagram is illustrative; no public page controls
a lab or reports invented native measurements.

## Build and preview

Requires Node.js 22.13+ (24 recommended), npm and Python 3. Dependencies and
fonts are pinned in `package-lock.json`; no CDN is needed at runtime.

```sh
cd explorer
npm ci
npm run build
python3 -m http.server 4173 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:4173/`. Output is `explorer/site/`: landing page,
`explorer/`, `viewer/`, all checked-in `golden/` rooms and a build manifest.
No VM, native build, credentials or live API is needed. Source links use the
explicit evidence revision in `app/system.ts`; `build.json` separately records
the build checkout and whether it was dirty.

```sh
npx playwright install chromium
npm test
```

Set `CHROMIUM_PATH` to reuse a compatible browser. Tests serve actual static
output at both `/` and `/prplmesh-lab/`, exercise inspectors, topology layouts,
protocol paths, mobile layout, room playback and manual navigation. They check
all room files, pinned source links and absence of external/live API requests.
Generated assets, dependencies and browser evidence are ignored by Git.

## Publish

The site is built and published by the Pages workflow
(`.github/workflows/pages.yml`, the same in the four lab repositories) on every
push to `main`: `pages/build` runs `npm ci`, `npm run build` and `npm test` here,
and `pages/finish-site.py` adds the labs bar shared by the four lab sites. The
Pages source is **GitHub Actions**, and the `github-pages` environment must allow
`main`.

The deployment provides:

- `https://boardfarmdevs.github.io/prplmesh-lab/`
- `https://boardfarmdevs.github.io/prplmesh-lab/explorer/`
- `https://boardfarmdevs.github.io/prplmesh-lab/viewer/`
- `https://boardfarmdevs.github.io/prplmesh-lab/viewer/manual.html`

Every push rebuilds the whole site together, avoiding stale viewer assets or
missing room files. To preview the finished site locally:

```sh
pages/build && python3 pages/finish-site.py
python3 -m http.server -d dist/site 8000
```

Public HTTPS Pages cannot proxy a private HTTP VM. Use the lab’s own URL or
its authenticated remote-access gateway for live operation. Keep screenshots
and illustrative diagrams separate from acceptance evidence.
