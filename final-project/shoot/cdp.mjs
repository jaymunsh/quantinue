// Chrome DevTools Protocol 드라이버 — npm 의존성 없이 node24 내장 WebSocket만 쓴다.
// 촬영용이라 "사람이 보는 속도"가 중요하다: 즉시 점프가 아니라 이징 스크롤로 움직인다.

const DEBUG_PORT = 9222;

export async function httpJson(path) {
  const res = await fetch(`http://127.0.0.1:${DEBUG_PORT}${path}`);
  return res.json();
}

class Conn {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.listeners = [];
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id !== undefined) {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(`${msg.error.message} (${JSON.stringify(msg.error)})`));
        else p.resolve(msg.result);
      } else {
        for (const l of this.listeners) l(msg);
      }
    });
  }

  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 30000);
    });
  }

  on(fn) { this.listeners.push(fn); }
  close() { this.ws.close(); }
}

export async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', () => reject(new Error(`WS open failed: ${wsUrl}`)), { once: true });
  });
  return new Conn(ws);
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 브라우저 타깃에 붙어 페이지 타깃 하나를 잡는다. */
export async function attach() {
  const version = await httpJson('/json/version');
  const browser = await connect(version.webSocketDebuggerUrl);
  const { targetInfos } = await browser.send('Target.getTargets');
  const pageTarget = targetInfos.find((t) => t.type === 'page');
  if (!pageTarget) throw new Error('no page target');
  const { sessionId } = await browser.send('Target.attachToTarget', {
    targetId: pageTarget.targetId, flatten: true,
  });
  const page = {
    browser,
    sessionId,
    targetId: pageTarget.targetId,
    send: (m, p) => browser.send(m, p, sessionId),
  };
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  return page;
}

export async function evaluate(page, expr, { awaitPromise = true } = {}) {
  const r = await page.send('Runtime.evaluate', {
    expression: expr, returnByValue: true, awaitPromise,
  });
  if (r.exceptionDetails) {
    throw new Error(`eval failed: ${r.exceptionDetails.text} :: ${r.exceptionDetails.exception?.description ?? ''}`);
  }
  return r.result.value;
}

export async function navigate(page, url, settleMs = 1200) {
  await page.send('Page.navigate', { url });
  // load 이벤트를 기다리는 대신 폴링한다 — 페이지 전환이 잦아 이벤트 경합이 생긴다.
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const ready = await evaluate(page, 'document.readyState');
      if (ready === 'complete') break;
    } catch { /* 전환 중 컨텍스트 파괴는 정상 */ }
    await sleep(150);
  }
  await sleep(settleMs);
}

/**
 * 이징 스크롤. 촬영본에서 눈이 따라갈 수 있도록 천천히 민다.
 * (브라우저 기본 smooth는 너무 빨라 판단 카드를 읽을 틈이 없다)
 *
 * 페이지 안에서 requestAnimationFrame으로 돌리지 **않는** 이유: 창이 가려지거나
 * 화면이 잠들면 Chrome이 rAF를 throttle해 콜백이 아예 안 온다. 그러면 스크롤을
 * 감싼 Promise가 영원히 안 풀려 촬영이 통째로 멈춘다(실제로 4분 대기 뒤 그렇게
 * 죽었다). 그래서 프레임 진행을 Node가 쥐고, 페이지에는 좌표만 던진다.
 */
export async function slowScrollTo(page, targetY, durationMs = 2500) {
  const start = await evaluate(page, 'window.scrollY');
  const end = await evaluate(page, `
    Math.max(0, Math.min(${targetY},
      document.documentElement.scrollHeight - window.innerHeight))
  `);
  if (Math.abs(end - start) < 2) return;

  const fps = 25;
  const steps = Math.max(2, Math.round((durationMs / 1000) * fps));
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
  const began = Date.now();
  for (let i = 1; i <= steps; i += 1) {
    const y = start + (end - start) * ease(i / steps);
    await evaluate(page, `window.scrollTo(0, ${y.toFixed(1)}), true`, { awaitPromise: false });
    const due = began + (durationMs * i) / steps;
    const wait = due - Date.now();
    if (wait > 0) await sleep(wait);
  }
}

/** 선택자로 요소 위치까지 천천히 스크롤. offset은 상단 여백. */
export async function slowScrollToSelector(page, selector, { durationMs = 2500, offset = 90 } = {}) {
  const y = await evaluate(page, `
    (() => { const el = document.querySelector(${JSON.stringify(selector)});
      return el ? el.getBoundingClientRect().top + window.scrollY - ${offset} : null; })()
  `);
  if (y === null) return false;
  await slowScrollTo(page, y, durationMs);
  return true;
}

export async function exists(page, selector) {
  return evaluate(page, `!!document.querySelector(${JSON.stringify(selector)})`);
}

export async function textOf(page, selector) {
  return evaluate(page, `
    (() => { const el = document.querySelector(${JSON.stringify(selector)});
      return el ? el.innerText.replace(/\\s+/g, ' ').trim() : null; })()
  `);
}
