# Repository Guidelines

## Project Structure & Module Organization

The active application has two primary modules:

- `data-agent-python-backend/`: FastAPI and LangGraph backend. Application code lives in `app/`; tests are in `tests/`; demo-data utilities are in `scripts/`; the restricted Python runtime is defined in `sandbox/python/`.
- `data-agent-frontend/`: Electron, React, and TypeScript client. UI code is in `src/`, Electron entry points are in `electron/`, and static assets are under `src/assets/` and `public/`.

Architecture notes and product references live in `docs/`. Treat `data-agent-backend/` and the root Maven files as legacy/reference code unless a task explicitly targets them. Do not hand-edit generated files such as `dist-electron/`, `checkpoints.db`, or Chroma index data.

## Build, Test, and Development Commands

Backend commands run from `data-agent-python-backend/`:

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run pytest tests/test_sql_policy.py -q
docker build -t data-agent-python-sandbox:latest sandbox/python
```

Frontend commands run from `data-agent-frontend/`:

```bash
npm ci
npm run dev
npm run lint
npm run build
```

## Coding Style & Naming Conventions

Python targets 3.11, uses four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes. Ruff configuration sets a 120-character line limit. Keep blocking database, file, or SDK work off the event loop. TypeScript uses strict mode, two-space indentation, single quotes, semicolon-free style, `PascalCase` components, and `camelCase` values. Add comments only when they explain non-obvious control flow or safety constraints.

## Testing Guidelines

Backend tests use `pytest` and `pytest-asyncio`; name files `test_<feature>.py` and tests `test_<behavior>`. Add regression coverage for bug fixes, especially around SQL safety, retrieval, context compaction, parallel tools, persistence, and SSE recovery. Run the focused test first, then the complete suite. Frontend changes must pass both lint and build; include manual verification for streaming, review, and navigation behavior.

## Commit & Pull Request Guidelines

Recent commits use short, imperative Chinese summaries. Keep each commit focused. PR titles must use a semantic prefix such as `feat:`, `fix:`, `refactor:`, `docs:`, or `test:`. PRs should explain the problem, implementation, verification commands, related issue, configuration/schema impact, and screenshots for visible UI changes.

## Security & Configuration

Use `DATA_AGENT_` environment variables; never commit API keys or production credentials. Keep business-database accounts read-only. Do not weaken SQLGlot validation, prompt-injection checks, Docker isolation, or result-size limits without tests and an explicit rationale.
