# DoneClaim — Todo 13

## Claim

Immutable intraday event-storage contracts now exist in all four mirrors:
canonical schema, idempotent migration, executable PostgreSQL expectations, and
the canonical integrated-design HTML.

## Contract coverage

- Transactional source cursor/checkpoint with non-empty keys.
- Stable raw-document identity and append-only raw versions. UPDATE/DELETE is
  rejected; document/version and document/hash are unique.
- Deterministic normalized events preserve source ordering and deduplicate event
  identity.
- Evidence spans reference both the normalized event and an immutable raw
  version, with valid non-empty hashes and offsets.
- Summary cache uses exactly `content_hash + model + prompt_version`; a composite
  FK proves the hash/length belongs to the raw version and CHECK permits only
  normalized length greater than 12,000.
- Processing receipts deduplicate `event + ticker + persona`; `ordered` requires
  a real `tb_order` lineage.
- Every persisted column has its named consumer in the HTML schema mirror.

## Evidence

- RED: `7 failed, 5 passed` before DDL.
- GREEN repeated: `12 passed in 11.44s`; `12 passed in 11.88s`.
- Ruff: pass. basedpyright: `0 errors, 0 warnings, 0 notes`. compileall: pass.
- Migration applied twice; full fresh/migrated structural catalog diff: zero.
- Manual PostgreSQL rejection/read-back matrix: PASS.
- Adversarial malformed input, inert prompt-shaped text, rollback/retry,
  partial-migration resume, stale-state replay, actual row counts, and cleanup:
  PASS.
- Disposable container removed and port 5490 free. Ports 8020 and 5445 untouched.

See `verification.md` and `manual-qa.md` for commands and concise captured output.
