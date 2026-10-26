// Real UI screenshots for docs/images/*.png.
//
// Everything here is synthetic: the app is built with placeholder env values,
// served by `vite preview`, and every network call (backend API and Supabase)
// is answered by Playwright route mocks. No real account, CV or job is used.
//
// Usage (from frontend/):  node scripts/screenshots.mjs [outDir]
import { chromium } from 'playwright';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const outDir = path.resolve(process.argv[2] || path.join(process.cwd(), '../docs/images'));
const distDir = path.resolve(process.cwd(), 'dist-screenshots');
const port = 4179;
const origin = `http://127.0.0.1:${port}`;
const API = 'https://api.screenshots.invalid';
const SUPA = 'https://screenshots.invalid';

fs.mkdirSync(outDir, { recursive: true });

// 1. Build against placeholder env values (never the real .env.local).
const build = spawnSync('npx', ['vite', 'build', '--outDir', distDir, '--emptyOutDir'], {
  stdio: 'inherit',
  env: { ...process.env, VITE_API_URL: API, VITE_SUPABASE_URL: SUPA, VITE_SUPABASE_ANON_KEY: 'screenshots-anon-key' },
});
if (build.status !== 0) process.exit(build.status || 1);

const server = spawn('npx', ['vite', 'preview', '--outDir', distDir, '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { stdio: 'ignore' });
async function waitForServer() {
  for (let i = 0; i < 60; i += 1) {
    try { const r = await fetch(origin); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('preview server did not start');
}

// 2. Synthetic fixtures.
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const fakeJwt = `${b64({ alg: 'none' })}.${b64({ sub: 'user-1', exp: 4102444800, role: 'authenticated' })}.sig`;
const fakeSession = {
  access_token: fakeJwt, refresh_token: 'refresh-synthetic', token_type: 'bearer', expires_in: 3600 * 24 * 365, expires_at: 4102444800,
  user: { id: 'user-1', aud: 'authenticated', role: 'authenticated', email: 'alex.example@example.com', app_metadata: {}, user_metadata: { full_name: 'Alex Example' }, created_at: '2026-01-01T00:00:00Z' },
};
const SESSION_ROW = { id: 'sess-1', title: 'Backend Engineer at Northwind', updated_at: '2026-10-23T10:00:00Z' };
const MATCH = {
  intent: 'match_job',
  match: { score: 78, label: 'Strong match', matched_skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker'], missing_skills: ['Kubernetes', 'Terraform'], reasons: ['4 of 6 required skills appear in your CV', 'Your backend experience is recent and relevant'] },
  job: { title: 'Backend Engineer', company: 'Northwind Labs', source_host: 'jobs.northwind.example' },
  input: { kind: 'job_url', job_ingest_status: 'ok', used_session_job: false },
};
const DOC = {
  intent: 'tailor_cv',
  document: { type: 'cv', template_id: 'modern-two-column', content: 'ALEX EXAMPLE\nBackend Engineer\n\nSUMMARY\nBackend engineer with five years of experience building Python and FastAPI services on PostgreSQL.\n\nEXPERIENCE\nExample Corp, Backend Engineer (2021-2026)\n- Built REST APIs serving 2M requests per day\n- Reduced report latency by 40% with query tuning\n\nSKILLS\nPython, FastAPI, PostgreSQL, Docker' },
  grounding: { removed: 1 },
  gaps: ['Add a measurable result for your last role'],
  input: { kind: 'job_text', job_ingest_status: 'ok', used_session_job: true },
};
const CLARIFY = { intent: 'clarify', missing: ['job'], job_ingest_status: 'login_wall', input: { kind: 'job_url', job_ingest_status: 'login_wall', used_session_job: false } };

function reply(content, structured) {
  return { session: SESSION_ROW, message: { id: `a-${Math.random().toString(36).slice(2)}`, role: 'assistant', content, structured, created_at: '2026-10-23T10:00:05Z' } };
}

async function openApp(browser, { width, height, theme = 'light', locale = 'en' }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  await ctx.addInitScript(({ theme: th, locale: loc, session }) => {
    try {
      localStorage.setItem('aca-theme', th);
      localStorage.setItem('aca-locale', loc);
      localStorage.setItem('sb-screenshots-auth-token', JSON.stringify(session));
    } catch { /* ignore */ }
  }, { theme, locale, session: fakeSession });
  const page = await ctx.newPage();
  await page.route(`${SUPA}/**`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }));
  // The app reloads the session transcript after the first reply, so the mock keeps it.
  const transcript = [];
  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(body) });
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } });
    if (url.pathname.endsWith('/chat/completions')) {
      const body = JSON.parse(req.postData() || '{}');
      const text = String(body.message || '').toLowerCase();
      let out;
      if (text.includes('tailor')) out = reply('I tailored your CV to this role. Review it, edit anything, then download.', DOC);
      else if (text.includes('login')) out = reply('I could not open that link.', CLARIFY);
      else out = reply('Here is how your CV compares with this job.', MATCH);
      transcript.push({ id: `u-${transcript.length}`, role: 'user', content: body.message, created_at: '2026-10-23T10:00:00Z' }, out.message);
      return json(out);
    }
    if (url.pathname.endsWith('/chat/sessions')) return json({ items: [] });
    if (url.pathname.includes('/chat/sessions/')) return json({ ...SESSION_ROW, messages: transcript });
    if (url.pathname.endsWith('/models')) return json({ items: [], models: [] });
    return json({ items: [] });
  });
  await page.goto(origin);
  await page.getByPlaceholder(/Ask anything about your career/).waitFor({ timeout: 15000 });
  return { ctx, page };
}

async function send(page, text) {
  const box = page.getByPlaceholder(/Ask anything about your career/);
  await box.fill(text);
  await box.press('Enter');
}

const shot = (page, name) => page.screenshot({ path: path.join(outDir, name) });

try {
  await waitForServer();
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});

  // Laptop, light: ask for a match (job link) and show the match card.
  {
    const { ctx, page } = await openApp(browser, { width: 1440, height: 900 });
    await send(page, 'Does my CV match this job? https://jobs.northwind.example/backend-engineer');
    await page.getByText('Matched skills').waitFor();
    await shot(page, 'in-laptop-chat.png');

    // Same conversation continues: tailor the CV, show the editable document preview.
    await page.getByRole('button', { name: 'Tailor my CV' }).click();
    await page.getByRole('button', { name: 'Download' }).waitFor();
    await shot(page, 'final-laptop.png');
    await ctx.close();
  }

  // Combo: link that cannot be read -> clarify card with the right explanation, then match.
  {
    const { ctx, page } = await openApp(browser, { width: 1440, height: 1300 });
    await send(page, 'Please match this login protected link https://private.example/job/1');
    await page.getByText(/login required/).waitFor();
    await send(page, 'Does my CV match this job? https://jobs.northwind.example/backend-engineer');
    await page.getByText('Matched skills').waitFor();
    await shot(page, 'combo-chat.png');
    await ctx.close();
  }

  // Dark theme.
  {
    const { ctx, page } = await openApp(browser, { width: 1440, height: 900, theme: 'dark' });
    await send(page, 'Does my CV match this job? https://jobs.northwind.example/backend-engineer');
    await page.getByText('Matched skills').waitFor();
    await shot(page, 'combo-dark.png');
    await ctx.close();
  }

  // Mobile.
  {
    const { ctx, page } = await openApp(browser, { width: 390, height: 844 });
    await send(page, 'Does my CV match this job? https://jobs.northwind.example/backend-engineer');
    await page.getByText('Matched skills').waitFor();
    await shot(page, 'combo-mobile.png');
    await ctx.close();
  }

  await browser.close();
  console.log(`screenshots written to ${outDir}`);
} finally {
  server.kill();
  fs.rmSync(distDir, { recursive: true, force: true });
}
