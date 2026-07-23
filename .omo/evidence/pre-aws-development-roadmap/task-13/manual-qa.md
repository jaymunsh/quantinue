# Task 13 manual QA

Surface: terminal plus disposable PostgreSQL 16 on `127.0.0.1:5490`.

The exact setup used `docker exec -i quantinue-task13-postgres psql
-v ON_ERROR_STOP=1 -U postgres -d fresh`. It inserted a short version, a
12,001-character version, a corrected second version, one normalized event, one
evidence span, and one processing receipt.

Observed successful state:

```text
cursor=cursor-2
raw_versions=2,hashes=short-hash,short-hash-v2
summary_rows=1
prompt_text_inert=true
order_table_exists=true
valid_order_lineage=true
```

The cursor was changed inside a transaction and rolled back before `cursor-2`
was committed. The raw prompt-injection-shaped text remained byte-for-byte inert
data and did not affect `tb_order`.

Each command below used `psql -v ON_ERROR_STOP=1`; `rc:1` is the expected
PostgreSQL constraint/trigger rejection:

```text
short_summary=rc:1
duplicate_summary=rc:1
overwrite_raw_hash=rc:1
duplicate_event=rc:1
orphan_evidence=rc:1
duplicate_receipt=rc:1
empty_hash=rc:1
invalid_length=rc:1
invalid_offsets=rc:1
invalid_status=rc:1
ordered_without_order=rc:1
summary_rows=1
event_rows=1
receipt_rows=1
```

Binary verdict: PASS. Every required rejection was non-zero, every permitted
insert had the expected row count, the corrected version preserved the original
hash, and an ordered receipt joined to a real `tb_order`.
