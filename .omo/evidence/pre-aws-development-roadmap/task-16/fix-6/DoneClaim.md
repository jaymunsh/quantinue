# Task 16 Fix-6 Done Claim

## 수정 계약

- `EventIngestionExecutor.close()`는 shield 안에서 각 저장소를 정확히 한 번 닫는다.
- `RuntimeError`, `ValueError`, `OSError`를 포함한 일반 `Exception` 종료 실패를 수집하고, 모든 저장소 시도 뒤 첫 실패를 그대로 다시 던진다.
- 취소 및 시스템 종료 같은 `BaseException`은 수집하거나 삼키지 않는다.
- 이미 진행 중인 런타임/취소 주 예외는 `JobRunner`의 종료 경계에서 보존된다.
- 라우팅 취소 회귀는 시간 지연 대신 첫 durable record 체크포인트에서 취소하며, 성공·실패와 무관하게 모든 저장소 및 SQLAlchemy 엔진을 `finally`에서 닫는다.

## 검증 결과

- TDD red: 기존 구현에서 `ValueError`, `OSError`가 ingestion 이후 routing/evidence 종료를 건너뜀.
- TDD green: 세 오류 유형 모두 호출 순서 `ingestion, routing, evidence`, 첫 예외 identity 보존.
- 기준 선택: `164 passed, 1 deselected` (`40.62s`).
  - deselected 1건은 보호된 사용자 변경으로 추가된 `test_owner_page_does_not_attach_watch_when_policy_is_disabled`; 해당 변경 포함 로컬 전체는 `165 passed`.
- critical 12: 10회 반복, `120/120 passed`.
- Ruff: 통과.
- focused basedpyright: `0 errors, 0 warnings, 0 notes`.
- compileall, diff check, 비밀 검사: 통과.
- PostgreSQL 16 직접 확인: `client_connections=0`, `ungranted_locks=0`; 서버 로그에 비정상 연결 종료 없음.

## 보호 및 정리

- `app-v2/src/quantinue/main.py`: `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
- `app-v2/tests/unit/test_runtime_ownership.py`: `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`
- 보호 파일, 8020 프로세스, 5445 컨테이너는 수정하지 않는다.
- fix-6 전용 PostgreSQL 컨테이너와 5490 포트는 커밋 전에 정리한다.
