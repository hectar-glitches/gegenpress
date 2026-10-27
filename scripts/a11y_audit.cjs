#!/usr/bin/env node
/* Automated accessibility audit of the console, with axe-core, in the
   states a fan actually sees -- not just the page as it loads.

     npm install --no-save axe-core playwright   (or have them available)
     node scripts/a11y_audit.cjs                 # prints JSON, exits 1 on any violation

   Rules: WCAG 2.0/2.1/2.2 A and AA as axe-core tags them. Automated tools
   catch a subset of WCAG failures -- they cannot judge whether a caption
   is useful or a voice is intelligible -- so a clean run is a floor, not
   a certificate. The canvas pitch is one image to axe; what it shows is
   carried to assistive technology by the audio description and the
   live region instead. */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const ROOT = path.resolve(__dirname, '..', 'docs');
const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json',
  '.woff2': 'font/woff2', '.mp3': 'audio/mpeg' };

const STATES = [
  ['opening frame', async p => {}],
  ['accessibility panel open', async p => { await p.click('#accBtn'); await p.waitForTimeout(600); }],
  ['Call it question', async p => {
    await p.evaluate(() => { clock = 44 * 60 + 58; sync(); play(); });
    await p.waitForTimeout(2500);
    await p.evaluate(() => pause());
  }],
  ['Try it panel open', async p => { await p.click('#try'); await p.waitForTimeout(600); }],
  ['fan mode', async p => { await p.click('#mFan'); await p.waitForTimeout(400); }],
  ['Arabic, larger text', async p => {
    await p.evaluate(() => { ACC.large = true; applyAcc(); setLang('ar'); });
    await p.waitForTimeout(400);
  }],
];

(async () => {
  const srv = http.createServer((q, r) => {
    let p = decodeURIComponent(q.url.split('?')[0]); if (p === '/') p = '/index.html';
    const f = path.join(ROOT, p);
    if (!f.startsWith(ROOT) || !fs.existsSync(f)) { r.writeHead(404); return r.end(); }
    r.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
    fs.createReadStream(f).pipe(r);
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await chromium.launch();
  const out = [];
  for (const [name, setup] of STATES) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    await setup(page);
    await page.addScriptTag({ content: AXE });
    const res = await page.evaluate(() => axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] },
    }));
    out.push({ state: name, passes: res.passes.length, violations: res.violations.map(v => ({
      id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
      targets: v.nodes.slice(0, 4).map(n => n.target.join(' ')),
    })) });
    await page.close();
  }
  await browser.close(); srv.close();
  console.log(JSON.stringify(out, null, 1));
  process.exit(out.some(s => s.violations.length) ? 1 : 0);
})();
