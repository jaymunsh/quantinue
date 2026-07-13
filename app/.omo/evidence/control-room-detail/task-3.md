# Task 3 — safe terminal-detail API projection

## Delivered

- Added frozen API views for terminal collection, strategist, and critic details.
- Added `GET /api/runs/{run_id}/detail`; the existing run-observability response carries
  the same projected detail.
- Added one URL projection boundary: only absolute, credential-free `http`/`https`
  references receive an `href`. Non-web, malformed, whitespace/control-character, and
  credential-bearing inputs remain non-clickable. Credential-bearing labels drop userinfo,
  query, and fragment material.
- Preserved the existing evidence and redacted stage-attempt projections. Raw attempt error
  messages remain absent from every detail response.

## TDD and focused verification

1. Red: `uv run pytest tests/unit/test_api_terminal_detail.py -q` initially failed with
   `404` because no dedicated detail route existed.
2. Green: `uv run pytest tests/unit/test_api_terminal_detail.py -q` → `8 passed`.
3. Static checks:

```text
uv run ruff format --check <changed API files and focused test>
5 files already formatted

uv run ruff check <same paths>
All checks passed!

uv run basedpyright <same paths>
0 errors, 0 warnings, 0 notes
```

Pure nonblank/noncomment LOC:

```text
src/quantinue/api/presentation.py 183
src/quantinue/api/run_detail.py 19
src/quantinue/api/schemas.py 117
src/quantinue/main.py 152
```

## Manual runtime proof

An in-memory `TestClient` driver called the real route. It returned HTTP 200, retained a
public SEC `https` destination, and converted a credential-bearing URL to a non-clickable,
credential-free label. No database, Docker resource, environment file, or host `localhost:5432`
resource was accessed.

```text
status=200
public_href=https://www.sec.gov/Archives/edgar/data/1
credential_href=None
credential_label=https://example.com/private
```

## Adversarial probes

- `sec://` and `fixture://`: readable label, no `href`.
- `javascript:` and `data:`: generic non-web label, no payload echoed and no `href`.
- Userinfo URL: no `href`; no userinfo/query/fragment in the label.
- Malformed IPv6 URL: `invalid reference`, no `href`.
- Attempt error redaction: preserved by the existing `AttemptView` projection; new terminal
  detail views contain only the bounded contract fields.

## Scope and residual observation

- No template/CSS, role service, core terminal-detail contract, scheduler, Docker, database,
  environment, or trading setting was changed by this task.
- A combined `tests/test_web.py` run had two pre-existing environment-dependent failures:
  default public NASDAQ data no longer matched its fixture shape, and the active local LLM mode
  differed from the test's mock-mode expectation. The focused API suite is green; no test or
  environment setting was weakened or changed.

## Amendment — strategist conviction

- Added the nullable `0..1` strategist conviction field to `StrategyDetailView` and projected
  the already-bounded terminal contract value into it.
- The focused API test now persists `0.82`, verifies it from the dedicated endpoint, and confirms
  the full observability response carries the identical detail view.
- Re-run after the amendment: focused API suite `8 passed`; Ruff format/check clean;
  basedpyright `0 errors, 0 warnings, 0 notes`.
- A fresh in-memory `TestClient` runtime call returned HTTP 200 with
  `strategy.conviction=0.82`. No Docker, database, environment file, or `localhost:5432`
  resource was accessed.

## Amendment — control-character reference redaction

- Corrected a verifier-found issue: whitespace/control references previously skipped `href` but
  reached the readable-label fallback unchanged.
- The projection now rejects that entire input class before URL parsing and returns only
  `invalid reference`. The terminal reference field preserves whitespace so leading whitespace is
  not normalized into a valid URL before the security boundary evaluates it.
- Added pure-projection and real route regressions for newline, NUL/tab, and leading whitespace.
  Each asserts no `href`, the generic label, and absence of the raw marker from the JSON response.
- Re-run: `uv run pytest tests/unit/test_api_terminal_detail.py
  tests/unit/test_terminal_detail_contract.py -q` → `20 passed`; Ruff format/check clean;
  basedpyright `0 errors, 0 warnings, 0 notes`.
- Manual in-memory `TestClient` calls to the real route returned HTTP 200 for all three inputs
  with `label=invalid reference`, `href=None`, and no marker in the response body. No Docker,
  database, environment file, or localhost service was accessed.
