# Health OS

Health OS is a calm, self-hosted personal health dashboard for routines, hydration, weight, sleep, exercise, and progress. It is designed for quick daily check-ins, private per-user data, and encouraging feedback without shame, calorie counting, telemetry, or cloud dependencies.

Health OS supports two deployment modes:

- **Standalone:** each person signs in with a unique PIN. Accounts are independent; there is no household administrator or member-management screen.
- **Home Assistant app:** Home Assistant Ingress signs each Home Assistant user into a separate Health OS account using their stable Home Assistant user ID. No PIN is required, although a user may add one for optional standalone access to the same account.

Identity providers are never matched by display name. Linking another sign-in method is an explicit, authenticated action, so people with similar names cannot accidentally share health data.

## Features

- Mobile-first Today screen with one-tap task, water, weight, sleep, and exercise check-ins.
- Intentional skip with undo, minimum exercise versions, editable plans, and time-sorted tasks.
- Weight goals and trends, weekly rhythm, responsive charts, meals, exports, and local backups.
- User-scoped timezone, caffeine cutoff, water target, reminder preferences, and quiet hours.
- Temporary travel timezone with automatic expiry and an explicit permanent-timezone choice.
- Durable UTC reminder schedules recalculated from each user's active timezone, including daylight-saving transitions.
- HttpOnly/SameSite sessions, CSRF protection, Argon2 PIN hashes, login throttling, and strict Home Assistant proxy trust.
- SQLite migrations that preserve existing profile IDs, PIN hashes, settings, and health history.

Health OS provides lifestyle organization, not diagnosis or emergency care.

## Architecture

The frontend uses React, TypeScript, Vite, TanStack Query, Lucide, and Recharts. The backend uses FastAPI, Pydantic, SQLAlchemy, SQLite, and Argon2. FastAPI serves the compiled SPA and REST API at one origin. The schema uses normalized profiles and external identities so authentication is separate from user-owned health records.

All persisted instants are UTC. Each user has an IANA timezone such as `America/Chicago`; local-day boundaries, weekday schedules, and reminder times are calculated from that timezone. Completed tasks retain their original local date and timezone so later timezone changes do not rewrite history. During the spring DST gap, a nonexistent scheduled time advances to the next valid local minute; during the autumn overlap, the first occurrence is used.

## Standalone development

Python 3.12 and Node 22 are recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`; API docs are at `http://localhost:8000/docs`. The root npm workspace manages the frontend. Do not mix pnpm and npm in one working tree.

## Standalone Docker deployment

```bash
cp .env.example .env
# Replace SESSION_SECRET with a long random value.
docker compose up -d --build
```

Open `http://localhost:8080`. Data is stored in the host directory selected by `DATA_DIR`; backups use `BACKUP_HOST_DIR`. Startup applies database migrations before serving traffic. The container runs as a non-root user. If a bind mount is not writable, grant the container write access using the normal ownership or ACL controls for your Docker/NAS platform; no application user ID is involved.

Standalone mode requires `SESSION_SECRET`. The first visitor creates a PIN account through the onboarding wizard. Additional people choose **Create private account** and receive completely independent data and preferences.

## Home Assistant app deployment

Add this GitHub repository as a Home Assistant app repository, install **Health OS**, start it, and select **Open Web UI**. Packaging is in `home-assistant-app/config.yaml`; the repository metadata is in `repository.yaml`.

The app:

- uses Ingress and exposes no host port;
- is available to non-admin Home Assistant users (`panel_admin: false`);
- accepts identity headers only in Home Assistant deployment mode and only from the configured Supervisor proxy network;
- keys accounts by stable Home Assistant user ID, while names remain informational;
- stores its SQLite database and generated session secret under `/data`;
- supports `amd64` and `aarch64` images published to GHCR.

Opening the container port directly is unsupported in Home Assistant mode because trusted Ingress identity headers are absent. Logging out clears the Health OS session; opening it again through Ingress signs the Home Assistant user back in. Removing a Health OS account deletes only that user's local Health OS data and does not change the Home Assistant account.

Home Assistant notification delivery uses a user-configured `notify.*` target and the Supervisor Core API. A configured reminder is recorded as sent only after successful delivery. If Home Assistant or the target is unavailable, the failure is retained for retry/diagnostics rather than reported as delivered.

## Timezone and travel behavior

The browser timezone is offered during onboarding in a friendly searchable dropdown, but the user confirms it. Settings show the active timezone and can warn when the browser and saved timezone differ. The user can keep the saved zone, switch permanently, or use the browser zone temporarily for seven days. Temporary travel mode automatically expires and reminder UTC schedules are recalculated without changing historical local dates.

Wake and sleep task times remain editable plan entries rather than duplicated global settings. Friday and Saturday reminder behavior and cross-midnight quiet hours are user scoped.

For example, the same local reminder remains personal even when users share one server:

```text
User 1
Health OS timezone: America/Chicago
Water reminder: 10:00 AM Central

User 2
Health OS timezone: America/Phoenix
Water reminder: 10:00 AM Arizona time
```

## Backup, restore, and export

Create a backup with `python scripts/backup.py` or `POST /api/backup`. Retention is controlled by `BACKUP_RETENTION_DAYS`. For a running standalone container:

```bash
docker exec health-os python /app/scripts/backup.py
```

To restore, stop the container, replace the SQLite file, make it writable by the container, and restart. Never replace SQLite while the app is running. Settings downloads JSON and CSV exports for the authenticated user only.

## Configuration

| Variable | Purpose | Standalone default |
|---|---|---|
| `DEPLOYMENT_MODE` | `standalone` or `home_assistant` | `standalone` |
| `AUTH_MODE` | `pin`, `home_assistant`, or `auto` | `pin` |
| `DATABASE_URL` | SQLAlchemy database URL | Compose uses `/data/health-os.db` |
| `DEFAULT_TIMEZONE` | Onboarding fallback IANA timezone | `America/Chicago` |
| `SESSION_SECRET` | Cookie signing secret | required for standalone startup |
| `SESSION_SECURE` | HTTPS-only session cookies | `false` |
| `SESSION_TIMEOUT_MINUTES` | Standard session duration | `120` |
| `KEEP_SIGNED_IN_DAYS` | Remembered PIN-session duration | `30` |
| `HA_TRUSTED_PROXIES` | Networks allowed to assert HA identity | `172.30.32.2/32` |
| `FRAME_ANCESTORS` | Optional trusted iframe origins | empty |
| `BACKUP_DIR`, `BACKUP_RETENTION_DAYS` | Backup destination and retention | `/backups`, `14` |

`SUPERVISOR_TOKEN` is injected by Home Assistant when `homeassistant_api: true`; do not configure or expose it manually. Deployment secrets are never returned from the settings API.

## Security and privacy

There is no telemetry, analytics, CDN, or remote font requirement. Standalone deployments should stay on a trusted network or behind an authenticated HTTPS reverse proxy. Home Assistant identity headers received from ordinary clients are ignored, including in standalone mode. A trusted Home Assistant identity creates or resumes only the account associated with its stable external subject.

PINs are unique only among PIN-enabled identities and are stored as Argon2 hashes. Authentication errors are intentionally generic. User settings, exports, tasks, completion history, reminders, notification target, and timezone are scoped to the authenticated profile.

## Testing

```bash
ruff check backend tests scripts migrations
pytest
cd frontend
npm run lint
npm test -- --run
npm run build
docker build -t health-os .
```

The automated suite covers standalone and Home Assistant identity isolation, spoofed-header rejection, onboarding, PIN linking, timezone day boundaries, Sunday schedules, travel expiry, DST gaps/overlaps, quiet hours, idempotent task completion, preserved historical dates, and durable notification delivery.

## Releases

Releases are managed by Release Please. Use Conventional Commit prefixes such as `fix:`, `feat:`,
and `feat!:` on changes merged to `main`. Release Please maintains a release pull request that
updates `home-assistant-app/config.yaml` and `home-assistant-app/CHANGELOG.md`. Merging that pull
request creates the matching `vX.Y.Z` GitHub release and publishes the exact and `latest` GHCR
container tags for `amd64` and `aarch64`.

The container publishing workflow is reusable and may also be started manually with an explicit
version, but normal releases should go through the generated release pull request so the app
manifest, changelog, Git tag, and container tag stay synchronized.

## Troubleshooting

- **Database is read-only:** grant the container write permission to the configured data and backup directories using your host platform's ownership or ACL tools.
- **Standalone startup rejects the secret:** set a long non-default `SESSION_SECRET` in `.env`.
- **Home Assistant shows an identity error:** open Health OS through Ingress, not by addressing the container directly.
- **Login loops over standalone HTTPS:** set `SESSION_SECURE=true` and ensure the reverse proxy preserves cookies.
- **DST/time looks wrong:** select the user's actual IANA timezone in Settings; `TZ` is not a substitute for per-user timezone configuration.

## License

Health OS is released under the [MIT License](LICENSE). You may use, copy, modify, publish, distribute, sublicense, sell, or fork it subject to the license notice.
