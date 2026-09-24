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

## Enable on GitHub when ready

The workflow builds and tests on relevant pushes to `main`.
Publication remains disabled until the repository owner opts in:

1. Push the source and `.github/workflows/pages.yml` to the canonical branch.
2. In **Settings → Pages**, select **GitHub Actions** as the source.
3. In **Settings → Secrets and variables → Actions → Variables**, add the
   repository variable `PUBLISH_PAGES` with value `true`.
4. Open the **Interactive documentation** Actions run for that push and choose
   **Re-run all jobs**. If the `github-pages` environment restricts branches,
   allow `main`.

The successful deployment provides:

- `https://boardfarmdevs.github.io/prplmesh-lab/`
- `https://boardfarmdevs.github.io/prplmesh-lab/explorer/`
- `https://boardfarmdevs.github.io/prplmesh-lab/viewer/`
- `https://boardfarmdevs.github.io/prplmesh-lab/viewer/manual.html`

Later relevant pushes rebuild the whole site together, avoiding stale viewer
assets or missing room files. Remove the variable to stop future publication.
No `gh-pages` branch, SPA rewrite, backend or change to RDK Pages is required.
See [GitHub’s Pages workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Public HTTPS Pages cannot proxy a private HTTP VM. Use the lab’s own URL or
its authenticated remote-access gateway for live operation. Keep screenshots
and illustrative diagrams separate from acceptance evidence.
