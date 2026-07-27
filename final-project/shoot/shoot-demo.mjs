// 본 촬영 드라이버 — `presentation-plan.md` §4-2 샷 리스트 A~H.
//
// 설계 이유 세 가지:
//  1) **마스터 연속 녹화 + 마크**. 각본이 시간축을 타므로(사건 ~1분, 방어선 ~4분)
//     장면마다 녹화를 끊었다 붙이면 한 번 놓친 순간을 되돌릴 수 없다. 통으로
//     찍고 마크를 남겨 나중에 잘라낸다.
//  2) **시간이 아니라 원장을 기다린다**. "1분쯤"에 카메라를 들이대는 대신
//     화면에 그 종목이 실제로 나타날 때까지 폴링한다. 각본 타이밍이 몇십 초
//     흔들려도 장면이 비지 않는다.
//  3) **계정이 다른 두 페이지를 한 테이크 안에서 오간다**(관제실 admin ↔
//     `/me` demo). 쿠키가 갈리도록 브라우저 컨텍스트를 따로 쓴다
//     (`cdp.mjs::openIsolatedPage`).
//
// 이 각본이 증명하는 한 문장(§4-0):
//   "손절선은 살 때 이미 정해져 있었고, 1분마다 도는 감시가 AI를 부르지 않고
//    그 선을 정확히 지켰다."
// 그래서 이 파일에서 **가장 중요한 두 샷은 B와 D다.**
//   B — 살 때부터 `/me`에 적혀 있는 자동 청산 손절 $139.50 (사전 약속)
//   D — 방어선 발동이 1건 → 2건으로 **자라는 순간** (사건이 일어나는 것)
// 나머지 샷은 이 둘을 감싸는 맥락이다. 시간이 모자라면 나머지를 줄인다.
//
// 각본 티커가 어느 패널에 뜨는지는 실측으로 확정했다(추정 금지):
//   NVEX → #allocation(집행된 매수)  ·  HLXM/VRDN → #protection(방어선 발동)
// "판단과 반박"(#judgements)은 cycle_ts=자정인 일일 슬롯만 그린다 — 장중
// 재판단을 일부러 뺀 불변식이라(관제실 숫자 = 잡 원장 숫자) 각본 티커는
// 거기 안 뜬다. 그래서 "근거가 남는다"는 주장은 이어받은 실제 운영 판단
// 카드로 보여주고, 각본 사건은 원장에 남은 결과로 보여준다.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  attach, evaluate, navigate, openIsolatedPage,
  slowScrollTo, slowScrollToSelector, sleep,
} from './cdp.mjs';
import { startCapture, writeConcatList } from './capture.mjs';
import { WORK, ensureChrome, login, setViewport } from './session.mjs';

const BASE = process.env.SHOOT_BASE ?? 'http://127.0.0.1:8022';
const OUT = process.env.SHOOT_OUT ?? 'master.mp4';
const USER = process.env.SHOOT_USER ?? 'admin';
const PASS = process.env.SHOOT_PASS ?? 'quantinue-admin';
const ME_USER = process.env.SHOOT_ME_USER ?? 'demo';
const ME_PASS = process.env.SHOOT_ME_PASS ?? 'qn-demo-user';
const FRAMEDIR = join(WORK, 'frames');

await ensureChrome();
// 브라우저에 붙기만 하고, 찍을 페이지는 **둘 다 새로 만든다.**
// `attach()`가 잡는 "첫 페이지 타깃"은 이전 실행이 남긴 페이지일 수 있다.
// 실제로 그 남은 페이지(로그인 안 된 컨텍스트)를 잡아 404 화면을 1분 넘게
// 녹화한 적이 있다. 컨텍스트를 직접 만들면 그런 상속이 원리적으로 없다.
const anchor = await attach();
const admin = await openIsolatedPage(anchor.browser, 'about:blank');
await setViewport(admin);

// `/me`는 demo 계정이다. 같은 오리진이라 컨텍스트를 갈라야 두 세션이 동시에 산다.
const me = await openIsolatedPage(anchor.browser, 'about:blank');
await setViewport(me);

// 지금 녹화가 찍을 페이지. 캡처 루프가 매 프레임 이걸 읽는다.
let shown = admin;
const show = (page) => { shown = page; };

const marks = [];
let t0 = 0;
const now = () => Date.now() - t0;
const mark = (scene, phase) => {
  const at = now();
  marks.push({ scene, phase, at });
  console.log(`[${(at / 1000).toFixed(1).padStart(6)}s] ${scene} ${phase}`);
};

/** 관제실을 다시 읽어온다 — 원장이 갱신됐는지 보는 유일한 방법. */
async function reloadAdmin(settle = 1500) {
  await navigate(admin, `${BASE}/admin`, settle);
}

/** 방어선 발동 배지의 건수. "1건 → 2건"이 샷 D의 증거다. */
async function protectionCount() {
  const text = await evaluate(admin, `
    (() => { const el = document.querySelector('#protection .panel__head .badge');
      return el ? el.textContent.trim() : null; })()
  `);
  if (!text) return null;
  const n = Number(text.replace(/[^0-9]/g, ''));
  return Number.isFinite(n) ? n : null;
}

/** 해당 섹션에 티커가 나타날 때까지 새로고침하며 기다린다. */
async function waitForTicker(section, ticker, { timeoutMs = 420000, everyMs = 12000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let tries = 0;
  while (Date.now() < deadline) {
    const found = await evaluate(admin, `
      (() => { const s = document.querySelector(${JSON.stringify(section)});
        return !!s && s.innerText.includes(${JSON.stringify(ticker)}); })()
    `);
    if (found) return true;
    tries += 1;
    if (tries % 2 === 0) console.log(`   … ${section} ${ticker} 대기 ${(now() / 1000).toFixed(0)}s`);
    await sleep(everyMs);
    await reloadAdmin(900);
  }
  return false;
}

/** 선택자 목록 중 텍스트에 ticker가 든 첫 요소로 천천히 이동. */
async function scrollToRow(containerSel, rowSel, ticker, { durationMs = 2200, offset = 240 } = {}) {
  const y = await evaluate(admin, `
    (() => {
      const rows = [...document.querySelectorAll(${JSON.stringify(`${containerSel} ${rowSel}`)})];
      const el = rows.find((n) => n.innerText.includes(${JSON.stringify(ticker)}));
      if (!el) return null;
      return el.getBoundingClientRect().top + window.scrollY - ${offset};
    })()
  `);
  if (y === null) return false;
  await slowScrollTo(admin, y, durationMs);
  return true;
}

/**
 * 크리틱이 실제로 반박한 판단 카드로 이동한다.
 * "AI를 쓰되 통제한다"는 주장을 화면으로 증명하는 유일한 자리라, 반박문이
 * 실제로 붙어 있는 카드를 골라야 한다 — 아무 카드나 잡으면 근거만 있고
 * 반박이 비어 그 주장이 화면에서 사라진다.
 */
async function scrollToJudgementWithObjection(skip = 0, durationMs = 2600) {
  const info = await evaluate(admin, `
    (() => {
      const items = [...document.querySelectorAll('#judgements .judgement-item')]
        .filter((n) => n.querySelector('.judgement-objection'));
      const el = items[${skip}];
      if (!el) return null;
      return {
        y: el.getBoundingClientRect().top + window.scrollY - 180,
        ticker: (el.querySelector('.judgement-ticker') || {}).textContent?.trim(),
        count: items.length,
      };
    })()
  `);
  if (!info) return null;
  await slowScrollTo(admin, info.y, durationMs);
  return info;
}

/**
 * 관제실이 **진짜로 그려졌는지** 본다.
 *
 * `location.pathname`으로 판정하면 안 된다 — 로그인 안 된 `/admin`은 404를
 * 주는데 경로는 그대로 `/admin`이다. 그 검사를 통과시켰다가 404 화면을
 * 1분 넘게 녹화한 적이 있다. 화면에 실제로 있어야 하는 패널을 묻는다.
 */
const adminReady = () => evaluate(admin, `!!document.querySelector('#protection')`);

console.log('관제실 로그인:', await login(admin, BASE, USER, PASS));
await reloadAdmin(1200);
if (!(await adminReady())) {
  throw new Error(`관제실이 안 떴다 — title="${await evaluate(admin, 'document.title')}" `
    + `path="${await evaluate(admin, 'location.pathname')}". 비밀번호(${USER})를 확인할 것.`);
}

// `/me`도 **녹화 전에** 로그인을 끝낸다. 로그인 화면은 한 프레임도 찍지 않는다.
console.log('/me 로그인:', await login(me, BASE, ME_USER, ME_PASS));
await navigate(me, `${BASE}/me`, 1500);
const meAccount = await evaluate(me, `
  (() => { const el = document.querySelector('#account');
    return el ? (el.innerText.match(/QUANTINUE-[A-Z0-9-]+/) || [null])[0] : null; })()
`);
console.log('/me 계좌:', meAccount);
if (!meAccount) throw new Error('/me에 계좌가 없다 — 로그인 실패로 본다');

// ── 녹화 시작 ────────────────────────────────────────────────────────────────
await reloadAdmin(1200);
const rec = startCapture(() => shown, FRAMEDIR, { fps: 25, quality: 84 });
await sleep(600);
t0 = Date.now();
mark('REC', 'start');

// 장면 도중 무엇이 터지든 녹화는 끝까지 마무리하고 마크를 남긴다.
// (앞 테이크는 스크롤 한 번이 멈춘 것 때문에 통째로 날아갔다)
try {

// ── A: 관제실 최상단 — 데모임을 먼저 밝힌다 ─────────────────────────────────
mark('A', 'in');
show(admin);
await slowScrollTo(admin, 0, 300);
await sleep(6000);                                       // 좌하단 LLM mock · Broker mock
await slowScrollToSelector(admin, '#report', { durationMs: 1500, offset: 110 });
await sleep(6000);                                       // 일일 리포트 헤더
mark('A', 'out');

// ── B: /me — 손절선이 **살 때 이미** 적혀 있다 (영상의 축) ──────────────────
// 리셋 +4분이면 VRDN이 청산돼 보유 목록에서 사라진다. 그래서 이 샷을 앞에 둔다.
mark('B', 'in');
show(me);
await navigate(me, `${BASE}/me`, 1500);
await slowScrollTo(me, 0, 300);
await sleep(5000);                                       // QUANTINUE-DEMO-01 · 총자산
await slowScrollToSelector(me, '#holdings', { durationMs: 2000, offset: 110 });
await sleep(4000);
const vrdnHeld = await evaluate(me, `
  (() => { const t = document.querySelector('#holdings');
    return !!t && t.innerText.includes('VRDN'); })()
`);
mark('B', vrdnHeld ? 'vrdn-held' : 'vrdn-missing');
if (vrdnHeld) {
  // 보유 행 자체로 이동한다 — "자동 청산 손절 $139.50"이 프레임 한가운데 와야 한다.
  const y = await evaluate(me, `
    (() => {
      const row = [...document.querySelectorAll('#holdings tr')]
        .find((n) => n.innerText.includes('VRDN'));
      return row ? row.getBoundingClientRect().top + window.scrollY - 320 : null;
    })()
  `);
  if (y !== null) await slowScrollTo(me, y, 1800);
  await sleep(11000);                                    // 손절 $139.50 · 익절 $172.50
}
// §4-6.4: 데모의 SPY 비교·계좌 곡선은 비어 있다. 보유 종목 표까지만 잡는다.
mark('B', 'out');

// ── C: 방어선 1건 — VRDN은 **아직 없다** (D의 대조군) ───────────────────────
mark('C', 'in');
show(admin);
await reloadAdmin(1200);
await slowScrollToSelector(admin, '#protection', { durationMs: 2200, offset: 110 });
const before = await protectionCount();
mark('C', `count-${before}`);
await sleep(9000);                                       // 배지 "1건" · HLXM만
mark('C', 'out');

// ── F: NVEX 호재 매수 — 배분(집행된 매수)에 남는다 ──────────────────────────
mark('F', 'wait');
const nvex = await waitForTicker('#allocation', 'NVEX', { timeoutMs: 120000, everyMs: 8000 });
mark('F', nvex ? 'in' : 'missing');
if (nvex) {
  await slowScrollToSelector(admin, '#allocation', { durationMs: 2500, offset: 110 });
  await sleep(2500);
  await scrollToRow('#allocation', 'tr', 'NVEX', { durationMs: 1800, offset: 300 });
  await sleep(6500);                                     // 1090주 @ $55.00
  mark('F', 'out');
}

// ── G: HLXM 악재 반전 매도 — 방어선 "판단 반전" ─────────────────────────────
mark('G', 'wait');
const hlxm = await waitForTicker('#protection', 'HLXM', { timeoutMs: 120000, everyMs: 8000 });
mark('G', hlxm ? 'in' : 'missing');
if (hlxm) {
  await slowScrollToSelector(admin, '#protection', { durationMs: 2200, offset: 110 });
  await sleep(2000);
  await scrollToRow('#protection', '.event-record', 'HLXM', { durationMs: 1800, offset: 300 });
  await sleep(6500);                                     // 200주 @ $80.00 · 판단 반전
  mark('G', 'out');
}

// ── H: 판단과 반박 — 근거가 남는다는 주장의 증거 ────────────────────────────
// (각본 사건이 아니라 이어받은 실제 운영 판단이다. 손절 대기 시간을 여기 쓴다)
mark('H', 'in');
await slowScrollToSelector(admin, '#judgements', { durationMs: 3000, offset: 110 });
await sleep(3500);
for (const i of [0, 1, 2]) {
  const info = await scrollToJudgementWithObjection(i, 2400);
  if (!info) break;
  if (i === 0) console.log(`   반박 붙은 판단 ${info.count}건`);
  await sleep(6000);                                     // 근거·리스크·크리틱 반박
}
mark('H', 'out');

// ── D: 방어선이 1건 → 2건으로 **자라는 순간** (다시 못 찍는 샷) ─────────────
// 여기서만은 결과를 보여주지 않는다. 배지가 바뀌는 것을 화면에 담아야 한다.
// 그래서 다른 데로 가지 않고 #protection에 앉아 새로고침만 반복한다.
mark('D', 'wait');
const target = (before ?? 1) + 1;
let after = before;
const deadline = Date.now() + 420000;
while (Date.now() < deadline) {
  await reloadAdmin(900);
  await slowScrollToSelector(admin, '#protection', { durationMs: 700, offset: 110 });
  after = await protectionCount();
  if (after !== null && after >= target) break;
  await sleep(11000);                                    // 사람이 기다리는 속도로 재확인
}
const grew = after !== null && after >= target;
// 'seen'은 배지가 바뀐 것을 **확인한 순간**이다. 편집은 이 앞뒤로 자른다 —
// 기다린 몇 분을 통째로 넣으면 아무도 안 본다(cut.mjs의 lookback).
mark('D', grew ? 'seen' : 'missing');
console.log(`   방어선 배지 ${before}건 → ${after}건`);
if (grew) {
  await sleep(6000);                                     // 바뀐 배지를 읽을 시간
  await scrollToRow('#protection', '.event-record', 'VRDN', { durationMs: 1800, offset: 300 });
  await sleep(9000);                                     // 손절 $139.50 — B에서 본 그 숫자
  await slowScrollToSelector(admin, '#protection', { durationMs: 1800, offset: 110 });
  await sleep(5000);                                     // 패널 전체 — 2건이 된 모습
  mark('D', 'out');
}

// ── E: /me — 보유에서 VRDN이 사라지고, 거래 내역에 청산 근거가 남는다 ───────
// 거래 내역 문구가 이 영상의 결론을 대신 말해준다:
// "모델 판단 없이 손절·익절·기간 조건으로 체결됐습니다."
mark('E', 'in');
show(me);
await navigate(me, `${BASE}/me`, 1500);
await slowScrollToSelector(me, '#holdings', { durationMs: 2000, offset: 110 });
await sleep(7000);                                       // VRDN이 없는 보유 목록
await slowScrollToSelector(me, '#timeline', { durationMs: 2400, offset: 110 });
await sleep(4000);
const soldY = await evaluate(me, `
  (() => {
    const rows = [...document.querySelectorAll('#timeline li, #timeline .trade-item, #timeline article')];
    const el = rows.find((n) => n.innerText.includes('매도') && n.innerText.includes('VRDN'));
    return el ? el.getBoundingClientRect().top + window.scrollY - 300 : null;
  })()
`);
if (soldY !== null) await slowScrollTo(me, soldY, 1800);
await sleep(11000);                                      // 매도 VRDN $139.50 · 규칙에 따른 청산
mark('E', 'out');

} catch (err) {
  mark('ERROR', String(err && err.message ? err.message : err));
  console.error('장면 중 오류 — 지금까지 찍은 것은 살린다:', err);
} finally {
  mark('REC', 'stop');
  await sleep(1200);
  const { frames, dropped } = await rec.stop();
  const span = frames.length ? frames[frames.length - 1].at / 1000 : 0;
  console.log(`\n프레임 ${frames.length}장 · ${span.toFixed(1)}s · 실효 ${(frames.length / span).toFixed(1)}fps · 실패 ${dropped}`);

  // 도착 시각 그대로 인코딩한다(§capture.mjs) — 프레임률이 흔들려도 속도가 안 밀린다.
  const list = writeConcatList(FRAMEDIR, frames, join(WORK, 'frames.txt'));
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', list,
    '-vsync', 'cfr', '-r', '30',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', join(WORK, OUT),
  ], { stdio: 'inherit' });

  writeFileSync(join(WORK, 'marks.json'), JSON.stringify({ out: OUT, marks }, null, 2));
  console.log('마크 저장:', join(WORK, 'marks.json'));

  // 만든 컨텍스트는 치운다. 남겨두면 다음 실행의 `attach()`가 그걸 잡는다 —
  // 로그인 안 된 페이지를 잡아 404를 녹화한 사고가 정확히 그거였다.
  for (const p of [admin, me]) {
    try { await anchor.browser.send('Target.disposeBrowserContext', {
      browserContextId: p.browserContextId }); } catch { /* 이미 닫혔으면 그만 */ }
  }
}
process.exit(0);
