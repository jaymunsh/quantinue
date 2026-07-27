# 촬영·편집 하네스

발표 영상을 다시 만들어야 할 때 쓰는 도구다. 전부 node 내장 기능과 `ffmpeg`만
쓰고, npm 설치가 필요 없다.

## 왜 화면 캡처가 아니라 페이지 직접 캡처인가

처음엔 `ffmpeg -f avfoundation`으로 화면을 녹화했다. **그 방식은 버렸다.**

macOS에서 전체화면 창은 자기 **Space**로 들어간다. 화면 캡처는 "그 디스플레이에
지금 보이는 Space"를 찍기 때문에, 촬영용 창이 자기 Space로 빠진 사이 캡처는
원래 데스크톱을 찍는다. 실제로 그렇게 개인 메신저와 브라우저 탭이 담긴 테이크가
나왔고 폐기했다.

지금은 headless Chrome의 렌더러에서 페이지를 직접 뜬다. 창 겹침·Space·화면
잠금과 무관하고, **페이지 바깥은 원리적으로 프레임에 들어올 수 없다.** 화면을
점유하지 않아 촬영 중에도 컴퓨터를 그대로 쓸 수 있다.

## 순서

```bash
cd final-project/shoot

# 1. 데모를 각본 시작점으로 되돌린다 (각본이 시간축을 탄다)
(cd ../../app-v2 && DEMO_WITH_HISTORY=1 QUANTINUE_DEMO_USER_PASSWORD='qn-demo-user' \
  ./scripts/run_demo.sh reset)

# 2. 마스터 촬영 — 사건이 원장에 뜰 때까지 기다렸다가 장면을 잡는다
node shoot-demo.mjs

# 3. 마스터에서 장면별 원본을 잘라 ../footage/ 로
node cut.mjs

# 4. 무결 검증 장면(S5)
./s5_verify.sh > .work/s5.txt && node render_s5.mjs .work/s5.txt .work/s5.html
node shoot-verify.mjs

# 5. 운영 실증거(S6) — 정규장(22:30 KST~)에 찍어야 장중 감시가 차 있다
node shoot-ops.mjs

# 6. 자막·배지를 얹어 러프컷, 그리고 발표용 요약본
node build_rough.mjs
node build_summary.mjs
```

**리셋 직후에 찍을 필요는 없다.** 각본 결과(NVEX 매수·HLXM 반전·VRDN 손절)는
원장에 남으므로, 이미 사건이 끝난 상태에서 찍어도 같은 화면이 나온다. 리셋은
"아직 사건이 안 난 상태"부터 담고 싶을 때만 필요하다.

## 각본이 화면 어디에 뜨는가 (실측)

| 장면 | 종목 | 뜨는 곳 |
|---|---|---|
| S3 호재 매수 | NVEX | `#allocation` 집행된 매수 — 1,090주 @ $55.00 |
| S4 악재 반전 | HLXM | `#protection` 판단 반전 — 200주 @ $80.00 |
| S2 방어선 | VRDN | `#protection` 손절 — 100주 @ $139.50 |

**각본 티커는 `#judgements`(판단과 반박)에 뜨지 않는다.** 그 패널은
`cycle_ts = 자정`인 일일 슬롯만 그리는데, 이건 배분 잡과 같은 필터라
"관제실 숫자 = 잡 원장 숫자"를 보장하려고 일부러 박아둔 불변식이다
(`control_room_reads.judgements()` docstring 참조). 장중 재판단은 설계상
거기 없다. 그래서 "판단에 근거가 남는다"는 주장은 이어받은 **실제 운영 판단**
카드로 보여준다(S1b).

## 금지선

`shoot-ops.mjs`가 운영(8020)에 보내는 요청은 **GET과 로그인 POST 하나뿐**이다.
관제실에는 실행 버튼이 섞여 있으므로 스크롤만 하고 클릭은 하지 않는다 — 이게
그 파일의 계약이다.

## 파일

| 파일 | 역할 |
|---|---|
| `cdp.mjs` | Chrome DevTools Protocol 드라이버 (WebSocket 직접) |
| `capture.mjs` | 페이지 직접 캡처 녹화기 + 프레임 타이밍 복원 |
| `session.mjs` | 경로 · headless Chrome 기동 · 로그인 · 뷰포트 고정 |
| `shoot-demo.mjs` | 마스터 촬영 (S1a·S3·S4·S1b·S1c·S2) |
| `shoot-verify.mjs` | S5 무결 검증 화면 |
| `shoot-ops.mjs` | S6 운영 실증거 (읽기 전용) |
| `cut.mjs` | 마크 기준으로 장면 분리 |
| `subs.mjs` | 자막·배지를 알파 PNG로 렌더 |
| `edit.mjs` | 오버레이 합성 · 이어붙이기 |
| `build_rough.mjs` / `build_summary.mjs` | 러프컷 · 발표용 요약본 |
| `shots.mjs` | 슬라이드를 PNG로 뽑아 조판 검증 |

## 자막을 왜 PNG로 그리나

이 기계의 `ffmpeg`은 빌드 옵션 17개짜리 슬림 빌드라 `drawtext`도 `subtitles`
필터도 없다. 남은 건 `overlay`뿐이라 자막을 Chrome으로 그려 알파 PNG로 뽑는다.
대신 얻는 것도 있다 — 한글 자간·굵기를 CSS로 통제할 수 있다.

## 중간물

`.work/`에 프레임·중간 클립이 쌓인다(수백 MB). 저장소에 넣지 않는다.
지워도 되고, 지우면 다시 촬영해야 한다.
