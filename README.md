# PulseWatch

Know when your services go silent.

PulseWatch is a small, real website and API monitoring service. An administrator configures public HTTP/HTTPS endpoints. A backend engine performs live health checks, stores history, opens and recovers incidents, calculates uptime, and publishes a client-facing status page.

Monitor → Detect → Analyze → Inform

## 1. Project Overview

PulseWatch is a Flask application with a public landing page, a public service status experience, and a protected admin control center. There is a single administrator account. Clients do not sign up.

## 2. Problem Statement

Services fail quietly. Teams need a simple way to watch public URLs, notice when they stop answering correctly, and share an honest status page with people who depend on those services.

## 3. Product Purpose

PulseWatch continuously checks configured websites and APIs, records availability and response time, detects incidents, and exposes safe health information to clients.

## 4. Client + Admin Architecture

| Side | Who | Access |
| --- | --- | --- |
| Public client | Anyone | `/`, `/status`, `/status/service/<id>`, `/api/public/status`, `/health` |
| Admin / operator | Single owner | `/login` then `/dashboard`, `/monitors`, `/incidents`, `/analytics`, `/settings` |

There is no multi-user auth, no OAuth, and no client signup. Credentials live in environment variables as a username plus a password hash.

```
Developer/Admin → GitHub → GitHub Actions → Tests → Docker Build → Azure → PulseWatch Server → Monitoring Engine → Websites/APIs

Client → Public Status Page → PulseWatch Backend → Real Monitoring Data
```

Conceptual layout:

```
                    PULSEWATCH
                         |
          ┌──────────────┴──────────────┐
          |                             |
       CLIENT                         ADMIN
          |                             |
   Public Status                  Admin Dashboard
          |                             |
          └──────────────┬──────────────┘
                         ↓
                  Flask Backend
                         ↓
                Monitoring Engine
                         ↓
                  HTTP/HTTPS Checks
                         ↓
              Websites / APIs
                         ↓
                     SQLite
                         ↓
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
   Analytics         Incidents       Recommendations
```

## 5. Features

- Real HTTP/HTTPS health checks (not browser timers)
- Configurable interval, timeout, and expected status code
- Manual check, enable/disable, edit, and delete
- Incident open / no-duplicate / recover lifecycle
- Uptime and response-time analytics from stored checks
- Admin diagnostic recommendations (possible cause / recommended check)
- Public status page and JSON API for **public** monitors only
- SSRF protections on stored URLs and on every outbound check
- Docker, Compose, GitHub Actions, Azure App Service notes

## 6. Technology Stack

Python, Flask, SQLite, SQLAlchemy, Jinja, CSS, JavaScript, APScheduler, Requests, pytest, Docker, Docker Compose, GitHub Actions.

## 7. Project Structure

```
pulsewatch/
├── app.py
├── wsgi.py
├── config.py
├── extensions.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── models/
├── routes/
├── services/
├── templates/
├── static/
├── tests/
├── scripts/hash_password.py
└── .github/workflows/ci.yml
```

## 8. Local Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # or cp .env.example .env
python scripts/hash_password.py
# paste the hash into PULSEWATCH_PASSWORD_HASH in .env
python app.py
```

Open http://127.0.0.1:5000

## 9. Environment Variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session signing |
| `PULSEWATCH_USERNAME` | Admin username |
| `PULSEWATCH_PASSWORD_HASH` | Werkzeug password hash |
| `PULSEWATCH_ENV` | `development` or `production` |
| `DATABASE_URL` | SQLAlchemy URL (SQLite by default) |
| `SESSION_COOKIE_SECURE` | `true` behind HTTPS |
| `PORT` | Listen port (default 5000) |
| `PULSEWATCH_HIGH_LATENCY_MS` | Degraded threshold (default 800) |

Never commit a real `.env` file.

## 10. Authentication

Session-based, single administrator. Protected routes redirect to `/login`. Logout clears the session and returns to `/`.

## 11. Monitoring Workflow

1. Admin adds a public HTTP/HTTPS URL.
2. PulseWatch validates the URL (SSRF rules) and stores the monitor.
3. APScheduler ticks while the process is running and checks enabled monitors when their interval is due.
4. Each check records HTTP status, response time, UP/DOWN, and history.
5. Incidents and recommendations update from those results.

## 12. Incident Lifecycle

- **UP → DOWN**: open one active incident
- **DOWN → DOWN**: do not open another
- **DOWN → UP**: mark recovered and record duration

## 13. Recommendation Engine

Not a chatbot. After checks, the backend writes admin-only guidance for timeouts, connection errors, HTTP 4xx/5xx, high latency, low uptime, and recovery. Language is “possible cause” / “recommended check”, not claimed root cause. Public pages never show these diagnostics.

## 14. Public Status Page

`/status` lists enabled monitors marked Public. Overall status is computed:

- **operational** — all public enabled services are UP and not slow
- **degraded** — none are DOWN, but at least one is unknown or slower than the latency threshold
- **down** — at least one public enabled service is DOWN

Clients see availability language only. Private monitors are omitted from HTML, detail routes, and `/api/public/status`.

## 15. Running Tests

```bash
pip install -r requirements.txt
pytest -q
```

Tests mock DNS and HTTP. They do not require live third-party websites.

## 16. Running with Docker

Create `.env` from `.env.example` (username + password hash required).

```bash
docker compose up --build
```

The app listens on port **5000**. SQLite is stored on the `pulsewatch-data` volume so checks survive container restarts.

## 17. GitHub Actions CI/CD

`.github/workflows/ci.yml` runs on push and pull request: checkout, Python 3.12, install, pytest, Docker image build. Azure credentials are not required for this workflow.

## 18. Azure Deployment

Suitable for **Azure App Service (Web App for Containers)** with a single instance.

Suggested settings:

- `WEBSITES_PORT=5000`
- `PULSEWATCH_ENV=production`
- `SESSION_COOKIE_SECURE=true`
- `SECRET_KEY`, `PULSEWATCH_USERNAME`, `PULSEWATCH_PASSWORD_HASH`
- `DATABASE_URL=sqlite:////home/data/pulsewatch.db` (or an Azure Files mount)

SQLite is cost-conscious but the container filesystem is ephemeral unless you mount durable storage. Run **one** instance/worker so APScheduler does not duplicate checks.

Do not use Kubernetes or Terraform for this design.

## 19. Security / SSRF Protection

Outbound checks allow only `http`/`https` without embedded credentials. Localhost, loopback, private, link-local, reserved, multicast, and cloud metadata destinations are rejected at save time and again at check time, including redirect targets.

## 20. API Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | No | Liveness `{ "status": "healthy", "service": "PulseWatch" }` |
| GET | `/api/public/status` | No | Public overall status and services |
| GET | `/` | No | Landing |
| GET | `/status` | No | Client status page |
| GET | `/status/service/<id>` | No | Public service detail |
| GET/POST | `/login` | No | Admin login |
| GET | `/logout` | Session | Logout |
| GET | `/dashboard` `/monitors` `/incidents` `/analytics` `/settings` | Admin | Control center |

## 21. Screenshots

Capture locally after first run:

- Landing (`/`)
- Public status (`/status`)
- Admin dashboard (`/dashboard`)
- Monitors (`/monitors`)

Place images under `docs/` if you publish the repo.

## 22. Future Improvements

- Email or webhook notifications
- Multi-region check probes
- Durable PostgreSQL for larger deployments
- Maintenance windows on the public status page
- Read-only API tokens for status widgets
