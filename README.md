# Health OS

Health OS is a calm, self-hosted health dashboard for individuals and households. Each household member gets a private PIN, timezone, plan, preferences, and health history. It works on phones, tablets, desktop browsers, and trusted embedded displays, emphasizing flexible routines and trend-based feedback without shame, calorie counting, analytics, or cloud dependencies.

## What is included

- Mobile-first Today screen with one next-best action, optimistic one-tap check-ins, undo, intentional skip, minimum exercise versions, daily completion, weekly rhythm, and trend-aware weight context.
- Weekend-aware Standard Day, Relaxed Friday, Relaxed Saturday, and Sunday Reset schedules.
- Week grid, responsive progress charts, editable/pausable plan, settings, easy-meal suggestions, and JSON/CSV exports.
- Weight, sleep, exercise, nutrition, hydration, caffeine, alcohol, reminders, external sensor mappings, callouts, settings, and audit persistence.
- Deterministic callouts with a hard maximum of one highest-priority and two secondary items. Alcohol plus possible driving always becomes the top safety callout and never estimates BAC or says driving is safe.
- Private household profiles distinguished by unique Argon2-hashed PINs, with admin-managed member creation and user-owned first-time setup.
- HttpOnly/SameSite sessions, CSRF double-submit protection, configurable Secure cookies and expiry, and failed-login rate limiting.
- Optional server-side external sensor adapter with connection testing and read-only discovery.
- SQLite migrations, Docker health check, persistent volumes, security headers, local backups, and portable exports.

## Architecture

`frontend/` is React 19 + TypeScript + Vite, TanStack Query, Lucide, and Recharts. `backend/` is FastAPI, Pydantic, SQLAlchemy, SQLite, and Argon2. FastAPI serves the compiled SPA and REST API at one origin. Business rules live in `backend/services.py`, independently of transport and storage configuration; `DATABASE_URL` can point to PostgreSQL after installing its driver.

The schema is normalized around `app_profile`, `habits`, `habit_schedules`, `daily_tasks`, `task_completions`, `exercise_sessions`, `meal_checkins`, `hydration_entries`, `caffeine_entries`, `alcohol_entries`, `sleep_entries`, `weight_entries`, `callouts`, `callout_dismissals`, `settings`, `reminder_rules`, `external_entity_mappings`, and `audit_events`. Plan items are archived instead of erasing historical check-ins.

## Local development

Python 3.12 and Node 22 are recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

In a second terminal, from the repository root:

```bash
npm install
npm run dev
```

The root `package.json` is an npm workspace that installs and runs the frontend. Do not mix
pnpm and npm in the same working tree; if switching package managers, remove existing
`node_modules` directories first.

Open `http://localhost:5173`. API docs are at `http://localhost:8000/docs`. To run the production build locally, build the frontend and start Uvicorn from the repository root; it will serve `frontend/dist`.

## Docker deployment

Copy the example environment file, choose host directories for persistent data and backups, and set a long random `SESSION_SECRET`:

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f health-os
```

Open `http://localhost:8080` or replace `localhost` with the server's address. Data is stored in `/data/health-os.db` inside the container and in the host directory configured by `DATA_DIR`; backups use `BACKUP_HOST_DIR`. The startup command applies migrations before serving traffic.

The image runs as a non-root user for security. Most Docker installations handle this normally. If a Linux or NAS bind mount reports “permission denied” or a read-only database, make the configured data and backup directories writable by container UID `10001`.

## Login and setup behavior

The first visitor completes an onboarding wizard and becomes the household admin. The admin can create another member with only a name and temporary PIN. On first sign-in, that member chooses their timezone, baselines, targets, and private replacement PIN. All member data and preferences are isolated. Only the admin can manage household members and embedding permissions.

Only Argon2 PIN hashes are stored in SQLite. “Keep me signed in” uses `KEEP_SIGNED_IN_DAYS`; otherwise sessions use `SESSION_TIMEOUT_MINUTES`. Set `SESSION_SECURE=true` when the app is served through HTTPS. Deployment secrets are intentionally never returned by `/api/settings`.

## Allow Embedding

Open Settings, enable **Allow Health OS to be embedded**, and enter the exact trusted origins that may frame it. This works with any dashboard, kiosk, portal, or local site that supports iframes—not one specific platform.

Standard HTML example:

```html
<iframe src="http://health-os.local:8080/?embedded=true" title="Health OS"></iframe>
```

Dashboard systems that use iframe-card YAML can use:

```yaml
type: iframe
url: http://health-os.local:8080/?embedded=true
aspect_ratio: 100%
```

`?embedded=true` uses compact top spacing and the mobile bottom navigation. Safe-area padding supports notched iPhones. The content security policy keeps other protections enabled while allowing only the origins saved in Settings.

Browsers block an HTTP iframe when its parent dashboard is loaded through HTTPS (mixed content). Prefer serving both through compatible HTTPS endpoints—often via the same trusted reverse proxy—or access both consistently through trusted local HTTP URLs. If the frame is blank, inspect the browser console and verify that the parent origin, including scheme and port, exactly matches an origin saved under Allow Embedding.

## Optional external sensor integration

Health OS includes an optional server-side adapter for compatible home-automation sensor APIs. It is separate from embedding and is not needed to use the application. Tokens stay on the backend, sensor access is read-only, and Health OS does not create entities or modify external configuration.

## Backup, restore, and export

Create a backup with `python scripts/backup.py` or `POST /api/backup`. Retention is controlled by `BACKUP_RETENTION_DAYS`. For a daily backup, schedule this command with the NAS scheduler or cron against the running container:

```bash
docker exec health-os python /app/scripts/backup.py
```

To restore: stop the container, copy a chosen backup to `${DATA_DIR}/health-os.db`, ensure the container can write the restored file, and restart. Never replace SQLite while the app is running. Settings links export JSON or CSV for weight, sleep, exercise, and completions; API routes are `/api/export/json` and `/api/export/{weight|sleep|exercise|habits}.csv`.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:////data/health-os.db` in Compose |
| `TZ` / `TIMEZONE` | Local schedule timezone | `America/Chicago` |
| `SESSION_SECRET` | Cookie signing secret | required by Compose |
| `SESSION_SECURE` | HTTPS-only cookie | `false` |
| `SESSION_TIMEOUT_MINUTES` | Standard session duration | `120` |
| `KEEP_SIGNED_IN_DAYS` | Remembered session duration | `30` |
| `FRAME_ANCESTORS` | First-run allowed iframe origins; editable in Settings | empty |
| `EMBEDDED_MODE` | Compact embedded default | `false` |
| `BACKUP_DIR`, `BACKUP_RETENTION_DAYS` | Backup destination and retention | `/backups`, `14` |
| `PHOTO_UPLOADS_ENABLED` | Locally stored meal photos | `false` |
| `INTEGRATION_ENABLED`, `INTEGRATION_BASE_URL`, `INTEGRATION_TOKEN`, `INTEGRATION_VERIFY_SSL` | Optional external sensor API | disabled |

## Security and privacy

There is no telemetry, analytics, CDN, remote font, or external API requirement. Run Health OS only on a trusted home network or behind an authenticated HTTPS reverse proxy. Use a strong unique PIN and session secret; do not commit `.env`. `FRAME_ANCESTORS` is deliberately scoped rather than disabling frame protection globally. X-Content-Type-Options, Referrer-Policy, Permissions-Policy, CSP, HttpOnly cookies, CSRF checks, validation, structured logs, and login throttling are enabled.

## Testing and mobile QA

```bash
ruff check backend tests scripts
pytest
cd frontend
npm run lint
npm test
npm run build
docker build -t health-os .
```

Test narrow and wide iPhone sizes, iPad portrait/landscape, desktop light/dark themes, reduced motion, keyboard navigation, VoiceOver task states, and both standalone and `?embedded=true` routes. Charts include screen-reader summaries and empty states.

## Troubleshooting

- **Database is read-only:** ensure the mounted data and backup directories are writable by UID 10001.
- **Container is unhealthy:** check `docker compose logs`; verify migration access and `/api/health`.
- **Login loops over HTTPS:** set `SESSION_SECURE=true` and ensure the proxy forwards cookies without rewriting SameSite.
- **External sensor connection fails:** verify the base URL is reachable from the container and the server-side token and TLS settings are correct.
- **DST/time looks wrong:** keep `TZ`/`TIMEZONE` at `America/Chicago`; schedules use IANA timezone rules, including daylight-saving transitions.

Health OS provides lifestyle organization, not diagnosis or emergency care. Safety callouts intentionally recommend conservative choices without claiming medical certainty.

## License

Health OS is available under the [MIT License](LICENSE). You may use, copy, modify, publish, distribute, sublicense, sell, or fork it subject to the license notice.
