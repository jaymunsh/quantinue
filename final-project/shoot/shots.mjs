// 슬라이드를 한 장씩 렌더해 PNG로 뽑는다 — 조판을 눈으로 검증하기 위해서.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { attach, evaluate, navigate, sleep } from './cdp.mjs';

import { WORK, ensureChrome } from './session.mjs';
const OUT = join(WORK, 'slideshots');
mkdirSync(OUT, { recursive: true });

await ensureChrome();
const page = await attach();
// 무대가 1600x900이므로 뷰포트를 딱 맞춰 scale(1)로 잡히게 한다.
await page.send('Emulation.setDeviceMetricsOverride', {
  width: 1640, height: 940, deviceScaleFactor: 1, mobile: false,
});
await navigate(page, `file://${join(WORK, '..', '..', 'slides', 'index.html')}`, 1200);

const n = await evaluate(page, 'document.querySelectorAll(".slide").length');
console.log('슬라이드', n, '장');

const only = process.argv[2] ? Number(process.argv[2]) : null;
for (let i = 0; i < n; i += 1) {
  await evaluate(page, `
    (() => { const s=[...document.querySelectorAll('.slide')];
      s.forEach((e,k)=>e.classList.toggle('on', k===${i})); return true; })()
  `);
  await sleep(320);
  if (only !== null && i !== only) continue;
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(OUT, `s${String(i + 1).padStart(2, '0')}.png`), Buffer.from(data, 'base64'));
}
console.log('저장:', OUT);
process.exit(0);
