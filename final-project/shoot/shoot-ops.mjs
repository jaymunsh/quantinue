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

/** 운영 기준 화면의 "최근 폴링 시도" 값. 살아 있다는 증거의 실체다. */
const pollStamp = () => evaluate(page, `
  (() => {
    const dl = document.querySelector('.runtime-status .equity-facts');
    if (!dl) return null;
    const dts = [...dl.querySelectorAll('dt')];
    const dt = dts.find((el) => el.textContent.trim() === '최근 폴링 시도');
    return dt ? dt.nextElementSibling.textContent.trim() : null;
  })()
`);

const dir = join(WORK, 'frames-s6');
const rec = startCapture(page, dir, { fps: 25, quality: 84 });

await slowScrollTo(page, 0, 300);
await sleep(6000);                                            // 실운영 헤더·일일 리포트
await slowScrollToSelector(page, '#report', { durationMs: 1600, offset: 110 });
await sleep(6500);
await slowScrollToSelector(page, '#chain', { durationMs: 2200, offset: 110 });
await sleep(6500);                                            // 오늘 잡 체인
await slowScrollToSelector(page, '#ledger', { durationMs: 2800, offset: 110 });
await sleep(6000);                                            // 계좌 총람 — 실계좌

// 운영 기준 화면. 관제실의 #watch는 재판단이 꺼져 있어(config `rejudge.enabled:
// false`) 장중에도 비어 있다 — 그 화면으로는 "지금 돌고 있다"를 못 보인다.
// 대신 여기 "최근 폴링 시도"는 1분마다 갱신되므로, **끝에 다시 들러 같은 칸이
// 다른 시각을 가리키는 것**을 한 테이크 안에 담는다. 그게 이 샷의 증거다.
await navigate(page, `${BASE}/admin/schedule`, 1800);
const pollBefore = await pollStamp();
const stampReadAt = Date.now();
await sleep(9000);                                            // 감시 ready · 폴링 시각
await slowScrollToSelector(page, '#jobs', { durationMs: 2400, offset: 110 });
await sleep(9000);                                            // 잡 14종 · 마지막 성공 · 다음 예정
// 표를 끝까지 훑는 데 시간을 쓴다. 폴링 주기가 60초라 어차피 기다려야 하는데,
// 빈 화면으로 버티면 편집에서 통째로 버리는 구간이 된다.
await slowScrollToSelector(page, '#glossary', { durationMs: 14000, offset: 110 });
await sleep(9000);

// 폴링이 한 번 더 돌 때까지 채운 뒤 **한 번만** 새로고침한다. 6초마다
// 다시 부르면 녹화본이 깜빡임투성이가 된다 — 증거 한 컷이 목적이지
// 폴링 자체를 보여주려는 게 아니다.
const elapsed = Date.now() - stampReadAt;
if (elapsed < 64000) await sleep(64000 - elapsed);
await navigate(page, `${BASE}/admin/schedule`, 1500);
const pollAfter = await pollStamp();
await sleep(9000);                                            // 갱신된 폴링 시각
console.log(`폴링 시각 ${pollBefore} → ${pollAfter}`
  + (pollAfter !== pollBefore ? ' · 갱신 확인' : ' · ⚠️ 갱신 못 봄'));

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
