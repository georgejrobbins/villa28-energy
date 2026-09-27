# villa28-energy

Personal, read-only home monitoring with Python 3.12, FastAPI and PostgreSQL. The dashboard is password-protected. No thermostat, HVAC or inverter control commands are implemented.

## This release

- Google Nest: official SDM device reads, multiple thermostat zones, OAuth through Nest Partner Connections Manager, automatic token refresh, five-minute polling and a Pub/Sub consumer.
- Temperature, heat/cool targets, humidity, HVAC state, mode, Eco state and connectivity are stored. History charts show temperature and humidity.
- Sungrow is intentionally **deferred**. Its provider interface makes no HTTP requests. No undocumented endpoints or field mappings are used.
- Transactional PostgreSQL migrations are tracked by checksum and serialized during deployment. Refresh and access tokens are encrypted. Logs omit credentials, OAuth query strings and event payloads.
- Google integration requires your credentials and account consent before it can collect real readings. Pub/Sub additionally requires a subscribed service account.

## Deploy through GitHub to Railway

Push this repository to the connected `main` branch. The existing Railway service should use the repository root, this Dockerfile, one replica, no sleeping/serverless mode, and the existing PostgreSQL service.

Railway service settings:

- Start command: `python -m app.run`
- Healthcheck: `/health` (allow 120 seconds)
- Database variable: `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- The Dockerfile also provides a start command using `PORT`, defaulting to 8000 locally.
- `railway.json` describes the same settings where legacy config-as-code is supported. Check the service settings rather than relying on that file alone.

### Environment variables

Set secrets in Railway, never in GitHub or source files. `.env.example` contains no actual credentials.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Reference to the existing Railway PostgreSQL database |
| `DASHBOARD_USERNAME` | Owner login name; defaults to `owner` |
| `DASHBOARD_PASSWORD` | Required owner password; missing value blocks dashboard/API access |
| `ENCRYPTION_KEY` | Fernet key, or an existing strong random secret of at least 32 characters |
| `GOOGLE_CLIENT_ID` | Google Cloud OAuth web application client ID |
| `GOOGLE_CLIENT_SECRET` | Corresponding OAuth client secret |
| `GOOGLE_DEVICE_ACCESS_PROJECT_ID` | Project UUID from the Nest Device Access console, **not** the Cloud project ID |
| `GOOGLE_PROJECT_ID` | Legacy fallback for the Device Access UUID, when the variable above is absent |
| `GOOGLE_PUBSUB_SUBSCRIPTION` | Full name: `projects/CLOUD_PROJECT/subscriptions/SUBSCRIPTION` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service account JSON with subscriber permission on that subscription |
| `POLLING_INTERVAL_SECONDS` | Defaults to 300; minimum 30 |
| `RAILWAY_PUBLIC_DOMAIN` | Injected by Railway; used for HTTPS callback URLs |
| `PUBLIC_BASE_URL` | Optional override, e.g. `http://localhost:8000` locally; leave unset on Railway |
| `LOG_LEVEL` | Defaults to INFO |

Generate a Fernet key locally with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and save it only in Railway. Keep the key stable; changing it makes stored tokens unreadable. The previous source's space-padding encryption format is not used. If upgrading from a running original version, reconnect Google after changing encryption format.

### Google setup

1. Enable SDM in the Google Cloud project and create a **Web application** OAuth client. Create/link a Nest Device Access project with that client.
2. Register `https://YOUR_PUBLIC_DOMAIN/auth/google/callback` as the OAuth client's authorized redirect URI.
3. Set the Google variables and encryption key above. Sign into the dashboard as `owner`, then select **Connect Google Nest** and complete consent yourself.
4. Enable Device Access events and configure a Pub/Sub pull subscription. Supply a service account with only the subscriber access it needs in `GOOGLE_SERVICE_ACCOUNT_JSON`. Keep its key out of GitHub.
5. The dashboard shows polling and event-connection status. Polling continues if Pub/Sub is not configured or unavailable. Initial readings can take up to one polling interval.

Official references:

- [Nest authorization and Partner Connections Manager](https://developers.google.com/nest/device-access/api/authorization)
- [SDM device listing](https://developers.google.com/nest/device-access/reference/rest/v1/enterprises.devices/list)
- [Temperature setpoints](https://developers.google.com/nest/device-access/traits/device/thermostat-temperature-setpoint)
- [Device names](https://developers.google.com/nest/device-access/traits/device/info)
- [Nest events](https://developers.google.com/nest/device-access/api/events)
- [Pub/Sub authentication](https://docs.cloud.google.com/pubsub/docs/authentication)

### Sungrow follow-up

The reserved callback is `https://YOUR_PUBLIC_DOMAIN/auth/sungrow/callback`. It currently returns an explicit deferred response and **cannot complete authorization**.

Before implementing the provider we need the official regional API base URL/version, OAuth authorization/token endpoints, required scopes and client authentication/signing rules, installation-list and telemetry endpoints, sample responses, field names/units, rate limits, and timestamp/timezone conventions. Existing Sungrow environment variables are ignored in this release.

## Routes

| Route | Behavior |
| --- | --- |
| `/health` | Public database health check; HTTP 503 on failure |
| `/` | Owner dashboard |
| `/auth/google` | Starts an owner-authorized, one-time-state OAuth flow |
| `/auth/google/callback` | Validates browser-bound state and exchanges the authorization code |
| `/auth/sungrow`, `/auth/sungrow/callback` | Owner-only HTTP 503 with the missing provider documentation |
| `/api/current` | Latest reading per thermostat and solar installation |
| `/api/history?device_id=ID&hours=24` | Chronological history, maximum 10,000 readings and 720 hours |
| `/api/history?installation_id=ID&hours=24` | Solar history when that provider is implemented |
| `/api/daily-summary?days=7` | UTC daily solar summaries; maximum 90 days |
| `/api/status` | Owner-only integration status, without secrets |

All data routes require HTTP Basic authentication over HTTPS. The public health check contains no home readings. Browser credentials are retained for the browser session; close the browser/private window to end that session.

## Database and event handling

The original four tables remain: `thermostat_readings`, `thermostat_events`, `solar_readings`, `oauth_tokens`. `schema_migrations` tracks applied DDL, and `oauth_states` stores hashed one-time authorization state with expiry.

Pub/Sub commits an event before acknowledging it. Unique message/event IDs handle duplicate delivery. Partial changes are merged into the latest known thermostat snapshot. Events older than that snapshot are retained in the event table but do not replace current state; full polling reconciles state. An initial full poll is required before partial updates can create snapshots.

Daily solar generation uses the maximum cumulative counter per installation per UTC day, then sums installations. Average power includes zero-valued samples. The maximum-export value is the largest individual installation sample, not a simultaneous site-wide total. Historical queries return latest 10,000 rows and flag truncation.

## Development and checks

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Populate local PostgreSQL connection, owner password, and encryption key.
uvicorn app.main:app --reload --no-access-log
pytest -q
```

Tests isolate application state in SQLite, parse DDL with a PostgreSQL parser, and exercise owner authentication, OAuth state/replay/expiry, token encryption and refresh, thermostat mappings, duplicate/late events, health errors, history and summaries. The optional PostgreSQL integration test uses `TEST_POSTGRES_URL` and creates/drops its own temporary schema. GitHub CI runs it against PostgreSQL 16 and also checks JavaScript syntax.

Real Google device access and Pub/Sub delivery require the configured account and consent; passing automated tests is not a claim that a household's devices have connected.
