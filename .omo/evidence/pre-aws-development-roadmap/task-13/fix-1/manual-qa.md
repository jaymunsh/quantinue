# Todo 13 provenance repair manual QA

Surface: `psql` against disposable PostgreSQL 16 on `127.0.0.1:5490`.
Every rejection used `ON_ERROR_STOP=1`; `rc:1` is the expected PostgreSQL
constraint or trigger failure.

Successful state and mutable state machines:

```text
cursor=cursor-2
raw_versions=2
summary_rows=1
receipt_status=processed
valid_order_lineage=true
```

Rejected immutable/coherence violations:

```text
raw_document_update=rc:1
raw_document_delete=rc:1
raw_version_update=rc:1
blank_event_source=rc:1
contradictory_source=rc:1
wrong_evidence_version=rc:1
span_past_end=rc:1
event_update=rc:1
evidence_delete=rc:1
summary_update=rc:1
immutable_rows=1,1,1
```

Binary verdict: PASS. Raw corrections append a second version, long summary
remains exactly one, event/evidence/summary provenance cannot be rewritten,
evidence cannot cross source versions or normalized-text bounds, and cursor plus
processing receipt still transition. A real `tb_order` remains reachable from
the ordered receipt.
