// 페이지 직접 캡처 녹화기.
//
// 왜 화면 캡처를 버렸나: macOS 전체화면 창은 **자기 Space**로 들어간다.
// 화면 캡처는 "그 디스플레이에 지금 보이는 Space"를 찍기 때문에, 내 창이
// 자기 Space로 빠진 사이 캡처는 원래 데스크톱(메신저·개인 브라우저)을
// 찍고 있었다. 실제로 그렇게 개인 정보가 담긴 테이크가 나왔고 폐기했다.
//
// 렌더러에서 페이지를 직접 뜨면 창 겹침·Space·화면 잠금과 무관하고,
// 페이지 바깥은 **원리적으로** 프레임에 들어올 수 없다.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { sleep } from './cdp.mjs';

/**
 * 고정 목표 프레임률로 캡처하되, 실제 도착 시각을 함께 남긴다.
 * 인코딩은 이 시각을 그대로 써서 타이밍을 복원하므로, 중간에 프레임률이
 * 흔들려도 영상 속도가 밀리지 않는다.
 */
export function startCapture(page, dir, { fps = 25, quality = 84 } = {}) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  // page에 함수를 줄 수 있다. 한 테이크 안에서 계정이 다른 두 페이지를
  // 오가야 하는데(관제실 admin ↔ /me demo), 녹화를 끊으면 그 사이 각본
  // 시간축이 지나가버린다. 매 프레임 "지금 찍을 페이지"를 물어보면
  // 녹화는 끊기지 않고 화면만 갈린다.
  const targetOf = typeof page === 'function' ? page : () => page;

  const frames = [];
  let running = true;
  let dropped = 0;

  const loop = (async () => {
    const t0 = Date.now();
    let i = 0;
    while (running) {
      const due = t0 + (i * 1000) / fps;
      const wait = due - Date.now();
      if (wait > 0) await sleep(wait);
      if (!running) break;
      try {
        const { data } = await targetOf().send('Page.captureScreenshot', { format: 'jpeg', quality });
        const name = `f${String(frames.length).padStart(6, '0')}.jpg`;
        writeFileSync(join(dir, name), Buffer.from(data, 'base64'));
        frames.push({ name, at: Date.now() - t0 });
      } catch {
        dropped += 1;              // 페이지 전환 중 실패는 정상 — 다음 프레임으로 넘어간다
      }
      i += 1;
    }
    return { t0 };
  })();

  return {
    frames,
    async stop() {
      running = false;
      await loop;
      return { frames, dropped };
    },
  };
}

/** 프레임 + 도착 시각으로 concat 목록을 만들어 CFR 영상으로 굽는다. */
export function writeConcatList(dir, frames, listPath, tailMs = 400) {
  const lines = [];
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].at : f.at + tailMs;
    const dur = Math.max(0.008, (next - f.at) / 1000);
    lines.push(`file '${join(dir, f.name)}'`);
    lines.push(`duration ${dur.toFixed(4)}`);
  });
  // concat 데모서는 마지막 파일을 한 번 더 적어야 그 프레임이 실제로 나온다.
  if (frames.length) lines.push(`file '${join(dir, frames[frames.length - 1].name)}'`);
  writeFileSync(listPath, lines.join('\n'));
  return listPath;
}
