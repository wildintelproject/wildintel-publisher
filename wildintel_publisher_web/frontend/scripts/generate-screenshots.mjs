#!/usr/bin/env node
/**
 * Regenerates the web wizard screenshots used in docs/guide-web-*.md.
 *
 * Runs a real Vite dev server (no backend needed) and drives it with
 * Playwright, using the system-installed Chrome (`channel: 'chrome'` — no
 * extra ~150MB browser download). Every /api/** request is intercepted at
 * the network layer and answered with realistic-but-fake fixture data (see
 * FIXTURES below), matching the exact response shapes each endpoint
 * documents in src/api.ts — no real Trapper/HuggingFace Hub/Zenodo/B2SHARE/
 * GBIF account is ever contacted.
 *
 * Usage: npm run screenshots   (from wildintel_publisher_web/frontend)
 */
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_DIR = path.resolve(__dirname, '..')
const OUT_DIR = path.resolve(__dirname, '../../../docs/img/web')
const PORT = 5199
const BASE_URL = `http://localhost:${PORT}`

// ── Fixture data — deliberately fake, but shaped exactly like a real
// response, and reusing GBIF's own publicly-documented sandbox demo
// org/installation/credentials (see docs/guide-cli.md) rather than making
// up new-looking ones. ────────────────────────────────────────────────────
const HFH_REPO_ID = 'wildintel/sierra-cazorla-camtraps'
const DOCS_DIR = '/home/alice/Documents/wildintel-publisher'

const FIXTURES = {
  'GET /api/version': { current: '1.4.0', latest: '1.4.0', update_available: false, release_url: null },
  'POST /api/camtrapdp/generate-metadata': {
    product_type: 'camtrapdp',
    title: 'Sierra de Cazorla Camera Traps 2025',
    description: 'Camera-trap monitoring of medium and large mammals in Sierra de Cazorla, Jaén (Spain), 2024–2025.',
    version: '1.0.0',
    license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: 'https://creativecommons.org/licenses/by/4.0/' },
    authors: [{ name: 'Alice Example', affiliation: 'WildINTEL Project' }],
    homepage: null,
    hfh_repo_id: null,
  },
  'GET /api/hfh/config': {
    username: 'wildintel', output_dir: `${DOCS_DIR}/hfh`, version: '1.0.0', timeout: 60, has_token: false,
  },
  'POST /api/hfh/test-token': { ok: true, username: 'wildintel', version_conflict: false },
  'GET /api/zenodo/config': {
    environment: 'sandbox', communities: null, output_dir: `${DOCS_DIR}/zenodo`, version: '1.0.0', timeout: 60, has_token: false,
  },
  'POST /api/zenodo/test-token': { ok: true },
  'POST /api/zenodo/sync-doi': {
    doi: '10.5281/zenodo.8241234', repo_url: `https://huggingface.co/datasets/${HFH_REPO_ID}`,
  },
  'GET /api/b2share/config': {
    environment: 'sandbox', community_id: null, output_dir: `${DOCS_DIR}/b2share`, version: '1.0.0', timeout: 60, has_token: false,
  },
  'POST /api/b2share/test-token': { ok: true },
  'POST /api/b2share/sync-pid': {
    pid: '10.23728/b2share.8f1a2b3c', repo_url: `https://huggingface.co/datasets/${HFH_REPO_ID}`,
  },
  'GET /api/gbif/config': {
    environment: 'sandbox', publishing_organization_key: null, installation_key: null,
    registry_language: 'eng', output_dir: `${DOCS_DIR}/gbif`, has_credentials: false,
  },
  'POST /api/gbif/test-credentials': { ok: true },
  'POST /api/publish/start': { task_id: 'demo-task' },
  'GET /api/publish/demo-task': {
    status: 'done', error: null, dry_run: false,
    repos: {
      hfh: {
        status: 'done', stage: 'done', error: null,
        repo_url: `https://huggingface.co/datasets/${HFH_REPO_ID}`, doi: null, pid: null, output_dir: `${DOCS_DIR}/hfh`,
      },
      zenodo: {
        status: 'done', stage: 'done', error: null,
        repo_url: 'https://zenodo.org/records/8241234', doi: '10.5281/zenodo.8241234', pid: null,
        output_dir: `${DOCS_DIR}/zenodo`,
      },
      b2share: {
        status: 'done', stage: 'done', error: null,
        repo_url: 'https://trng-b2share.eudat.eu/records/8f1a2b3c', doi: null, pid: '10.23728/b2share.8f1a2b3c',
        output_dir: `${DOCS_DIR}/b2share`,
      },
      gbif: {
        status: 'done', stage: 'done', error: null,
        repo_url: 'https://registry.gbif-test.org/dataset/3a2f9c1e-7e21-4b7a-9c3e-1f0d2a5b6c7d', doi: null, pid: null,
        output_dir: `${DOCS_DIR}/gbif`,
      },
    },
  },
}

function waitForServer(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    (async function poll() {
      while (Date.now() < deadline) {
        try {
          const r = await fetch(url)
          if (r.ok || r.status === 404) return resolve()
        } catch { /* not up yet */ }
        await new Promise((r) => setTimeout(r, 300))
      }
      reject(new Error(`Timed out waiting for ${url}`))
    })()
  })
}

async function installApiMocks(page) {
  await page.route('**/api/**', (route) => {
    const req = route.request()
    const { pathname } = new URL(req.url())
    const key = `${req.method()} ${pathname}`
    if (key === 'GET /api/health') return route.fulfill({ status: 200, body: '{}' })
    if (!(key in FIXTURES)) {
      console.warn(`[generate-screenshots] Unmocked request: ${key} — failing it.`)
      return route.fulfill({ status: 501, contentType: 'application/json', body: JSON.stringify({ detail: `No fixture for ${key}` }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FIXTURES[key]) })
  })
}

/** `locator` is usually `page.locator('main > div')` (the whole wizard), but for
 * the two sync sections it's scoped to just that section — both can be on
 * screen at once, so cropping to one keeps the other out of the shot
 * regardless of its own state (see the Zenodo/B2SHARE sync steps below). */
async function shot(locator, name) {
  await locator.screenshot({ path: path.join(OUT_DIR, name) })
  console.log(`  ✔ ${name}`)
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })

  console.log(`Starting Vite dev server on ${BASE_URL} ...`)
  const vite = spawn('npx', ['vite', '--port', String(PORT), '--strictPort'], { cwd: FRONTEND_DIR, stdio: 'pipe' })
  vite.stderr.on('data', (d) => process.stderr.write(`[vite] ${d}`))
  try {
    await waitForServer(BASE_URL)

    const browser = await chromium.launch({ channel: 'chrome' })
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
    await installApiMocks(page)

    console.log('Walking the wizard...')
    await page.goto(BASE_URL)
    await page.getByRole('button', { name: /get started/i }).click()

    // Step 0-2: Camtrap DP, local directory, past the download-result screen.
    await page.getByRole('button', { name: /camtrap dp/i }).click()
    await page.getByRole('button', { name: /local directory/i }).click()
    await page.getByLabel('Directory').fill(`${DOCS_DIR}/trapper`)
    const nextBtn = page.getByRole('button', { name: /^next$/i })
    await nextBtn.waitFor()
    await page.waitForFunction(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => /^next$/i.test(b.textContent ?? ''))
      return btn && !btn.disabled
    })
    await nextBtn.click()
    await nextBtn.click()

    // Step 3: select all four repositories, reorder so HFH publishes first
    // (GBIF's own archive URL suggestion depends on it) — screenshot the
    // selection + publish-order screen.
    await page.getByRole('button', { name: /hugging face hub/i }).click()
    await page.getByRole('button', { name: /zenodo/i }).click()
    await page.getByRole('button', { name: /b2share/i }).click()
    await page.getByRole('button', { name: /gbif/i }).click()
    await shot(page.locator('main > div'), 'repo-selection.png')

    await page.getByRole('button', { name: /start publishing/i }).click()

    // Configure Hugging Face Hub
    await page.getByLabel('Repository name').fill('sierra-cazorla-camtraps')
    await page.getByLabel('HuggingFace Hub token').fill('hf_ExAmPle1234567890abcdefghijklmno')
    await page.getByRole('button', { name: /test token/i }).click()
    await page.getByText('Connected as wildintel.').waitFor()
    await shot(page.locator('main > div'), 'hfh-configure.png')
    await page.getByRole('button', { name: /^continue$/i }).click()

    // Configure Zenodo
    await page.getByLabel('Communities').fill('wildintel, camera-traps')
    await page.getByLabel('Zenodo token').fill('zen_ExAmPle1234567890abcdefghijklmno')
    await page.getByRole('button', { name: /test token/i }).click()
    await page.getByText('Token verified.').waitFor()
    await shot(page.locator('main > div'), 'zenodo-configure.png')
    await page.getByRole('button', { name: /^continue$/i }).click()

    // Configure B2SHARE
    await page.getByLabel('Community UUID').fill('b2c1e6b0-79ad-4d97-a4a1-2b0e9a6f1a11')
    await page.getByLabel('B2SHARE token').fill('b2s_ExAmPle1234567890abcdefghijklmno')
    await page.getByRole('button', { name: /test token/i }).click()
    await page.getByText('Token verified.').waitFor()
    await shot(page.locator('main > div'), 'b2share-configure.png')
    await page.getByRole('button', { name: /^continue$/i }).click()

    // Configure GBIF — Archive URL is already prefilled from HFH's repo_id.
    await page.getByLabel('Publishing organization UUID').fill('0a16da09-7719-40de-8d4f-56a15ed52fb6')
    await page.getByLabel('Installation UUID').fill('92d76df5-3de1-4c89-be03-7a17abad962a')
    await page.getByLabel('GBIF username').fill('ws_client_demo')
    await page.getByLabel('GBIF password').fill('Demo123')
    await page.getByRole('button', { name: /test credentials/i }).click()
    await page.getByText('Credentials verified.').waitFor()
    await shot(page.locator('main > div'), 'gbif-configure.png')
    await page.getByRole('button', { name: /^continue$/i }).click()

    // Primary DOI choice (hfh + zenodo + b2share all selected)
    await page.getByText('Which DOI should Hugging Face Hub cite as primary?').waitFor()
    await shot(page.locator('main > div'), 'primary-doi-choice.png')
    await page.getByRole('radio', { name: /^zenodo$/i }).click()

    // Confirm, publish, and land on "All done!"
    await page.getByRole('button', { name: /start publishing now/i }).click()
    await page.getByText('All done!').waitFor()
    await shot(page.locator('main > div'), 'all-done.png')

    // Sync DOI to Hugging Face Hub (Zenodo) — both this section and
    // B2SHARE's own sync section are on screen at once (both were
    // published), so every locator below is scoped to its own <h5> heading's
    // container to avoid matching the other section's identical field labels.
    const zenodoSync = page.getByRole('heading', { name: 'Sync DOI to Hugging Face Hub' }).locator('xpath=..')
    await zenodoSync.getByLabel('Repository name').fill('sierra-cazorla-camtraps')
    await zenodoSync.getByLabel('HuggingFace Hub token').fill('hf_ExAmPle1234567890abcdefghijklmno')
    await shot(zenodoSync, 'zenodo-sync-doi-form.png')
    await zenodoSync.getByRole('button', { name: /^sync doi$/i }).click()
    const zenodoSynced = page.getByText('DOI synced to').locator('xpath=..')
    await zenodoSynced.waitFor()
    await shot(zenodoSynced, 'zenodo-sync-doi-done.png')

    // Sync PID/DOI to Hugging Face Hub (B2SHARE)
    const b2shareSync = page.getByRole('heading', { name: 'Sync PID/DOI to Hugging Face Hub' }).locator('xpath=..')
    await b2shareSync.getByLabel('Repository name').fill('sierra-cazorla-camtraps')
    await b2shareSync.getByLabel('HuggingFace Hub token').fill('hf_ExAmPle1234567890abcdefghijklmno')
    await shot(b2shareSync, 'b2share-sync-pid-form.png')
    await b2shareSync.getByRole('button', { name: /^sync pid\/doi$/i }).click()
    const b2shareSynced = page.getByText('PID/DOI synced to').locator('xpath=..')
    await b2shareSynced.waitFor()
    await shot(b2shareSynced, 'b2share-sync-pid-done.png')

    await browser.close()
    console.log(`\nDone — screenshots written to ${OUT_DIR}`)
  } finally {
    vite.kill()
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
