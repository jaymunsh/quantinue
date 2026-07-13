# Task 8 cleanup receipt

- Docker project: `quantinue-task8`
- Isolated ports used: UI `127.0.0.1:18011`, PostgreSQL `127.0.0.1:55444`
- Smoke results: `/health` returned mock/mock OK; `/` rendered the control room; `/api/runs` completed an NVDA fixture run.
- Cleanup: `docker compose -p quantinue-task8 -f .omo/evidence/task-8-compose.yaml down -v` removed both containers, the project network, and `quantinue-task8_task8_pgdata`.
- Post-cleanup inspection found no `quantinue-task8` containers. Pre-existing services on ports 8011, 5432, and 55432 remained present and untouched.
- Local state-harness and regular QA uvicorn processes on port 8765 were stopped after capture.
