// 자막·배지를 투명 PNG로 렌더한다.
//
// 왜 Chrome으로 그리나: 이 ffmpeg 빌드에는 drawtext도 subtitles도 없다(빌드
// 옵션 17개짜리 슬림 빌드). 한글 자막을 넣을 방법이 overlay 필터밖에 없어서,
// 이미 CDP로 몰고 있는 Chrome에 그려 알파 PNG로 뽑는다. 폰트·자간·굵기를
// CSS로 통제할 수 있어 결과가 오히려 낫다.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { attach, evaluate, sleep } from './cdp.mjs';
import { WORK, ensureChrome } from './session.mjs';

const OUTDIR = join(WORK, 'overlays');
mkdirSync(OUTDIR, { recursive: true });

const W = 1920;

/** 자막 한 줄(또는 두 줄) — 화면 아래쪽에 앉는 띠. */
const subtitleHtml = (text, kind) => `
<style>
  html,body { margin:0; background:transparent; }
  .wrap { width:${W}px; height:260px; display:flex; align-items:flex-end;
          justify-content:center; padding-bottom:44px; }
  .sub { max-width:1500px; text-align:center;
         font-family:"Apple SD Gothic Neo","AppleSDGothicNeo-Bold",sans-serif;
         font-weight:700; font-size:46px; line-height:1.34; letter-spacing:-0.012em;
         color:#fff; padding:18px 34px; border-radius:14px;
         background:rgba(10,14,20,.80);
         box-shadow:0 10px 40px rgba(0,0,0,.45);
         -webkit-font-smoothing:antialiased; }
  /* 결정론 경로와 LLM 경로를 색으로 가른다 — "LLM을 쓰되 통제한다"는
     차별점은 화면만으로는 안 보여서 자막이 그 역할을 한다. */
  .sub.det { border-left:9px solid #3fb950; }
  .sub.llm { border-left:9px solid #a371f7; }
  .sub.live{ border-left:9px solid #f0883e; }
</style>
<div class="wrap"><div class="sub ${kind}">${text}</div></div>`;

/** 화면 우상단 상시 배지 — "이거 진짜예요?"의 여지를 없애는 장치. */
const badgeHtml = (text, tone) => `
<style>
  html,body { margin:0; background:transparent; }
  .wrap { width:${W}px; height:130px; display:flex; justify-content:flex-end;
          align-items:flex-start; padding:34px 44px 0 0; }
  .badge { font-family:"Apple SD Gothic Neo",-apple-system,sans-serif;
           font-weight:800; font-size:23px; letter-spacing:.10em;
           padding:13px 24px; border-radius:999px;
           -webkit-font-smoothing:antialiased; }
  .demo { color:#ffd77a; background:rgba(60,44,8,.92); border:2px solid #d29922; }
  .live { color:#c6f7d0; background:rgba(9,48,24,.92); border:2px solid #3fb950; }
</style>
<div class="wrap"><span class="badge ${tone}">${text}</span></div>`;

await ensureChrome();
const page = await attach();

async function shot(html, height, file) {
  await page.send('Emulation.setDeviceMetricsOverride', {
    width: W, height, deviceScaleFactor: 1, mobile: false,
  });
  await page.send('Emulation.setDefaultBackgroundColorOverride', {
    color: { r: 0, g: 0, b: 0, a: 0 },
  });
  await evaluate(page, `document.open(), document.write(${JSON.stringify(html)}), document.close(), true`);
  await sleep(320);
  const { data } = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  writeFileSync(join(OUTDIR, file), Buffer.from(data, 'base64'));
  console.log('  ', file);
}

export async function renderAll(items) {
  for (const it of items) {
    if (it.type === 'badge') await shot(badgeHtml(it.text, it.tone), 130, `${it.id}.png`);
    else await shot(subtitleHtml(it.text, it.kind ?? ''), 260, `${it.id}.png`);
  }
  // 오버라이드를 풀어 놓지 않으면 다음 촬영에서 창 크기가 어긋난다.
  await page.send('Emulation.clearDeviceMetricsOverride');
  await page.send('Emulation.setDefaultBackgroundColorOverride');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const items = JSON.parse(process.argv[2] ?? '[]');
  await renderAll(items);
  process.exit(0);
}
