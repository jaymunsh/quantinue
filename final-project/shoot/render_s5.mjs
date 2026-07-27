// s5_verify.sh의 실행 기록을 화면에 올릴 수 있는 페이지로 만든다.
//
// 원칙: **출력은 한 글자도 고치지 않는다.** 이 페이지는 터미널 흉내가 아니라
// "이 명령을 돌렸고 이렇게 나왔다"는 기록이고, 명령줄을 함께 보여주기 때문에
// 보는 사람이 직접 재현할 수 있다. 각색한 화면을 만들면 영상 전체의 신뢰가
// 그 한 장에서 무너진다.
import { readFileSync, writeFileSync } from 'node:fs';

const src = process.argv[2];
const dest = process.argv[3];
const raw = readFileSync(src, 'utf8');

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const body = raw
  .split('\n')
  .map((line) => {
    if (line.startsWith('$ ')) return `<span class="cmd">${esc(line)}</span>`;
    if (line.startsWith('# ')) return `<span class="hdr">${esc(line)}</span>`;
    if (/preflight OK/.test(line)) return `<span class="ok">${esc(line)}</span>`;
    if (/\bFAIL\b|ERROR/.test(line)) return `<span class="bad">${esc(line)}</span>`;
    return esc(line);
  })
  .join('\n');

writeFileSync(dest, `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>데모 원장 무결 검증</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  /* 1080p 프레임에서 읽히는 크기가 기준이다 — 터미널 기본 크기로 두면
     영상에서 아무도 못 읽는다. */
  body { margin: 0; background: #0d1117; color: #c9d1d9;
         font: 22px/1.62 "SFMono-Regular", "JetBrains Mono", Menlo, monospace; }
  header { padding: 34px 60px 24px; border-bottom: 1px solid #21262d;
           display: flex; align-items: baseline; gap: 20px; }
  header h1 { margin: 0; font-size: 30px; letter-spacing: .01em; color: #e6edf3; font-weight: 700;
              font-family: "Apple SD Gothic Neo", -apple-system, sans-serif; }
  header .tag { font-size: 17px; letter-spacing: .06em; color: #7d8590;
                font-family: "Apple SD Gothic Neo", -apple-system, sans-serif; }
  header .badge { margin-left: auto; font-size: 19px; font-weight: 700; letter-spacing: .06em;
                  color: #ffd77a; border: 2px solid #d29922; background: rgba(60,44,8,.92);
                  padding: 10px 20px; border-radius: 999px;
                  font-family: "Apple SD Gothic Neo", -apple-system, sans-serif; }
  pre { margin: 0; padding: 30px 60px 60px; white-space: pre-wrap; word-break: break-word; }
  .cmd { color: #79c0ff; font-weight: 600; }
  .hdr { color: #8b949e; }
  .ok  { color: #3fb950; font-weight: 600; }
  .bad { color: #f85149; font-weight: 600; }
</style></head>
<body>
  <header>
    <h1>데모 원장 무결 검증</h1>
    <span class="tag">실제 실행 출력 · 편집 없음</span>
    <span class="badge">데모 환경 · 모의 AI · 모의 체결</span>
  </header>
  <pre>${body}</pre>
</body></html>
`);
console.log('wrote', dest);
