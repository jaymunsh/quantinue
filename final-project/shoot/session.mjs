// 촬영 세션 공통: 경로, headless Chrome 기동, 로그인, 뷰포트 고정.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evaluate, httpJson, navigate, sleep } from './cdp.mjs';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const FOOTAGE = join(HERE, '..', 'footage');
export const WORK = join(HERE, '.work');            // 프레임·중간물. 저장소에 넣지 않는다.
mkdirSync(FOOTAGE, { recursive: true });
mkdirSync(WORK, { recursive: true });

export const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export const PORT = 9222;

/**
 * headless Chrome을 띄운다(이미 떠 있으면 그대로 쓴다).
 *
 * headless인 것이 핵심이다. 화면 캡처로 찍던 초기 방식은 macOS 전체화면 창이
 * **자기 Space**로 들어가는 바람에, 캡처가 그 디스플레이에 실제로 보이던 다른
 * 화면(메신저 등)을 담았다. 렌더러에서 페이지를 직접 뜨면 창 겹침·Space·화면
 * 잠금과 무관하고, 페이지 바깥은 원리적으로 프레임에 들어올 수 없다.
 */
export async function ensureChrome() {
  try {
    await httpJson('/json/version');
    return 'already-running';
  } catch { /* 아래에서 띄운다 */ }

  const profile = join(WORK, 'chrome-profile');
  if (!existsSync(profile)) mkdirSync(profile, { recursive: true });
  const child = spawn(CHROME, [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', '--force-device-scale-factor=1',
    '--window-size=1920,1080', 'about:blank',
  ], { detached: true, stdio: 'ignore' });
  child.unref();

  for (let i = 0; i < 40; i += 1) {
    await sleep(500);
    try { await httpJson('/json/version'); return 'launched'; } catch { /* 기동 대기 */ }
  }
  throw new Error('headless Chrome이 뜨지 않았다');
}

/** 뷰포트를 1920x1080으로 못 박는다 — 창 크기·디스플레이와 무관하게 같은 조판. */
export async function setViewport(page, w = 1920, h = 1080, scale = 1) {
  await page.send('Emulation.setDeviceMetricsOverride', {
    width: w, height: h, deviceScaleFactor: scale, mobile: false,
  });
}

/** 로그인. 이미 세션이 살아 있으면 아무것도 하지 않는다. */
export async function login(page, base, user, pass) {
  await navigate(page, `${base}/login`, 1200);
  const hasForm = await evaluate(page, '!!document.querySelector(\'input[name="login_id"]\')');
  if (!hasForm) return 'already-logged-in';
  await evaluate(page, `
    (() => {
      const f = document.querySelector('form[action="/login"]');
      f.querySelector('[name=login_id]').value = ${JSON.stringify(user)};
      f.querySelector('[name=password]').value = ${JSON.stringify(pass)};
      f.submit();
      return true;
    })()
  `);
  await sleep(2500);
  return evaluate(page, 'location.pathname');
}
