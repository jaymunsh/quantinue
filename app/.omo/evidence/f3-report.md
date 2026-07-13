# F3 hands-on manual QA

## Verdict

**FAIL / REVISE required.** Runtime, safety, Docker, and automated responsive gates pass, but the independent visual/CJK review found blocking mobile wrapping and history-badge defects. Product files were inspected read-only and were not modified.

## Passed checks

- Offline `GET /health`: mock/mock safe defaults.
- Two same-minute `POST /api/runs` requests: identical run ID, client-order ID, and broker order ID; both returned completed 01-11 with 11 evidence records.
- Focused retry/timeout/duplicate-order/store/UI tests: `42 passed in 1.21s`.
- Chromium completed UI: 1440/1024/768/390 plus keyboard and reduced-motion, `5 passed`.
- Store-backed state UI: running/retrying/failed at 1440/390, `2 passed` per state; raw provider error redacted.
- Lighthouse reproducibility: mobile x3 and desktop x3; performance/accessibility/best-practices/SEO all 100 in all six runs.
- Checked-in Compose contract: PASS (`127.0.0.1:5444 -> db:5432`, `127.0.0.1:8011 -> web:8000`, no host 5432 publication).
- Collision-safe Docker smoke used only project `quantinue_f3_qa`, host ports 15444/18013, returned healthy and completed 11 stages/11 evidence records.
- Existing `pf-postgres` host 5432 binding remained present before and after QA and was never operated on.

## Blocking visual findings

1. At 390 px, `외부 계정 없이도` wraps after `외부 계정`, separating the intended phrase in every state capture (`dashboard.html` command description).
2. At 390 px, `담당자가 독립 교체할 수 있습니다` wraps after `독립`, producing an unnatural Korean semantic break in running/retrying/failed captures (`dashboard.html` pipeline explanation).
3. At 390 px, the recent-run status badge stretches across the value grid column instead of remaining a pill (`dashboard.css` mobile table layout needs `justify-self: start` or equivalent).
4. QA-fixture-only defect: the F3 running harness supplied `ProviderTimeout`, so the running screenshots show a failure code. This does not prove a production-path defect, but those running-state captures cannot support a clean visual PASS. A corrected running fixture should omit `error_code` and be recaptured.

## Exact command families

```sh
uv run uvicorn quantinue.main:app --host 127.0.0.1 --port 18765
curl -fsS -X POST -H 'content-type: application/json' -d '{"ticker":"NVDA"}' http://127.0.0.1:18765/api/runs
npx playwright test .omo/evidence/f3-browser.spec.js --reporter=line
F3_STATE=<running|retrying|failed> uv run uvicorn --app-dir .omo/evidence f3-state-harness:app --host 127.0.0.1 --port <18766|18767|18768>
F3_STATE=<state> F3_BASE_URL=http://127.0.0.1:<port> npx playwright test .omo/evidence/f3-state-browser.spec.js --reporter=line
F3_BASE_URL=http://127.0.0.1:18765 node .omo/evidence/f3-lighthouse.mjs
uv run pytest -q tests/unit/test_retry.py tests/unit/test_broker_provider.py tests/unit/test_persistence_orchestration.py tests/test_web.py
sh scripts/test_compose_contract.sh
docker compose -f compose.yaml -f .omo/evidence/f3-compose-override.yaml --project-name quantinue_f3_qa up --build --wait
docker compose -f compose.yaml -f .omo/evidence/f3-compose-override.yaml --project-name quantinue_f3_qa down -v --remove-orphans
docker image rm quantinue_f3_qa-web:latest
```

## Artifacts

- `f3-api-duplicate.txt`, `f3-focused-tests.txt`
- `f3-browser.txt`, `f3-state-{running,retrying,failed}.txt`
- `f3-completed-*.png`, `f3-{running,retrying,failed}-*.png`
- `f3-lighthouse.json`
- `f3-compose-contract.txt`, `f3-compose-default-rendered.yaml`, `f3-docker-runtime.txt`
- `f3-docker-before.txt`, `f3-docker-after.txt`, `f3-cleanup.txt`, `f3-post-cleanup.txt`

## Cleanup receipt

Ports 18765-18768, 15444, and 18013 are free. No `quantinue_f3_qa` container, volume, network, image, harness process, or temporary JSON remains. Existing non-F3 containers were left untouched.
