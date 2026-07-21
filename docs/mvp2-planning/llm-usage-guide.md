# LLM 사용처 안내 — 어디서, 무엇을, 얼마나 (2026-07-21)

> AWS 이전 시 openai 모드 전환이 강제되므로, **호출당 비용이 생기기 전에**
> 모든 LLM 사용처를 전수 조사해 남긴다. "추론이 필요한 곳엔 추론모델,
> 아닌 곳엔 경량모델"을 어디에 적용할지의 근거 문서다.
>
> 코드 기준: main HEAD (유닛 572 green 시점). 조사 방법: 콜사이트 전수 grep +
> provider/config/schema 직접 확인.

---

## 0. 세 줄 요약

1. **실제 LLM을 호출하는 곳은 단 2곳이다** — 전략 판단(STRATEGY)과 비판
   검증(CRITIC), 둘 다 `roles/analysis/job.py`. 나머지(공시·뉴스·리뷰)는
   결정론이거나 프롬프트에 흡수됐다.
2. **태스크별 모델 분리는 아직 없다.** openai 모드는
   `QUANTINUE_OPENAI_MODEL`(기본 `gpt-4o-mini`) **하나**를 모든 콜에 쓴다.
   "추론모델 vs 경량모델"은 고려만 됐고 배선된 적 없다 — 전환 시 설계 필요.
3. **비용 원장도 아직 없다.** `tb_llm_usage` 테이블과 `budget.daily_llm_usd`
   (3.0)는 선언만 있고 기록·강제 코드가 0이다(`open-items.md` §3-1).
   openai 전환의 선행 필수 작업.

---

## 1. LLM 사용처 전수 (라이브 호출)

호출은 전부 분석 잡(`AnalysisJob`) 안이다. 분석 잡은 **성향당 1개**
등록된다(aggressive·conservative → 잡 2개, `orchestration/job_factory.py:805`).

### A. STRATEGY — 전략 판단 (가장 무거운 콜)

| | |
|---|---|
| 위치 | `roles/analysis/job.py:204` |
| 시스템 프롬프트 | `prompts/role_07_strategist_{aggressive,conservative}.md` — **유일하게 성향별 분기** (`llm/prompts.py:45`) |
| 입력 | 종목 1개의 증거 묶음: 스크리닝 점수·창지표(ma20/50·rsi·vol_ratio 등)·보유 맥락·공시 폼 종류·헤드라인 최대 5개. 본문·재무제표 없음 — 수백 토큰 |
| 출력 | `StrategyModelOutput`: score·label·reason + **bull_case·key_risk 서사**(각 200자 상한, max_tokens 512 실측 근거) |
| 빈도 | **일 1회 × (llm_depth 20 + 보유 종목) × 성향 2종** ≈ 하루 40~60콜 |
| 성격 | 다중 증거 종합 + 방향 판단 + 서사 생성. **추론 부담 최대** |

### B. CRITIC — 비판 검증 (반증 탐지)

| | |
|---|---|
| 위치 | `roles/analysis/job.py:372` |
| 시스템 프롬프트 | `prompts/role_08_critic.md` — 성향 무관 단일 |
| 입력 | 전략의 제안(방향·확신도·근거) + 동일 지표. 소형 |
| 출력 | `ModelOutput`: score·label·reason. score가 승인 문턱(`gates.critic_approval` 0.70, 과신 시 0.80)과 비교됨 |
| 빈도 | **비-hold 제안에만** 호출 — hold면 결정론 verdict(`job.py:335`), 하드 게이트 차단 시에도 스킵(`job.py:367`). 하루 수 콜~수십 콜 |
| 성격 | 반증·모순 탐지. 서사 없음. 단 **승인/기각이 실제 주문을 좌우한다** |

### LLM을 안 쓰는 곳 (헷갈리기 쉬운 순서대로)

| 자리 | 왜 LLM이 없나 |
|---|---|
| 공시·인사이더 채점 | **결정론**(Form 4 필드 기반, `roles/disclosure/`). LLM에 폼 종류만 주고 채점시켰더니 전부 0.500을 내서 기각한 이력. Form 4/3/5는 `disclosure.llm_bypass_forms`로 우회 |
| 뉴스(role_06) | 독립 콜 없음. 헤드라인이 **STRATEGY 프롬프트에 흡수**된다. 투표권은 없음(benzinga=gray 0.50 < trust_min 0.55) — "투표권 없이 영향은 준다" |
| T+5 리뷰(role_11) | 결정론 결과 대조(`roles/role_11_reviewer/processor.py:140`) |
| `AnalysisTask.DISCLOSURE / NEWS / REVIEW` | enum에는 있으나 **라이브 호출부 0** — 레거시. mock 어댑터와 프롬프트 로더 계약만 남아 있다 |

---

## 2. 모드와 설정 — 지금의 배선

선택은 `build_llm_analyzer()`(`llm/provider.py:256`)의 3-way 분기 하나다.

| 모드 | 모델 | 용도 |
|---|---|---|
| `mock` | `deterministic-mock-v1` | 테스트·오프라인. 고정값 — 판단이 가짜 |
| `local` | `QUANTINUE_LOCAL_LLM_MODEL` (관측: `Qwen3.6-35B-A3B-OptiQ-4bit`, oMLX 127.0.0.1:8888) | 현 관측 운용. 비용 0 |
| `openai` | `QUANTINUE_OPENAI_MODEL` (기본 `gpt-4o-mini` — **경량 최저가 모델이다. 추론모델 아님**) | AWS 이전 시 강제 |

공통 설정: `QUANTINUE_LLM_TIMEOUT_SECONDS`(관측 90) ·
`QUANTINUE_LLM_MAX_RETRIES`(1, 구조화 출력 재시도) ·
`QUANTINUE_LLM_MAX_OUTPUT_TOKENS`(512). SDK 재시도는 양 모드 모두 0으로
고정하고 재시도 예산을 pydantic-ai `Agent(retries=)`가 소유한다.

### ⚠️ openai 전환 시 그대로 옮겨지지 않는 것

로컬 경로에만 붙어 있는 `model_settings`(`provider.py:278-296`)가 openai
경로에는 **하나도 적용되지 않는다**:

- `max_tokens=512` · `temperature=0` — openai 경로는 라이브러리 기본값
- `openai_reasoning_effort="none"` + `enable_thinking=False` — Qwen의
  chain-of-thought 억제용. openai에서는 반대로 **추론을 얼마나 켤지**를
  다시 정해야 한다(추론 모델을 쓴다면)

`open-items.md` §3-3의 재확인 2건(retries 동작 · 성향 격차)도 이때 함께 본다.

---

## 3. "추론모델 vs 경량모델" — 현재 상태와 제안

**현재: 미배선.** 모드당 모델 1개, per-call 오버라이드 없음, 태스크별 모델
설정 키 없음. 문서·코드 어디에도 tier 구분 구현 흔적이 없다 — 이 문서가
그 첫 설계 근거다.

다행히 분리 지점은 이미 코드에 있다: `AnalysisTask` enum이 콜의 성격을
구분하고, `analyze(task, ...)`가 모든 콜의 단일 통로다.

### 제안 매핑 (실무 관점)

| 태스크 | 제안 tier | 근거 |
|---|---|---|
| **STRATEGY** | **추론 모델** (예: o4-mini급 reasoning tier) | 다중 증거 종합 + 서사 생성. 로컬 35B가 하던 일이고, 성향 격차(보수형 -0.100 일괄 패턴)가 프롬프트 재추론에 달려 있다 — 경량 모델이 가장 티 나게 무너질 자리 |
| **CRITIC** | **중간** — 처음엔 STRATEGY와 같은 모델로 시작 | 반증 탐지는 판단력이 필요하고, 승인/기각이 주문을 좌우한다. 콜 수가 적어(비-hold만) 절감 효과도 작다 — 여기서 아끼는 건 리스크 대비 이득이 없다 |
| (향후 DISCLOSURE·NEWS 재활성화 시) | 경량 (mini/nano급) | 요약·분류 성격. 단 지금은 호출부가 없으므로 **배선하면 유령** |

즉 실질 결론은 단순하다: **콜이 2종뿐이고 둘 다 판단 콜이라, 초기엔 모델
하나(추론 tier)로 시작해도 된다.** 태스크별 분리는 DISCLOSURE류 경량 콜이
부활하거나 인트라데이(R3)로 콜 수가 곱해질 때 실익이 생긴다. 분리를 만들
때의 최소 설계: `AnalysisTask → 모델명` 맵을 Settings에 두고
`build_llm_analyzer`가 태스크별 analyzer를 반환 — 콜사이트는 안 바뀐다.

### 비용 자릿수 감각 (전환 판단용)

하루 콜 수 ≈ STRATEGY 40~60 + CRITIC 수~수십 = **최대 ~100콜/일**.
콜당 입력 수백~2천 토큰(시스템 프롬프트 포함) + 출력 ≤512 토큰이므로
하루 총량은 **수십만 토큰 자릿수**다. 경량(gpt-4o-mini급)이면 하루 수 센트,
추론 tier(o4-mini급)여도 하루 $0.5 미만 — `budget.daily_llm_usd=3.0` 안에
넉넉히 든다. 요율 표와 크레딧($90/10일) 대비 실산은
`aws-migration-review.md` §2가 정본이다.
단 **요율은 전환 시점에 실제 가격표로 재확인**하고, 인트라데이(R3)로
사이클이 곱해지는 순간 이 산수는 무효다. 그래서 예산 배선(§4)이 선행이다.
비용이 제약이 아니므로 예산 배선의 실제 역할은 절약이 아니라
**폭주 차단**(버그로 인한 무한 재시도·중복 호출)이다.

---

## 4. openai 전환 전 선행 작업 (순서대로)

1. **LLM 예산 배선** (`open-items.md` §3-1, completion-plan ⑨) —
   `PydanticAiAnalyzer.analyze`에서 매 콜을 `tb_llm_usage`(스키마는 이미
   있다: `db/schema.sql:249`)에 기록하고, `budget.daily_llm_usd` 초과 시
   **호출 스킵**(판단 없이 사는 쪽이 아니라 **안 사는** 쪽).
2. **openai 경로에 model_settings 부여** — max_tokens·temperature·
   (추론 모델이면) reasoning effort. 지금은 로컬에만 있다(§2).
3. **§3-3 재확인 2건** — retries가 openai에서 의도대로 도는지, 성향 격차가
   실 모델에서도 유지되는지 (mock 아닌 실콜 한 바퀴).
4. 그 다음에야 모델 tier 결정(§3)이 의미를 갖는다.

---

## 부록: 한눈에 보는 배선

```
main.py:196  build_llm_analyzer(settings)          # 모드 → analyzer 1개 (전 콜 공유)
   └─ job_factory.py:805  성향별 분석 잡 × {aggressive, conservative}
        └─ AnalysisJob.run  (일 1회 · 범위 = llm_depth 20 + 보유 전부)
             ├─ 종목마다   analyze(STRATEGY, …, profile=성향)   # job.py:204  ★ 추론 무거움
             └─ 비-hold만  analyze(CRITIC, …)                   # job.py:372  ★ 주문 게이트
```

정본 파일: `llm/provider.py`(어댑터·모드 선택) · `llm/prompts.py`(프롬프트
로더·성향 분기) · `core/config.py:89-102`(설정 키) ·
`config/pipeline.yaml`(llm_depth·bypass_forms·budget) ·
`db/schema.sql:249`(tb_llm_usage). 계약 테스트: `tests/unit/test_llm_provider.py` ·
`test_llm_prompts.py`.
