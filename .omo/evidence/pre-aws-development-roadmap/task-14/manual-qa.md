# Todo 14 manual QA

- Environment: disposable PostgreSQL 16, `127.0.0.1:5490`, database `contracts`.
- Public boundary: `ingest_incrementally()` with a typed paged provider and
  `PostgresEventIngestionRepository`.
- Complete pages: page 1/2 included reordered IDs and a duplicate. Direct SQL returned
  `documents=3`, `versions=3`, `events=3`, `receipts=3`, cursor `news:c2`.
- Pagination loop: second page repeated token `same`; the adapter raised
  `PaginationLoopError` before page commit. Direct SQL returned `documents=1`,
  cursor `news:c1`.
- Partial provider failure: page 2 raised `ConnectionError`; direct SQL returned
  `documents=1`, cursor `wire:c1`.
- Restart/late overlap: focused integration test restarted from `c2`, re-read a duplicate
  plus one late item, and observed two documents total with cursor `c3`.
- Malformed item: empty provider ID violated the existing Todo 13 constraint; the complete
  page and cursor rolled back.
- Prompt injection/paywall URL: stored verbatim as raw data; adapters perform no article URL
  request and expose no tool-execution seam.
- Cancellation: cancellation before a complete page preserved the prior single row and
  cursor `c1`; resume remains possible.

Raw redacted terminal output is in `manual-output.txt`. All expected failure scenarios are
asserted by tests, so pytest exits zero only when the failure is safely contained.
