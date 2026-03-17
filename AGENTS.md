# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the FastAPI backend: `api/v1/endpoints/` for routes, `services/` for business logic, `models/` for SQLAlchemy models, `schemas/` for Pydantic types, and `agents/` for LLM workflows. `alembic/` stores database migrations. `tests/` holds pytest suites such as `test_auth.py` and `test_questions.py`. `frontend/` contains the Vue 3 client, with views under `frontend/src/views/`, shared layout/router code in `frontend/src/layouts/` and `frontend/src/router/`, and styles in `frontend/src/assets/styles/`. Deployment files live at the repo root: `docker-compose.yml`, `docker-compose.webui.yml`, `Dockerfile`, and `nginx.conf`.

## Build, Test, and Development Commands
Use `make dev` to run the backend locally with auto-reload on port 8000. Use `make up` and `make down` to start or stop the Docker Compose stack. Run `make build` to rebuild containers, `make migrate` to apply Alembic migrations, and `make migrate-create msg="add_user_flag"` to generate a revision. Run backend tests with `make test` or `pytest tests/ -v`, and lint with `make lint`. For the frontend, use `cd frontend && npm install`, `npm run dev`, and `npm run build`.

## Coding Style & Naming Conventions
Follow existing style: 4-space indentation in Python and 2-space indentation in Vue, TypeScript, HTML, and CSS. Prefer `snake_case` for Python modules and functions, `PascalCase` for Vue view files like `Dashboard.vue`, and descriptive service names like `question_service.py`. Keep route modules feature-scoped under `app/api/v1/endpoints/`. Lint Python with Ruff (`ruff check app/ --select E,F,W --ignore E501`).

## Testing Guidelines
Pytest is configured in `pytest.ini` with `testpaths = tests` and `python_files = test_*.py`. Add tests alongside the affected feature area and keep file names in the `test_<feature>.py` pattern. Cover new endpoints, service logic, and migration-sensitive behavior. For frontend changes, at minimum verify the affected flow locally with `npm run dev` and note the manual checks in the PR.

## Commit & Pull Request Guidelines
Commit messages should use Conventional Commits, as seen in history: `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`. Keep each commit focused on one change. Pull requests should include a short description, impacted modules, test evidence (`make test`, `make lint`, frontend build status), linked issues if any, and screenshots for UI changes. Highlight new environment variables, migrations, and deployment steps explicitly.

## Security & Configuration Tips
Start from `.env.example` and keep secrets out of Git. Review `app/core/config.py` when adding settings. Change default credentials before deployment, and document any changes that affect Docker, nginx, or external services such as PostgreSQL, Milvus, MinIO, Redis, RabbitMQ, or the LLM endpoint.
