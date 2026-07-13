# Task 8 browser-tooling audit

- Runtime/production dependency audit: `npm audit --omit=dev` reports **0 vulnerabilities**.
- QA tooling audit: **17 moderate**, **0 high**, **0 critical** after pinning both `playwright` and `@playwright/test` to `1.55.1`.
- Remaining advisory: `GHSA-8988-4f7v-96qf`, unbounded W3C baggage allocation in `@opentelemetry/core <2.8.0`.
- Dependency path: development-only `lighthouse 12.8.2` → `@sentry/node` → OpenTelemetry instrumentation/resources/core packages.
- npm reports a force-fix path to `lighthouse 12.6.1`, outside the pinned range and a downgrade. It was not applied because browser QA dependencies are development-only, production audit is clean, and the suggested change is not a safe forward upgrade.
- Full machine-readable audit: `.omo/evidence/task-8-npm-audit.json`.
