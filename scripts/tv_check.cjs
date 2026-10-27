#!/usr/bin/env node
/* The TV output, checked the way a graphics system would load it: a
   1920x1080 page, transparent, driven by take/clear and by CasparCG's
   play()/stop()/next()/update(). Prints JSON; exits 1 on any failure.

     node scripts/tv_check.cjs        (needs playwright) */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..', 'docs');
const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.woff2': 'font/woff2' };
(async () => {
  const srv = http.createServer((q, r) => {
    let p = decodeURIComponent(q.url.split('?')[0]); if (p === '/') p = '/index.html';
    const f = path.join(ROOT, p);
    if (!f.startsWith(ROOT) || !fs.existsSync(f)) { r.writeHead(404); return r.end(); }
    r.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
    fs.createReadStream(f).pipe(r);
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(base + '?output=overlay', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const state = () => page.evaluate(() => {
    const l = document.querySelector('#lower'), r = l.getBoundingClientRect();
    return { onAir: l.classList.contains('up') && getComputedStyle(l).opacity === '1',
      box: [r.left, r.top, r.right, r.bottom].map(Math.round),
      background: getComputedStyle(document.body).backgroundColor,
      pitchHidden: getComputedStyle(document.querySelector('#cv')).display === 'none',
      player: document.querySelector('#lName').textContent, hero: document.querySelector('#lForm').textContent };
  });
  const out = { loaded: await state() };
  await page.keyboard.press('Enter'); await page.waitForTimeout(600); out.take = await state();
  await page.keyboard.press('ArrowRight'); await page.waitForTimeout(600); out.next = await state();
  await page.evaluate(() => update('{"lang":"fr","cue":1}')); await page.waitForTimeout(400); out.update = await state();
  await page.evaluate(() => stop()); await page.waitForTimeout(600); out.stop = await state();
  out.casparcg = await page.evaluate(() => ['play', 'stop', 'next', 'update'].every(f => typeof window[f] === 'function'));
  out.errors = errors;
  await browser.close(); srv.close();
  const t = out.take;
  out.ok = !out.loaded.onAir && t.onAir && !out.stop.onAir
    && out.loaded.background === 'rgba(0, 0, 0, 0)' && t.pitchHidden
    && t.box[0] >= 96 && t.box[2] <= 1824 && t.box[3] <= 1026 && t.box[1] >= 54
    && out.next.player !== t.player && out.update.hero === 'Le plus bas'
    && out.casparcg && !errors.length;
  console.log(JSON.stringify(out, null, 1));
  process.exit(out.ok ? 0 : 1);
})();
