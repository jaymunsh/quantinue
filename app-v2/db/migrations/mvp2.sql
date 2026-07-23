-- MVP-2 schema migration: upgrades a 1st-generation database in place.
--
-- Every statement is idempotent, so this file may be replayed safely.
-- Existing rows are preserved: new columns are nullable or carry a DEFAULT,
-- and reason TEXT values are wrapped as {"legacy": "..."} rather than dropped.
--
-- Apply:  psql "$QUANTINUE_DATABASE_URL" -f db/migrations/mvp2.sql

BEGIN;

CREATE TABLE IF NOT EXISTS tb_watch_sweep (
  sweep_at TIMESTAMPTZ PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
  attempts INT NOT NULL DEFAULT 1 CHECK (attempts > 0),
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL,
  detail TEXT,
  CHECK ((status = 'running') = (finished_at IS NULL))
);

CREATE TABLE IF NOT EXISTS tb_watch_sweep_item (
  sweep_at TIMESTAMPTZ NOT NULL REFERENCES tb_watch_sweep(sweep_at),
  ticker TEXT NOT NULL,
  persona TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('claimed','dispatched','completed')),
  attempt INT NOT NULL CHECK (attempt > 0),
  claimed_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (sweep_at, ticker, persona),
  CHECK ((status = 'claimed') = (dispatched_at IS NULL)),
  CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);

-- 1. reason TEXT -> JSONB (4 tables). Legacy prose is preserved under "legacy".
DO $$
DECLARE
  target RECORD;
BEGIN
  FOR target IN
    SELECT table_name FROM information_schema.columns
    WHERE table_schema = 'public'
      AND column_name = 'reason'
      AND data_type = 'text'
      AND table_name IN ('tb_disclosure', 'tb_disclosure_signal', 'tb_news', 'tb_news_signal')
  LOOP
    EXECUTE format(
      'ALTER TABLE %I ALTER COLUMN reason TYPE JSONB USING '
      'CASE WHEN reason IS NULL THEN NULL ELSE jsonb_build_object(''legacy'', reason) END',
      target.table_name
    );
  END LOOP;
END $$;

ALTER TABLE tb_disclosure ALTER COLUMN reason SET DEFAULT '{}'::jsonb;
UPDATE tb_disclosure SET reason = '{}'::jsonb WHERE reason IS NULL;

-- 2. Disclosure signal aggregates, mirroring tb_news_signal.
ALTER TABLE tb_disclosure_signal
  ADD COLUMN IF NOT EXISTS disclosure_count SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS top_evidence TEXT[] NOT NULL DEFAULT '{}';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'tb_disclosure_signal'::regclass
      AND conname = 'tb_disclosure_signal_disclosure_count_check'
  ) THEN
    ALTER TABLE tb_disclosure_signal
      ADD CONSTRAINT tb_disclosure_signal_disclosure_count_check CHECK (disclosure_count >= 0);
  END IF;
END $$;

-- 3. Strategist side admits 'sell' (M5 exits).
ALTER TABLE tb_strategist_signals DROP CONSTRAINT IF EXISTS tb_strategist_signals_side_check;
ALTER TABLE tb_strategist_signals
  ADD CONSTRAINT tb_strategist_signals_side_check CHECK (side IN ('buy', 'hold', 'sell'));

-- 4. Critic cache-state source is renamed so lineage `source` stays uniform.
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'tb_critic_verdict' AND column_name = 'source'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'tb_critic_verdict' AND column_name = 'verdict_source'
  ) THEN
    ALTER TABLE tb_critic_verdict RENAME COLUMN source TO verdict_source;
    ALTER TABLE tb_critic_verdict
      RENAME CONSTRAINT tb_critic_verdict_source_check TO tb_critic_verdict_verdict_source_check;
  END IF;
END $$;

-- 5. Reproduction lineage on roles 07 and 08 (R10). Nullable: existing rows predate it.
ALTER TABLE tb_strategist_signals
  ADD COLUMN IF NOT EXISTS source TEXT,
  ADD COLUMN IF NOT EXISTS source_ref TEXT,
  ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS evidence_id TEXT,
  ADD COLUMN IF NOT EXISTS parent_evidence_ids JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS model_provider TEXT,
  ADD COLUMN IF NOT EXISTS model_name TEXT,
  ADD COLUMN IF NOT EXISTS prompt_version TEXT,
  ADD COLUMN IF NOT EXISTS policy_version TEXT,
  ADD COLUMN IF NOT EXISTS input_hash TEXT;

ALTER TABLE tb_critic_verdict
  ADD COLUMN IF NOT EXISTS source TEXT,
  ADD COLUMN IF NOT EXISTS source_ref TEXT,
  ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS evidence_id TEXT,
  ADD COLUMN IF NOT EXISTS parent_evidence_ids JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS model_provider TEXT,
  ADD COLUMN IF NOT EXISTS model_name TEXT,
  ADD COLUMN IF NOT EXISTS prompt_version TEXT,
  ADD COLUMN IF NOT EXISTS policy_version TEXT,
  ADD COLUMN IF NOT EXISTS input_hash TEXT;

-- 6. New tables: users, LLM spend ledger, benchmark closes.
CREATE TABLE IF NOT EXISTS tb_user (
  user_id BIGSERIAL PRIMARY KEY, login_id TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','user')), otp_secret TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tb_llm_usage (
  id BIGSERIAL PRIMARY KEY, called_at TIMESTAMPTZ NOT NULL, task TEXT NOT NULL,
  model TEXT NOT NULL, prompt_tokens INT NOT NULL CHECK (prompt_tokens >= 0),
  completion_tokens INT NOT NULL CHECK (completion_tokens >= 0),
  est_cost_usd NUMERIC NOT NULL CHECK (est_cost_usd >= 0), run_id TEXT
);

CREATE TABLE IF NOT EXISTS tb_benchmark_price (
  price_date DATE NOT NULL, ticker TEXT NOT NULL, close NUMERIC NOT NULL CHECK (close > 0),
  PRIMARY KEY (price_date, ticker)
);

-- 7. Account ownership, investment type, and lifecycle status.
ALTER TABLE tb_account
  ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES tb_user(user_id),
  ADD COLUMN IF NOT EXISTS inv_type TEXT,
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'tb_account'::regclass AND conname = 'tb_account_inv_type_check'
  ) THEN
    ALTER TABLE tb_account ADD CONSTRAINT tb_account_inv_type_check
      CHECK (inv_type IN ('aggressive','conservative'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'tb_account'::regclass AND conname = 'tb_account_status_check'
  ) THEN
    ALTER TABLE tb_account ADD CONSTRAINT tb_account_status_check
      CHECK (status IN ('active','paused','closed'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS tb_account_user_id_key
  ON tb_account(user_id) WHERE user_id IS NOT NULL;

COMMIT;

-- M4-7a: 투표원은 technical·disclosure·news·model 4개인데 CHECK가 0~3이라
-- 만장일치 4에서 INSERT가 깨진다. 실계산을 켜기 전에 범위를 넓힌다.
DO $$
BEGIN
  ALTER TABLE tb_strategist_signals
    DROP CONSTRAINT IF EXISTS tb_strategist_signals_signal_consensus_check;
  ALTER TABLE tb_strategist_signals
    ADD CONSTRAINT tb_strategist_signals_signal_consensus_check
    CHECK (signal_consensus BETWEEN 0 AND 4);
END $$;

-- M4 관측: 역할 09의 판단(집행/보류·사유)이 어디에도 저장되지 않아
-- "이번 주에 갭 가드가 몇 번 걸렸나"를 물을 수 없었다. 주문이 생긴 경우만
-- tb_order에 남았을 뿐, 막힌 경우는 JSONB 요약 문자열이 전부였다.
-- 문턱 보정(premarket_gap_max 등)이 바로 이 관측에 의존한다.
CREATE TABLE IF NOT EXISTS tb_order_plan (
  id BIGSERIAL PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL, cycle_ts TIMESTAMPTZ NOT NULL,
  trade_date DATE NOT NULL, account_id BIGINT, signal_id BIGINT,
  decision TEXT NOT NULL CHECK (decision IN ('planned','skipped')), skipped_reason TEXT,
  quantity INT NOT NULL CHECK (quantity >= 0), entry_price NUMERIC, stop_price NUMERIC, take_profit_price NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (ticker, cycle_ts, account_id),
  CHECK ((decision = 'planned' AND skipped_reason IS NULL AND quantity > 0)
      OR (decision = 'skipped' AND skipped_reason IS NOT NULL AND quantity = 0))
);

-- M5: 매도(청산) 주문 표현. tb_order는 브래킷 매수 전용이었다 —
-- order_type CHECK가 'bracket'만 받고, 손절·익절이 NOT NULL이며,
-- stop < entry < take_profit 삼중 제약이 매도에서는 만족될 수 없다.
-- 청산에 더미 손절·익절을 채우는 대신 컬럼을 비우고 제약을 조건부로 만든다.
DO $$
BEGIN
  ALTER TABLE tb_order ALTER COLUMN stop_price DROP NOT NULL;
  ALTER TABLE tb_order ALTER COLUMN take_profit_price DROP NOT NULL;
  ALTER TABLE tb_order ADD COLUMN IF NOT EXISTS closes_order_id BIGINT REFERENCES tb_order(id);

  ALTER TABLE tb_order DROP CONSTRAINT IF EXISTS tb_order_order_type_check;
  ALTER TABLE tb_order ADD CONSTRAINT tb_order_order_type_check
    CHECK (order_type IN ('bracket','close'));

  ALTER TABLE tb_order DROP CONSTRAINT IF EXISTS tb_order_check;
  ALTER TABLE tb_order ADD CONSTRAINT tb_order_check
    CHECK (order_type <> 'bracket' OR (
      stop_price IS NOT NULL AND take_profit_price IS NOT NULL
      AND stop_price < entry_price AND entry_price < take_profit_price));

  ALTER TABLE tb_order DROP CONSTRAINT IF EXISTS tb_order_close_target_check;
  ALTER TABLE tb_order ADD CONSTRAINT tb_order_close_target_check
    CHECK (order_type <> 'close' OR closes_order_id IS NOT NULL);
END $$;


-- Phase 2: 일봉 원장. 신규 테이블이라 무손실 — 기존 행에 손대지 않는다.
CREATE TABLE IF NOT EXISTS tb_daily_bar (
  trade_date DATE NOT NULL, ticker TEXT NOT NULL,
  open NUMERIC NOT NULL CHECK (open > 0), high NUMERIC NOT NULL CHECK (high > 0),
  low NUMERIC NOT NULL CHECK (low > 0), close NUMERIC NOT NULL CHECK (close > 0),
  volume BIGINT NOT NULL CHECK (volume >= 0), source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (trade_date, ticker),
  CHECK (low <= open AND open <= high), CHECK (low <= close AND close <= high)
);

-- Phase 2: 잡 실행 원장. 신규 테이블이라 무손실 — 기존 행에 손대지 않는다.
CREATE TABLE IF NOT EXISTS tb_job_run (
  job_name TEXT NOT NULL, slot_date DATE NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
  detail TEXT, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
  -- 같은 슬롯을 몇 번 집었나(재시도 포함). started_at은 마지막 시도의 것만
  -- 남으므로(결함 24 수리) 이 수가 없으면 "하루에 몇 번 돌았나"를 원장이 못 답한다.
  attempts INT NOT NULL DEFAULT 1 CHECK (attempts > 0),
  PRIMARY KEY (job_name, slot_date),
  CHECK ((status = 'running') = (finished_at IS NULL))
);
-- 기존 설치는 CREATE IF NOT EXISTS가 건너뛰므로 컬럼을 따로 더한다(멱등).
-- 이미 있으면 CHECK까지 통째로 스킵된다 — 제약이 중복 생성되지 않는다.
ALTER TABLE tb_job_run
  ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 1 CHECK (attempts > 0);

-- Phase 2: 공시 원시 원장. 신규 테이블이라 무손실.
CREATE TABLE IF NOT EXISTS tb_disclosure_raw (
  filing_no TEXT NOT NULL, trade_date DATE NOT NULL, ticker TEXT NOT NULL,
  cik TEXT NOT NULL, form_type TEXT NOT NULL, company_name TEXT NOT NULL,
  source_ref TEXT NOT NULL, event_type TEXT, is_hard_event BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (filing_no),
  CHECK (is_hard_event = false OR event_type IS NOT NULL)
);

-- Phase 3: 분석 범위의 크기는 config(screening.llm_depth)와 보유 수가 정한다.
-- 50 상한은 구 스크리너가 종목당 1콜을 쓰던 시절의 흔적이고, 걸리는 순간
-- 보유가 범위 밖으로 밀려 청산 시그널을 남길 자리가 없어진다.
-- 제약 이름은 신규 설치가 생성하는 것과 같아야 한다(카탈로그 대조).
ALTER TABLE tb_daily_pick DROP CONSTRAINT IF EXISTS tb_daily_pick_rank_check;
ALTER TABLE tb_daily_pick ADD CONSTRAINT tb_daily_pick_rank_check CHECK (rank >= 1);

-- Phase 3: 유니버스는 상장 피드가 아니라 거래 가능 범위다. 상장폐지된 보유는
-- 이월되고 여기에 라벨이 붙는다 — 라벨 없이 union만 하면 "왜 상장 피드에 없는
-- 종목이 유니버스에 있나"에 답할 수 없고, 그 자체가 다음 세대의 유령이 된다.
-- 기존 행은 전부 상장 피드에서 온 것이므로 DEFAULT 'listed'가 정확하다.
ALTER TABLE tb_universe ADD COLUMN IF NOT EXISTS listing_status TEXT NOT NULL DEFAULT 'listed';
ALTER TABLE tb_universe DROP CONSTRAINT IF EXISTS tb_universe_listing_status_check;
ALTER TABLE tb_universe ADD CONSTRAINT tb_universe_listing_status_check
  CHECK (listing_status IN ('listed','held_delisted'));

-- Phase 3: 뉴스 원시 원장. 공시(tb_disclosure_raw)와 같은 이유로 FK가 없다 —
-- tb_news(채점 결과)는 (trade_date, ticker) → tb_daily_pick을 걸어 그날 분석
-- 대상이 아닌 종목에 행을 넣을 수 없는데, 일괄 수집이 노리는 것이 그 바깥이다.
-- PK가 (기사, 티커)인 이유: 기사 하나가 여러 종목을 언급하고, 소비는 종목
-- 단위다. 겹치는 창을 다시 받아도 이 키가 중복을 흡수한다.
CREATE TABLE IF NOT EXISTS tb_news_raw (
  article_id BIGINT NOT NULL, ticker TEXT NOT NULL, trade_date DATE NOT NULL,
  headline TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (article_id, ticker)
);
-- 분석 잡이 매 실행 던지는 유일한 질문의 모양이다: 그 세션 · 이 종목들 ·
-- 최신순 N건. 원장이 하루 1400행씩 자라므로 순차 스캔으로 두면 곧 비싸진다.
CREATE INDEX IF NOT EXISTS ix_news_raw_session ON tb_news_raw (trade_date, ticker, published_at DESC);

-- Phase 4: 당일 시작 equity 스냅샷 — daily_loss_limit의 분모. 소비자는 배분
-- 잡의 계좌 게이트(같은 커밋). 하루 첫 기록이 이긴다 — 잡의 INSERT가
-- ON CONFLICT DO NOTHING이라 재실행이 아침 값을 덮지 않는다.
CREATE TABLE IF NOT EXISTS tb_account_equity_daily (
  account_id BIGINT NOT NULL REFERENCES tb_account(id), trade_date DATE NOT NULL,
  equity NUMERIC NOT NULL CHECK (equity >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, trade_date)
);

-- 웹 W1: 비밀번호 로그인. tb_user는 스키마만 있고 소비자가 0이던 테이블이라
-- 자격증명 필드가 otp_secret(2단계 TOTP용) 하나뿐이었다 — 비밀번호를 담을
-- 자리가 없었다. 해시만 담고 평문은 어디에도 남기지 않는다.
-- nullable인 이유: 관리자가 계정을 먼저 만들고 비밀번호를 나중에 정할 수
-- 있어야 한다. 해시가 없는 행은 "로그인할 수 없는 계정"이지 "아무 비밀번호나
-- 통하는 계정"이 아니다 — 검증 경로가 그것을 강제한다.
ALTER TABLE tb_user
  ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- 장중 사건 저장 계약. 모두 IF NOT EXISTS 또는 재생성 가능한 trigger라 재개 시
-- 중단 지점과 무관하게 같은 카탈로그로 수렴한다.
BEGIN;

-- PostgreSQL 16 정규 카탈로그 manifest v1. 이미 존재하는 객체는 이름만 같아도
-- 통과시키지 않는다. 빠진 table은 아래 DDL이 만들고, 빠진 function/trigger는
-- 데이터 audit 뒤 복원하지만, 동작이 다른 기존 객체는 operator가 먼저 제거한다.
DO $$
DECLARE
  mismatch TEXT;
BEGIN
  WITH expected(table_name, constraint_fingerprint, index_fingerprint) AS (
    VALUES
      ('tb_event_source_cursor','ee0b3732479d8c505891f3a280aeebe2','518fd3697c038975c5452885bbf9ef32'),
      ('tb_event_raw_document','89669b577dc901e62a0157a9ffacd87e','18bcbbb8a4571640a5a40443aa60e4ff'),
      ('tb_event_raw_version','2f69f42397ed28ad7f59aef7c061acce','41dd70251cac8c784303238549084098'),
      ('tb_normalized_event','732e9cf6008127fe96fa5c36c202228a','bd099a3e64d5587e49d448c76168d621'),
      ('tb_event_evidence_pack','47361641935d956672fd42dd30c1f5fd','e081b23fff49d0e5fffb695364deed81'),
      ('tb_event_summary_cache','c37a7b22190e1325c04e1aa7e7561b02','afadfc9caa44d0b2770c5a0460233409'),
      ('tb_event_processing_receipt','5cc41b57758ef8e3607406501c718c1e','9f8b132b3e4633a0d713bdce19f7b922')
  ),
  existing AS (
    SELECT class.oid, class.relname AS table_name
    FROM pg_class AS class
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    JOIN expected ON expected.table_name = class.relname
    WHERE namespace.nspname = 'public' AND class.relkind = 'r'
  ),
  constraint_entries AS (
    SELECT existing.table_name,
           catalog_constraint.conname || '|' ||
           catalog_constraint.contype::text || '|' ||
           catalog_constraint.convalidated || '|' ||
           catalog_constraint.condeferrable || '|' ||
           catalog_constraint.condeferred || '|' ||
           pg_get_constraintdef(catalog_constraint.oid, false) AS entry
    FROM existing
    JOIN pg_constraint AS catalog_constraint
      ON catalog_constraint.conrelid = existing.oid
  ),
  constraint_fingerprints AS (
    SELECT table_name, md5(string_agg(entry, E'\n' ORDER BY entry)) AS fingerprint
    FROM constraint_entries GROUP BY table_name
  ),
  index_entries AS (
    SELECT existing.table_name,
           index_class.relname || '|' || catalog.indisunique || '|' ||
           catalog.indisprimary || '|' || catalog.indisvalid || '|' ||
           coalesce(pg_get_expr(catalog.indpred, catalog.indrelid), '') || '|' ||
           pg_get_indexdef(catalog.indexrelid, 0, false) AS entry
    FROM existing
    JOIN pg_index AS catalog ON catalog.indrelid = existing.oid
    JOIN pg_class AS index_class ON index_class.oid = catalog.indexrelid
  ),
  index_fingerprints AS (
    SELECT table_name, md5(string_agg(entry, E'\n' ORDER BY entry)) AS fingerprint
    FROM index_entries GROUP BY table_name
  ),
  differences AS (
    SELECT existing.table_name
    FROM existing
    JOIN expected USING (table_name)
    LEFT JOIN constraint_fingerprints USING (table_name)
    LEFT JOIN index_fingerprints USING (table_name)
    WHERE (constraint_fingerprints.fingerprint, index_fingerprints.fingerprint)
      IS DISTINCT FROM
      (expected.constraint_fingerprint, expected.index_fingerprint)
  )
  SELECT string_agg(table_name, ', ' ORDER BY table_name) INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event constraint/index catalog: %', mismatch;
  END IF;

  WITH expected(table_name, column_name, expression) AS (
    VALUES
      ('tb_event_source_cursor','updated_at','now()'),
      ('tb_event_raw_document','document_id',
       'nextval(''tb_event_raw_document_document_id_seq''::regclass)'),
      ('tb_event_raw_document','first_seen_at','now()'),
      ('tb_event_raw_version','raw_version_id',
       'nextval(''tb_event_raw_version_raw_version_id_seq''::regclass)'),
      ('tb_event_raw_version','captured_at','now()'),
      ('tb_normalized_event','event_id',
       'nextval(''tb_normalized_event_event_id_seq''::regclass)'),
      ('tb_normalized_event','created_at','now()'),
      ('tb_event_evidence_pack','evidence_id',
       'nextval(''tb_event_evidence_pack_evidence_id_seq''::regclass)'),
      ('tb_event_evidence_pack','created_at','now()'),
      ('tb_event_summary_cache','summary_id',
       'nextval(''tb_event_summary_cache_summary_id_seq''::regclass)'),
      ('tb_event_summary_cache','created_at','now()'),
      ('tb_event_processing_receipt','receipt_id',
       'nextval(''tb_event_processing_receipt_receipt_id_seq''::regclass)'),
      ('tb_event_processing_receipt','claimed_at','now()')
  ),
  actual AS (
    SELECT class.relname AS table_name, attribute.attname AS column_name,
           pg_get_expr(default_value.adbin, default_value.adrelid) AS expression
    FROM pg_attrdef AS default_value
    JOIN pg_class AS class ON class.oid = default_value.adrelid
    JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
    JOIN pg_attribute AS attribute
      ON attribute.attrelid = class.oid
     AND attribute.attnum = default_value.adnum
    WHERE namespace.nspname = 'public'
      AND class.relname IN (
        'tb_event_source_cursor', 'tb_event_raw_document',
        'tb_event_raw_version', 'tb_normalized_event',
        'tb_event_evidence_pack', 'tb_event_summary_cache',
        'tb_event_processing_receipt'
      )
  ),
  differences AS (
    SELECT COALESCE(expected.table_name, actual.table_name) AS table_name,
           COALESCE(expected.column_name, actual.column_name) AS column_name
    FROM expected FULL JOIN actual USING (table_name, column_name)
    WHERE expected.expression IS DISTINCT FROM actual.expression
      AND (
        actual.table_name IS NOT NULL
        OR to_regclass('public.' || expected.table_name) IS NOT NULL
      )
  )
  SELECT string_agg(table_name || '.' || column_name, ', ' ORDER BY 1, 2)
    INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event default catalog: %', mismatch;
  END IF;

  WITH expected(function_name, source_fingerprint) AS (
    VALUES
      ('enforce_event_evidence_span','b7b49636c5bb5134e002a75a122e28cd'),
      ('enforce_normalized_event_source','a3c624ba1dec6bd404e51498350163b3'),
      ('reject_event_provenance_mutation','f0c933f2b332d19ec7d51866e2ad5a7b')
  ),
  actual AS (
    SELECT procedure.proname AS function_name, md5(procedure.prosrc) AS source_fingerprint,
           language.lanname, procedure.provolatile, procedure.prosecdef,
           procedure.prokind, procedure.pronargs
    FROM pg_proc AS procedure
    JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
    JOIN pg_language AS language ON language.oid = procedure.prolang
    JOIN expected ON expected.function_name = procedure.proname
    WHERE namespace.nspname = 'public'
  ),
  differences AS (
    SELECT actual.function_name
    FROM actual JOIN expected USING (function_name)
    WHERE actual.source_fingerprint IS DISTINCT FROM expected.source_fingerprint
       OR (actual.lanname, actual.provolatile, actual.prosecdef,
           actual.prokind, actual.pronargs)
          IS DISTINCT FROM ('plpgsql', 'v'::"char", false, 'f'::"char", 0::smallint)
  )
  SELECT string_agg(function_name, ', ' ORDER BY function_name) INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event function catalog: %', mismatch;
  END IF;

  WITH expected(trigger_name, definition) AS (
    VALUES
      ('trg_normalized_event_source',
       'CREATE TRIGGER trg_normalized_event_source BEFORE INSERT ON public.tb_normalized_event FOR EACH ROW EXECUTE FUNCTION enforce_normalized_event_source()'),
      ('trg_event_evidence_span',
       'CREATE TRIGGER trg_event_evidence_span BEFORE INSERT ON public.tb_event_evidence_pack FOR EACH ROW EXECUTE FUNCTION enforce_event_evidence_span()'),
      ('trg_event_raw_document_immutable',
       'CREATE TRIGGER trg_event_raw_document_immutable BEFORE DELETE OR UPDATE ON public.tb_event_raw_document FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation()'),
      ('trg_event_raw_version_immutable',
       'CREATE TRIGGER trg_event_raw_version_immutable BEFORE DELETE OR UPDATE ON public.tb_event_raw_version FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation()'),
      ('trg_normalized_event_immutable',
       'CREATE TRIGGER trg_normalized_event_immutable BEFORE DELETE OR UPDATE ON public.tb_normalized_event FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation()'),
      ('trg_event_evidence_immutable',
       'CREATE TRIGGER trg_event_evidence_immutable BEFORE DELETE OR UPDATE ON public.tb_event_evidence_pack FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation()'),
      ('trg_event_summary_immutable',
       'CREATE TRIGGER trg_event_summary_immutable BEFORE DELETE OR UPDATE ON public.tb_event_summary_cache FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation()')
  ),
  actual AS (
    SELECT trigger.tgname AS trigger_name,
           pg_get_triggerdef(trigger.oid, false) AS definition
    FROM pg_trigger AS trigger
    JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public' AND NOT trigger.tgisinternal
      AND relation.relname IN (
        'tb_event_source_cursor', 'tb_event_raw_document',
        'tb_event_raw_version', 'tb_normalized_event',
        'tb_event_evidence_pack', 'tb_event_summary_cache',
        'tb_event_processing_receipt'
      )
  ),
  differences AS (
    SELECT actual.trigger_name
    FROM actual LEFT JOIN expected USING (trigger_name)
    WHERE expected.trigger_name IS NULL
       OR expected.definition IS DISTINCT FROM actual.definition
  )
  SELECT string_agg(trigger_name, ', ' ORDER BY trigger_name) INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event trigger catalog: %', mismatch;
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS tb_event_source_cursor (
  source_name TEXT PRIMARY KEY,
  cursor_value TEXT NOT NULL,
  checkpoint_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT tb_event_source_cursor_source_name_check
    CHECK (length(btrim(source_name)) > 0),
  CONSTRAINT tb_event_source_cursor_cursor_value_check
    CHECK (length(btrim(cursor_value)) > 0)
);

CREATE TABLE IF NOT EXISTS tb_event_raw_document (
  document_id BIGSERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_document_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_event_raw_document_source UNIQUE (source_name, source_document_id),
  CONSTRAINT tb_event_raw_document_source_name_check
    CHECK (length(btrim(source_name)) > 0),
  CONSTRAINT tb_event_raw_document_source_document_id_check
    CHECK (length(btrim(source_document_id)) > 0)
);

CREATE TABLE IF NOT EXISTS tb_event_raw_version (
  raw_version_id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES tb_event_raw_document(document_id),
  version_no INT NOT NULL,
  content_hash TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  normalized_length INT NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_event_raw_version_number UNIQUE (document_id, version_no),
  CONSTRAINT uq_event_raw_version_hash UNIQUE (document_id, content_hash),
  CONSTRAINT uq_event_raw_version_summary_fk
    UNIQUE (raw_version_id, content_hash, normalized_length),
  CONSTRAINT tb_event_raw_version_version_no_check CHECK (version_no > 0),
  CONSTRAINT tb_event_raw_version_content_hash_check
    CHECK (length(btrim(content_hash)) > 0),
  CONSTRAINT tb_event_raw_version_normalized_length_check
    CHECK (
      normalized_length >= 0
      AND normalized_length = char_length(normalized_text)
    )
);

CREATE OR REPLACE FUNCTION reject_event_provenance_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
END;
$$;

CREATE TABLE IF NOT EXISTS tb_normalized_event (
  event_id BIGSERIAL PRIMARY KEY,
  raw_version_id BIGINT NOT NULL REFERENCES tb_event_raw_version(raw_version_id),
  event_key TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_sequence TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_normalized_event_key UNIQUE (event_key),
  CONSTRAINT uq_normalized_event_source_order UNIQUE (source_name, source_sequence),
  CONSTRAINT tb_normalized_event_event_key_check
    CHECK (length(btrim(event_key)) > 0),
  CONSTRAINT tb_normalized_event_source_name_check
    CHECK (length(btrim(source_name)) > 0),
  CONSTRAINT tb_normalized_event_source_sequence_check
    CHECK (length(btrim(source_sequence)) > 0),
  CONSTRAINT tb_normalized_event_event_type_check
    CHECK (length(btrim(event_type)) > 0)
);

CREATE TABLE IF NOT EXISTS tb_event_evidence_pack (
  evidence_id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES tb_normalized_event(event_id),
  raw_version_id BIGINT NOT NULL REFERENCES tb_event_raw_version(raw_version_id),
  start_offset INT NOT NULL,
  end_offset INT NOT NULL,
  quote_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_event_evidence_span
    UNIQUE (event_id, raw_version_id, start_offset, end_offset),
  CONSTRAINT tb_event_evidence_pack_offsets_check
    CHECK (start_offset >= 0 AND end_offset > start_offset),
  CONSTRAINT tb_event_evidence_pack_quote_hash_check
    CHECK (length(btrim(quote_hash)) > 0)
);

CREATE TABLE IF NOT EXISTS tb_event_summary_cache (
  summary_id BIGSERIAL PRIMARY KEY,
  raw_version_id BIGINT NOT NULL,
  content_hash TEXT NOT NULL,
  normalized_length INT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  summary_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_event_summary_raw_version
    FOREIGN KEY (raw_version_id, content_hash, normalized_length)
    REFERENCES tb_event_raw_version(raw_version_id, content_hash, normalized_length),
  CONSTRAINT uq_event_summary_cache_key
    UNIQUE (content_hash, model, prompt_version),
  CONSTRAINT tb_event_summary_cache_normalized_length_check
    CHECK (normalized_length > 12000),
  CONSTRAINT tb_event_summary_cache_content_hash_check
    CHECK (length(btrim(content_hash)) > 0),
  CONSTRAINT tb_event_summary_cache_model_check
    CHECK (length(btrim(model)) > 0),
  CONSTRAINT tb_event_summary_cache_prompt_version_check
    CHECK (length(btrim(prompt_version)) > 0),
  CONSTRAINT tb_event_summary_cache_summary_text_check
    CHECK (length(btrim(summary_text)) > 0)
);

CREATE TABLE IF NOT EXISTS tb_event_processing_receipt (
  receipt_id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES tb_normalized_event(event_id),
  ticker TEXT NOT NULL,
  persona TEXT NOT NULL,
  status TEXT NOT NULL,
  order_id BIGINT REFERENCES tb_order(id),
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT uq_event_processing_key UNIQUE (event_id, ticker, persona),
  CONSTRAINT tb_event_processing_receipt_ticker_check
    CHECK (length(btrim(ticker)) > 0),
  CONSTRAINT tb_event_processing_receipt_persona_check
    CHECK (length(btrim(persona)) > 0),
  CONSTRAINT tb_event_processing_receipt_status_check
    CHECK (status IN ('claimed','processed','skipped','ordered')),
  CONSTRAINT tb_event_processing_receipt_order_check
    CHECK ((status = 'ordered') = (order_id IS NOT NULL))
);

ALTER TABLE tb_normalized_event
  DROP CONSTRAINT IF EXISTS tb_normalized_event_source_name_check;
ALTER TABLE tb_normalized_event
  ADD CONSTRAINT tb_normalized_event_source_name_check
    CHECK (length(btrim(source_name)) > 0);

DO $$
DECLARE
  mismatch TEXT;
BEGIN
  WITH expected(table_name, column_name, data_type, required, default_kind) AS (
    VALUES
      ('tb_event_source_cursor','source_name','text',true,'none'),
      ('tb_event_source_cursor','cursor_value','text',true,'none'),
      ('tb_event_source_cursor','checkpoint_at','timestamp with time zone',true,'none'),
      ('tb_event_source_cursor','updated_at','timestamp with time zone',true,'now'),
      ('tb_event_raw_document','document_id','bigint',true,'nextval'),
      ('tb_event_raw_document','source_name','text',true,'none'),
      ('tb_event_raw_document','source_document_id','text',true,'none'),
      ('tb_event_raw_document','source_url','text',true,'none'),
      ('tb_event_raw_document','published_at','timestamp with time zone',true,'none'),
      ('tb_event_raw_document','first_seen_at','timestamp with time zone',true,'now'),
      ('tb_event_raw_version','raw_version_id','bigint',true,'nextval'),
      ('tb_event_raw_version','document_id','bigint',true,'none'),
      ('tb_event_raw_version','version_no','integer',true,'none'),
      ('tb_event_raw_version','content_hash','text',true,'none'),
      ('tb_event_raw_version','raw_text','text',true,'none'),
      ('tb_event_raw_version','normalized_text','text',true,'none'),
      ('tb_event_raw_version','normalized_length','integer',true,'none'),
      ('tb_event_raw_version','captured_at','timestamp with time zone',true,'now'),
      ('tb_normalized_event','event_id','bigint',true,'nextval'),
      ('tb_normalized_event','raw_version_id','bigint',true,'none'),
      ('tb_normalized_event','event_key','text',true,'none'),
      ('tb_normalized_event','source_name','text',true,'none'),
      ('tb_normalized_event','source_sequence','text',true,'none'),
      ('tb_normalized_event','event_type','text',true,'none'),
      ('tb_normalized_event','occurred_at','timestamp with time zone',true,'none'),
      ('tb_normalized_event','payload','jsonb',true,'none'),
      ('tb_normalized_event','created_at','timestamp with time zone',true,'now'),
      ('tb_event_evidence_pack','evidence_id','bigint',true,'nextval'),
      ('tb_event_evidence_pack','event_id','bigint',true,'none'),
      ('tb_event_evidence_pack','raw_version_id','bigint',true,'none'),
      ('tb_event_evidence_pack','start_offset','integer',true,'none'),
      ('tb_event_evidence_pack','end_offset','integer',true,'none'),
      ('tb_event_evidence_pack','quote_hash','text',true,'none'),
      ('tb_event_evidence_pack','created_at','timestamp with time zone',true,'now'),
      ('tb_event_summary_cache','summary_id','bigint',true,'nextval'),
      ('tb_event_summary_cache','raw_version_id','bigint',true,'none'),
      ('tb_event_summary_cache','content_hash','text',true,'none'),
      ('tb_event_summary_cache','normalized_length','integer',true,'none'),
      ('tb_event_summary_cache','model','text',true,'none'),
      ('tb_event_summary_cache','prompt_version','text',true,'none'),
      ('tb_event_summary_cache','summary_text','text',true,'none'),
      ('tb_event_summary_cache','created_at','timestamp with time zone',true,'now'),
      ('tb_event_processing_receipt','receipt_id','bigint',true,'nextval'),
      ('tb_event_processing_receipt','event_id','bigint',true,'none'),
      ('tb_event_processing_receipt','ticker','text',true,'none'),
      ('tb_event_processing_receipt','persona','text',true,'none'),
      ('tb_event_processing_receipt','status','text',true,'none'),
      ('tb_event_processing_receipt','order_id','bigint',false,'none'),
      ('tb_event_processing_receipt','claimed_at','timestamp with time zone',true,'now'),
      ('tb_event_processing_receipt','completed_at','timestamp with time zone',false,'none')
  ),
  actual AS (
    SELECT c.table_name, c.column_name, c.data_type,
           c.is_nullable = 'NO' AS required,
           CASE
             WHEN c.column_default IS NULL THEN 'none'
             WHEN c.column_default LIKE 'nextval(%' THEN 'nextval'
             WHEN c.column_default = 'now()' THEN 'now'
             ELSE c.column_default
           END AS default_kind
    FROM information_schema.columns AS c
    WHERE c.table_schema = 'public'
      AND c.table_name IN (
        'tb_event_source_cursor', 'tb_event_raw_document',
        'tb_event_raw_version', 'tb_normalized_event',
        'tb_event_evidence_pack', 'tb_event_summary_cache',
        'tb_event_processing_receipt'
      )
  ),
  differences AS (
    SELECT COALESCE(e.table_name, a.table_name) AS table_name,
           COALESCE(e.column_name, a.column_name) AS column_name
    FROM expected AS e
    FULL JOIN actual AS a USING (table_name, column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR (e.data_type, e.required, e.default_kind)
          IS DISTINCT FROM (a.data_type, a.required, a.default_kind)
  )
  SELECT string_agg(table_name || '.' || column_name, ', ' ORDER BY 1, 2)
    INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event column catalog: %', mismatch;
  END IF;

  WITH expected(table_name, constraint_name, constraint_type, fragment) AS (
    VALUES
      ('tb_event_source_cursor','tb_event_source_cursor_pkey','p','primary key (source_name)'),
      ('tb_event_source_cursor','tb_event_source_cursor_source_name_check','c','length(btrim(source_name)) > 0'),
      ('tb_event_source_cursor','tb_event_source_cursor_cursor_value_check','c','length(btrim(cursor_value)) > 0'),
      ('tb_event_raw_document','tb_event_raw_document_pkey','p','primary key (document_id)'),
      ('tb_event_raw_document','uq_event_raw_document_source','u','unique (source_name, source_document_id)'),
      ('tb_event_raw_document','tb_event_raw_document_source_name_check','c','length(btrim(source_name)) > 0'),
      ('tb_event_raw_document','tb_event_raw_document_source_document_id_check','c','length(btrim(source_document_id)) > 0'),
      ('tb_event_raw_version','tb_event_raw_version_pkey','p','primary key (raw_version_id)'),
      ('tb_event_raw_version','uq_event_raw_version_number','u','unique (document_id, version_no)'),
      ('tb_event_raw_version','uq_event_raw_version_hash','u','unique (document_id, content_hash)'),
      ('tb_event_raw_version','uq_event_raw_version_summary_fk','u','unique (raw_version_id, content_hash, normalized_length)'),
      ('tb_event_raw_version','tb_event_raw_version_document_id_fkey','f','references tb_event_raw_document(document_id)'),
      ('tb_event_raw_version','tb_event_raw_version_version_no_check','c','version_no > 0'),
      ('tb_event_raw_version','tb_event_raw_version_content_hash_check','c','length(btrim(content_hash)) > 0'),
      ('tb_event_raw_version','tb_event_raw_version_normalized_length_check','c','normalized_length = char_length(normalized_text)'),
      ('tb_normalized_event','tb_normalized_event_pkey','p','primary key (event_id)'),
      ('tb_normalized_event','tb_normalized_event_raw_version_id_fkey','f','references tb_event_raw_version(raw_version_id)'),
      ('tb_normalized_event','uq_normalized_event_key','u','unique (event_key)'),
      ('tb_normalized_event','uq_normalized_event_source_order','u','unique (source_name, source_sequence)'),
      ('tb_normalized_event','tb_normalized_event_event_key_check','c','length(btrim(event_key)) > 0'),
      ('tb_normalized_event','tb_normalized_event_source_name_check','c','length(btrim(source_name)) > 0'),
      ('tb_normalized_event','tb_normalized_event_source_sequence_check','c','length(btrim(source_sequence)) > 0'),
      ('tb_normalized_event','tb_normalized_event_event_type_check','c','length(btrim(event_type)) > 0'),
      ('tb_event_evidence_pack','tb_event_evidence_pack_pkey','p','primary key (evidence_id)'),
      ('tb_event_evidence_pack','tb_event_evidence_pack_event_id_fkey','f','references tb_normalized_event(event_id)'),
      ('tb_event_evidence_pack','tb_event_evidence_pack_raw_version_id_fkey','f','references tb_event_raw_version(raw_version_id)'),
      ('tb_event_evidence_pack','uq_event_evidence_span','u','unique (event_id, raw_version_id, start_offset, end_offset)'),
      ('tb_event_evidence_pack','tb_event_evidence_pack_offsets_check','c','end_offset > start_offset'),
      ('tb_event_evidence_pack','tb_event_evidence_pack_quote_hash_check','c','length(btrim(quote_hash)) > 0'),
      ('tb_event_summary_cache','tb_event_summary_cache_pkey','p','primary key (summary_id)'),
      ('tb_event_summary_cache','fk_event_summary_raw_version','f','references tb_event_raw_version(raw_version_id, content_hash, normalized_length)'),
      ('tb_event_summary_cache','uq_event_summary_cache_key','u','unique (content_hash, model, prompt_version)'),
      ('tb_event_summary_cache','tb_event_summary_cache_normalized_length_check','c','normalized_length > 12000'),
      ('tb_event_summary_cache','tb_event_summary_cache_content_hash_check','c','length(btrim(content_hash)) > 0'),
      ('tb_event_summary_cache','tb_event_summary_cache_model_check','c','length(btrim(model)) > 0'),
      ('tb_event_summary_cache','tb_event_summary_cache_prompt_version_check','c','length(btrim(prompt_version)) > 0'),
      ('tb_event_summary_cache','tb_event_summary_cache_summary_text_check','c','length(btrim(summary_text)) > 0'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_pkey','p','primary key (receipt_id)'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_event_id_fkey','f','references tb_normalized_event(event_id)'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_order_id_fkey','f','references tb_order(id)'),
      ('tb_event_processing_receipt','uq_event_processing_key','u','unique (event_id, ticker, persona)'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_ticker_check','c','length(btrim(ticker)) > 0'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_persona_check','c','length(btrim(persona)) > 0'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_status_check','c','status = any'),
      ('tb_event_processing_receipt','tb_event_processing_receipt_order_check','c','order_id is not null')
  ),
  actual AS (
    SELECT c.relname AS table_name, p.conname AS constraint_name,
           p.contype::text AS constraint_type,
           lower(pg_get_constraintdef(p.oid)) AS definition
    FROM pg_constraint AS p
    JOIN pg_class AS c ON c.oid = p.conrelid
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname IN (
        'tb_event_source_cursor', 'tb_event_raw_document',
        'tb_event_raw_version', 'tb_normalized_event',
        'tb_event_evidence_pack', 'tb_event_summary_cache',
        'tb_event_processing_receipt'
      )
  ),
  differences AS (
    SELECT COALESCE(e.table_name, a.table_name) AS table_name,
           COALESCE(e.constraint_name, a.constraint_name) AS constraint_name
    FROM expected AS e
    FULL JOIN actual AS a USING (table_name, constraint_name)
    WHERE e.constraint_name IS NULL OR a.constraint_name IS NULL
       OR e.constraint_type IS DISTINCT FROM a.constraint_type
       OR position(e.fragment IN a.definition) = 0
  )
  SELECT string_agg(table_name || '.' || constraint_name, ', ' ORDER BY 1, 2)
    INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event constraint catalog: %', mismatch;
  END IF;
END;
$$;

DO $$
DECLARE
  invalid_events BIGINT;
  invalid_evidence BIGINT;
BEGIN
  SELECT count(*) INTO invalid_events
  FROM tb_normalized_event AS event
  JOIN tb_event_raw_version AS version
    ON version.raw_version_id = event.raw_version_id
  JOIN tb_event_raw_document AS document
    ON document.document_id = version.document_id
  WHERE event.source_name IS DISTINCT FROM document.source_name;

  SELECT count(*) INTO invalid_evidence
  FROM tb_event_evidence_pack AS evidence
  JOIN tb_normalized_event AS event ON event.event_id = evidence.event_id
  JOIN tb_event_raw_version AS version
    ON version.raw_version_id = event.raw_version_id
  WHERE evidence.raw_version_id IS DISTINCT FROM event.raw_version_id
     OR evidence.end_offset > version.normalized_length;

  IF invalid_events > 0 OR invalid_evidence > 0 THEN
    RAISE EXCEPTION
      'incoherent pre-existing event provenance: events=%, evidence=%',
      invalid_events, invalid_evidence;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_normalized_event_source()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  expected_source TEXT;
BEGIN
  SELECT document.source_name INTO expected_source
  FROM tb_event_raw_version AS version
  JOIN tb_event_raw_document AS document
    ON document.document_id = version.document_id
  WHERE version.raw_version_id = NEW.raw_version_id;
  IF expected_source IS DISTINCT FROM NEW.source_name THEN
    RAISE EXCEPTION 'normalized event source does not match raw document';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_event_evidence_span()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  expected_version BIGINT;
  text_length INT;
BEGIN
  SELECT event.raw_version_id, version.normalized_length
    INTO expected_version, text_length
  FROM tb_normalized_event AS event
  JOIN tb_event_raw_version AS version
    ON version.raw_version_id = event.raw_version_id
  WHERE event.event_id = NEW.event_id;
  IF expected_version IS DISTINCT FROM NEW.raw_version_id THEN
    RAISE EXCEPTION 'evidence raw version does not match normalized event';
  END IF;
  IF NEW.end_offset > text_length THEN
    RAISE EXCEPTION 'evidence span exceeds normalized text length';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_event_raw_document_immutable
  ON tb_event_raw_document;
DROP TRIGGER IF EXISTS trg_event_raw_version_immutable
  ON tb_event_raw_version;
DROP TRIGGER IF EXISTS trg_normalized_event_source
  ON tb_normalized_event;
DROP TRIGGER IF EXISTS trg_normalized_event_immutable
  ON tb_normalized_event;
DROP TRIGGER IF EXISTS trg_event_evidence_span
  ON tb_event_evidence_pack;
DROP TRIGGER IF EXISTS trg_event_evidence_immutable
  ON tb_event_evidence_pack;
DROP TRIGGER IF EXISTS trg_event_summary_immutable
  ON tb_event_summary_cache;

CREATE TRIGGER trg_normalized_event_source
BEFORE INSERT ON tb_normalized_event
FOR EACH ROW EXECUTE FUNCTION enforce_normalized_event_source();
CREATE TRIGGER trg_event_evidence_span
BEFORE INSERT ON tb_event_evidence_pack
FOR EACH ROW EXECUTE FUNCTION enforce_event_evidence_span();
CREATE TRIGGER trg_event_raw_document_immutable
BEFORE UPDATE OR DELETE ON tb_event_raw_document
FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
CREATE TRIGGER trg_event_raw_version_immutable
BEFORE UPDATE OR DELETE ON tb_event_raw_version
FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
CREATE TRIGGER trg_normalized_event_immutable
BEFORE UPDATE OR DELETE ON tb_normalized_event
FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
CREATE TRIGGER trg_event_evidence_immutable
BEFORE UPDATE OR DELETE ON tb_event_evidence_pack
FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();
CREATE TRIGGER trg_event_summary_immutable
BEFORE UPDATE OR DELETE ON tb_event_summary_cache
FOR EACH ROW EXECUTE FUNCTION reject_event_provenance_mutation();

DO $$
DECLARE
  mismatch TEXT;
BEGIN
  WITH expected(trigger_name, table_name, fragment) AS (
    VALUES
      ('trg_normalized_event_source','tb_normalized_event','before insert'),
      ('trg_event_evidence_span','tb_event_evidence_pack','before insert'),
      ('trg_event_raw_document_immutable','tb_event_raw_document','before delete or update'),
      ('trg_event_raw_version_immutable','tb_event_raw_version','before delete or update'),
      ('trg_normalized_event_immutable','tb_normalized_event','before delete or update'),
      ('trg_event_evidence_immutable','tb_event_evidence_pack','before delete or update'),
      ('trg_event_summary_immutable','tb_event_summary_cache','before delete or update')
  ),
  actual AS (
    SELECT trigger.tgname AS trigger_name, relation.relname AS table_name,
           lower(pg_get_triggerdef(trigger.oid)) AS definition
    FROM pg_trigger AS trigger
    JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND NOT trigger.tgisinternal
      AND relation.relname IN (
        'tb_event_source_cursor', 'tb_event_raw_document',
        'tb_event_raw_version', 'tb_normalized_event',
        'tb_event_evidence_pack', 'tb_event_summary_cache',
        'tb_event_processing_receipt'
      )
  ),
  differences AS (
    SELECT COALESCE(e.trigger_name, a.trigger_name) AS trigger_name
    FROM expected AS e
    FULL JOIN actual AS a USING (trigger_name, table_name)
    WHERE e.trigger_name IS NULL OR a.trigger_name IS NULL
       OR position(e.fragment IN a.definition) = 0
  )
  SELECT string_agg(trigger_name, ', ' ORDER BY trigger_name)
    INTO mismatch
  FROM differences;
  IF mismatch IS NOT NULL THEN
    RAISE EXCEPTION 'incompatible event trigger catalog: %', mismatch;
  END IF;
END;
$$;

DROP FUNCTION IF EXISTS reject_event_raw_version_mutation();

COMMIT;
