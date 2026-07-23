# Task 16 Fix-5 Done Claim

## 구현 계약

- 캐시 적중 요약도 `MAX_SUMMARY_CHARS`를 초과하면 `OVERSIZED_SUMMARY`로 실패하며 사용되지 않는다.
- 사용자 프롬프트 템플릿 본문이 바뀌면 요약 캐시 identity가 바뀐다.
- 한 틱에 `sec`, `news`, `wire`가 모두 도착해도 전역 accepted backlog 준비는 한 번만 실행되며 poison 문서는 유한 실패로 기록된다.
- ingestion, routing, evidence 저장소 종료를 각각 정확히 한 번 시도하고 첫 종료 오류를 보존한다.
- 런타임의 주 예외가 진행 중이면 종료 오류가 그 주 예외를 대체하지 않는다.

## 검증

- 관련 선택: `63 passed`
- 경계 스트레스: 6개 시나리오를 10회 반복, 매회 `6 passed`
- Ruff check: 통과
- Ruff format check 대상 소스: 통과
- Python compileall: 통과
- diff check 및 비밀 패턴 검사: 통과
- PostgreSQL 16, 로컬 포트 5490에서 통합 테스트 실행
- basedpyright: 이번 변경과 무관한 `job_runner.py` 기존 `Any`/암시적 문자열 연결 진단 8건 재현; 새 fix-5 코드 진단 없음

## 보호 및 정리

- `app-v2/src/quantinue/main.py`: `c68c0ad1dcba0f595e87b5fcef064f201efdb6e4e7849fc15598de2a9af65174`
- `app-v2/tests/unit/test_runtime_ownership.py`: `c366abf57ff738bd13f78097fa5e96a5cc5e916f2b16ced6ea254ad4c67c5d99`
- 위 두 사용자 소유 변경은 수정하거나 스테이징하지 않는다.
- fix-5 전용 PostgreSQL 컨테이너는 검증 뒤 제거한다.
