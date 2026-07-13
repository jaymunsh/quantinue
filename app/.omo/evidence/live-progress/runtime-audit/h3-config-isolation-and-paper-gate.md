# H3 Runtime Audit — Configuration Isolation and Paper-Trading Fail-Closed Gate

## Verdict: CONFIRMED

The audit used a fresh temporary working directory and `SettingsConfigDict(env_file=None)`. It did not open, parse, or disclose the operator `.env`; it used only controlled placeholder values and removed temporary directories automatically.

| Hypothesis | Runtime evidence | Result |
| --- | --- | --- |
| Test isolation is deterministic despite conflicting local provider/database settings. | Applying the exact `tests/conftest.py` runtime gate produced `mock/fixture/memory/mock/trading=false` in a no-dotenv settings instance. | CONFIRMED |
| Missing paper credentials or control-room token fails before composition/use. | Controlled construction rejected missing API key, enabled trading without Alpaca mode, and enabled Alpaca without the token. | CONFIRMED |
| Paper-mode mutation remains protected at the actual HTTP boundary. | `TestClient` observed `POST /api/runs` without token → HTTP 403. Same-origin form request with a valid controlled token proceeded to the ordinary invalid-ticker response. | CONFIRMED |

Focused regression: `22 passed in 1.19s` (`tests/unit/test_config.py`, `tests/unit/test_control_room_access.py`).

Cleanup: no Docker, PostgreSQL, network provider, `.env`, source, or test changes; all temporary probe directories were removed.
