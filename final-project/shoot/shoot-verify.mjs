// S5 촬영: 무결 검증 기록 화면.
// 마스터와 같은 방식(페이지 직접 캡처)이라 규격이 그대로 맞는다.
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { attach, slowScrollTo, sleep } from './cdp.mjs';
import { startCapture, writeConcatList } from './capture.mjs';
import { FOOTAGE, WORK, ensureChrome, setViewport } from './session.mjs';

const DEST = join(FOOTAGE, 's5-verify.mp4');

await ensureChrome();
const page = await attach();
await setViewport(page);
await page.send('Page.navigate', { url: `file://${join(WORK, 's5.html')}` });
await sleep(1800);

const dir = join(WORK, 'frames-s5');
const rec = startCapture(page, dir, { fps: 25, quality: 86 });
await sleep(4500);                       // 헤더 + preflight OK 줄을 읽을 시간
await slowScrollTo(page, 420, 3000);
await sleep(5500);                       // 주문=체결 · 중복 0
await slowScrollTo(page, 820, 2500);
await sleep(5500);                       // 각본 5건 체결
const { frames, dropped } = await rec.stop();

const span = frames[frames.length - 1].at / 1000;
console.log(`프레임 ${frames.length} · ${span.toFixed(1)}s · ${(frames.length / span).toFixed(1)}fps · 실패 ${dropped}`);
const list = writeConcatList(dir, frames, join(WORK, 'frames-s5.txt'));
execFileSync('ffmpeg', [
  '-hide_banner', '-loglevel', 'error', '-y',
  '-f', 'concat', '-safe', '0', '-i', list,
  '-vsync', 'cfr', '-r', '30',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
  '-pix_fmt', 'yuv420p', '-movflags', '+faststart', DEST,
], { stdio: 'inherit' });
console.log('S5:', DEST);
process.exit(0);
