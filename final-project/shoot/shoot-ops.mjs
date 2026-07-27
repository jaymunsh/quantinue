// S6 촬영: 운영 8020 실증거 (정규장 개장 후).
//
// **읽기 전용 엄수.** 이 스크립트가 운영에 보내는 요청은 GET과 로그인 POST
// 하나뿐이다. 폼 제출·버튼 클릭·날짜 변경은 일절 하지 않는다 — 관제실
// 화면에는 실행 버튼이 섞여 있어서, 스크롤만 하고 클릭은 안 한다는 것이
// 이 파일의 계약이다.
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { attach, evaluate, navigate, slowScrollTo, slowScrollToSelector, sleep } from './cdp.mjs';
import { startCapture, writeConcatList } from './capture.mjs';
import { FOOTAGE, WORK, ensureChrome, login, setViewport } from './session.mjs';

const BASE = 'http://127.0.0.1:8020';
const USER = 'admin';
const PASS = 'quantinue-admin';
// 기본은 본 테이크. 개장 전 예비 테이크는 S6_DEST로 파일명을 갈아 끼운다.
const DEST = process.env.S6_DEST
  ?? join(FOOTAGE, 's6-live-ops.mp4');

await ensureChrome();
const page = await attach();
await setViewport(page);

await navigate(page, `${BASE}/login`, 1200);
if (await evaluate(page, '!!document.querySelector(\'input[name="login_id"]\')')) {
  await evaluate(page, `
    (() => { const f = document.querySelector('form[action="/login"]');
      f.querySelector('[name=login_id]').value = ${JSON.stringify(USER)};
      f.querySelector('[name=password]').value = ${JSON.stringify(PASS)};
      f.submit(); return true; })()
  `);
  await sleep(2500);
}
await navigate(page, `${BASE}/admin`, 2000);
const where = await evaluate(page, 'location.pathname');
if (where !== '/admin') throw new Error(`운영 관제실에 못 들어감: ${where}`);
console.log('운영 관제실 진입 ·', await evaluate(page, 'document.title'));

const dir = join(WORK, 'frames-s6');
const rec = startCapture(page, dir, { fps: 25, quality: 84 });

await slowScrollTo(page, 0, 300);
await sleep(6000);                                            // 실운영 헤더·일일 리포트
await slowScrollToSelector(page, '#report', { durationMs: 1600, offset: 110 });
await sleep(6500);
await slowScrollToSelector(page, '#watch', { durationMs: 2200, offset: 110 });
await sleep(7000);                                            // 장중 감시 — 실시세가 도는 자리
await slowScrollToSelector(page, '#chain', { durationMs: 2200, offset: 110 });
await sleep(6500);                                            // 오늘 잡 체인
await slowScrollToSelector(page, '#protection', { durationMs: 2500, offset: 110 });
await sleep(5000);
await slowScrollToSelector(page, '#ledger', { durationMs: 2800, offset: 110 });
await sleep(6000);                                            // 계좌 총람 — 실계좌

const { frames, dropped } = await rec.stop();
const span = frames[frames.length - 1].at / 1000;
console.log(`프레임 ${frames.length} · ${span.toFixed(1)}s · ${(frames.length / span).toFixed(1)}fps · 실패 ${dropped}`);

const list = writeConcatList(dir, frames, join(WORK, 'frames-s6.txt'));
execFileSync('ffmpeg', [
  '-hide_banner', '-loglevel', 'error', '-y',
  '-f', 'concat', '-safe', '0', '-i', list,
  '-vsync', 'cfr', '-r', '30',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
  '-pix_fmt', 'yuv420p', '-movflags', '+faststart', DEST,
], { stdio: 'inherit' });
console.log('S6:', DEST);
process.exit(0);
