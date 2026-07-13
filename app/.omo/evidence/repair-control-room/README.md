# Control-room timed-out repair evidence

- Regression boundary: a persisted `timed_out` attempt is projected to a safe `failed` stage status while the attempt entry retains `timed_out`; both `GET /` and `GET /api/runs/{run_id}` return 200.
- Browser captures: `timed-out-mobile.png`, `timed-out-tablet.png`, and `timed-out-desktop.png` are fresh live-server screenshots from the persisted timed-out fixture.
- Responsive checks: 390, 768, and 1280 px have no document-level horizontal overflow. The exact Korean safety copy is visible at every viewport.
- Isolation: the server listened only on `127.0.0.1:18082`; no Docker service or PostgreSQL port was used.
