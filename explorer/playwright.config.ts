import { defineConfig } from '@playwright/test';

const environment = { ...process.env };
delete environment.DISPLAY;
delete environment.WAYLAND_DISPLAY;

export default defineConfig({
  testDir: './tests',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4178',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      env: environment,
      executablePath: process.env.CHROMIUM_PATH,
      args: [
        '--no-sandbox',
        '--num-raster-threads=2',
        '--ozone-platform=headless',
        '--enable-unsafe-swiftshader',
        '--use-gl=angle',
        '--use-angle=swiftshader',
      ],
    },
  },
  webServer: {
    command: 'python3 tests/serve-pages.py',
    url: 'http://127.0.0.1:4178/prplmesh-lab/',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
