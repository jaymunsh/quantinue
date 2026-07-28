# Quantinue

**실물 시장 데이터와 AI 판단으로 굴러가는 모의 자동매매 시스템.**

매일 뉴욕 세션일에 한 번, 시가총액 상위 2,000종목의 세계를 원장(PostgreSQL)에
담고 → 오늘 깊이 볼 종목 20여 개를 고르고 → LLM이 성향별(공격형·안전형)로
판단하고 → 둘째 LLM(크리틱)이 반박하고 → 살아남은 판단만 모의 계좌에서
사고판다. 그 아래에 정규장 동안 1분마다 도는 방어층(LLM 0콜)이 손절·익절선을
지킨다. 시세·뉴스·공시·AI 판단은 전부 실물이고, **모의인 것은 브로커 주문 한
군데뿐**이다.

## 문서 — 여기서 시작

3부작이 GitHub Pages로 서빙된다. 처음이면 순서대로:

| 순서 | 문서 | 무엇을 주나 |
|---|---|---|
| 1 | [하루의 해부](https://jaymunsh.github.io/quantinue/quantinue-day-anatomy.html) | **입구.** 실제로 돈 하루(2026-07-21)를 체결 하나의 계보로 따라간다. 30분이면 시스템의 사고방식이 잡힌다 |
| 2 | [통합 설계서](https://jaymunsh.github.io/quantinue/quantinue-integrated-design.html) | **설계 정본.** JOB 계약 · 장중 층 · 데이터 모델 · 확정 결정 D1~D8과 그 이유 · 의도적으로 안 만든 것 |
| 3 | [기술 부록](https://jaymunsh.github.io/quantinue/quantinue-engineering.html) | **과정과 내부.** 10일 연대기 · 실행에서만 잡힌 결함 27건 · 코드 구조 맵 · 28테이블 ERD |

- 켜고·보고·끄는 **운영 정본**: [docs/operations-runbook.md](docs/operations-runbook.md)
- 1차(MVP-1) 정적 쇼케이스: [quantinue-mvp1-showcase.html](https://jaymunsh.github.io/quantinue/quantinue-mvp1-showcase.html)

## 저장소 구조

| 폴더 | 무엇 |
|---|---|
| [`app-v2/`](app-v2/) | **현행 애플리케이션 (MVP-2)** — FastAPI · PostgreSQL 원장 · 등록 JOB 14종 · 장중 감시. 실행법은 [app-v2/README.md](app-v2/README.md) |
| [`app/`](app/) | 1차 산출물 (MVP-1) — 11단계 선형 파이프라인. **동결, 수정하지 않는다** |
| [`docs/`](docs/) | 문서 전부 — 3부작 HTML(GitHub Pages 소스) · 운영 런북 · [mvp2-planning/](docs/mvp2-planning/) 계획·핸드오프 기록 |
| [`final-project/`](final-project/) | 최종 발표 준비 — 발표 계획 · 슬라이드 · 데모 촬영 하네스 |

## 바로 실행 — 키 없이 3분

기본값이 전부 오프라인이라(fixture 시세 · 메모리 저장소 · mock LLM · 모의
브로커) 외부 키·네트워크·과금 없이 뜬다:

```bash
git clone https://github.com/jaymunsh/quantinue.git
cd quantinue/app-v2
cp .env.example .env
uv sync
uv run uvicorn quantinue.main:app --reload   # → http://localhost:8000
```

PostgreSQL까지 포함하려면 `docker compose up --build --wait`
(웹 `127.0.0.1:8011` · DB `127.0.0.1:5445`). 행동 반경은 `.env`의 모드 스위치
4개(`DATA`/`DATABASE`/`LLM`/`BROKER`)가 정하고, 전부 안전한 쪽이 기본값이다 —
전체 목록과 의미는 [app-v2/.env.example](app-v2/.env.example)의 주석이 정본이다.
실제 주문 제출은 `BROKER_MODE=alpaca`(페이퍼 전용) + `TRADING_ENABLED=true`의
**이중 잠금** 뒤에 있다.

운영 관측 인스턴스(백그라운드 잡·장중 감시)는 일반 `uvicorn`이 아니라
`./scripts/run_observation.sh`로만 시작한다 — 절차는
[운영 런북](docs/operations-runbook.md)을 따른다.

## 검증

```bash
cd app-v2
uv run pytest tests/unit tests/test_*.py -q          # 유닛·웹 804 green (2026-07-28)
uv run pytest tests/integration -q -p no:unraisableexception   # 통합 190 green — 새 컨테이너에서 (기술 부록 런북 참조)
uv run ruff check src tests scripts                  # clean
```

## 정본의 위치

문서가 아니라 파일이 정본인 것들:

- 스키마: [app-v2/db/schema.sql](app-v2/db/schema.sql)
- 정책(문턱·주기·한도): [app-v2/config/pipeline.yaml](app-v2/config/pipeline.yaml)
- 세션 간 개발 핸드오프: [docs/mvp2-planning/dev-handoff.md](docs/mvp2-planning/dev-handoff.md)

## 현재 상태 (2026-07-28)

기능 구현은 완료. 운영 관측 인스턴스가 `watch=true / rejudge=false /
stream=false`로 무인 운영 중이며, 원장에는 2026-07-19~27 구간 7슬롯일의
기록(판단 342건 · 체결 62건 · LLM 4일 $0.53)이 쌓여 있다. 07-28에는
텔레그램 알림(일일 요약·실패 알림)을 운영에 켰고, 같은 날 잡힌 배분 결함
(센트 미만 시세가 돈 계약 검증에 걸림)을 당일 수정·배포했다 — 실패가
5분 안에 알림으로 왔고, 원인 규명부터 배포까지 로그와 커밋으로 남아 있다.

남은 것은 개발이 아니라 순차 운영 활성화다 — 순서와 조건은
[설계서의 운영·검증 절](https://jaymunsh.github.io/quantinue/quantinue-integrated-design.html#ops)에 있다.
