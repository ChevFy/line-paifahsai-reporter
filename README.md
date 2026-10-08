# line-paifahsai-backend

Backend for a LINE LIFF app that lets people report wildfires in **Pai District,
Mae Hong Son** and dispatches the reports to local volunteer firefighters.

Part of the **Pai Fah Sai club (ชมรมปายฟ้าใส)** in Pai. It covers Pai District
only. It is not a nationwide service.

> This is not an emergency hotline. For urgent fires, call **1362**
> (Thailand's wildfire reporting center).

## What it does

- **Report a fire.** A person opens the LIFF form in LINE, pins the fire on a map,
  and can add a photo. No sign-up is needed.
- **Dedup reports.** Reports within 1 km of an active incident are merged into it,
  so the same fire isn't dispatched twice.
- **Notify volunteers.** Registered volunteers in Pai get a LINE message with
  "I'll go" and map buttons.
- **Track the response.** Volunteers mark arrived, done, or withdraw. The incident
  closes when everyone is done.
- **Escalate.** If nobody accepts within 20 minutes, the alert is sent again and
  admins are notified.
- **Share photos.** Volunteers open reporter photos from a signed link in the alert.
  The link expires after 3 days.
- **Fail loudly.** When something fails (LINE API, storage, background jobs), the
  error is logged and an admin alert is saved to the database.

## API

All LIFF endpoints that need a user take a LINE ID token in
`Authorization: Bearer <token>`. Every error response has the shape
`{"detail": {"message": "..."}}`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/healthz` | – | Health check |
| `GET` | `/districts` | – | Districts for the form's dropdown |
| `GET` | `/incidents/active` | – | Active incidents for the map. Optional `?district_code=` |
| `POST` | `/reports` | ID token | Submit a fire report and get back a `report_id` |
| `POST` | `/reports/{report_id}/image` | ID token | Attach a photo to your own report (multipart field `image`, max 10 MB) |
| `POST` | `/volunteers` | ID token | Register as a volunteer. Status starts as `pending` |
| `GET` | `/volunteers/me` | ID token | Get your volunteer status |
| `GET` | `/incidents/{id}/photos` | Signed link | Photo page for volunteers and admins |
| `GET` | `/incidents/{id}/photos/{report_id}` | Signed link | A single photo |
| `POST` | `/webhook` | LINE signature | LINE Messaging API webhook (button presses, messages) |

Report first, then upload the photo. A failed upload never loses the report.

## Admin CLI

There is no admin dashboard yet. Use these commands instead:

```bash
python -m scripts.volunteers list|approve|reject|suspend <id>
python -m scripts.incidents photos <incident_id>   # prints a signed photo link
```

## Tech stack

FastAPI · SQLAlchemy 2.0 · PostgreSQL + PostGIS · LINE Messaging API ·
S3-compatible storage (SeaweedFS) · Postgres-backed job queue

## Quick start

```bash
cp .env.example .env              # fill in your LINE, database, and S3 values
docker compose --profile storage up -d
uv sync
uv run alembic upgrade head
uv run python main.py
```

## Tests

```bash
uv run pytest
```

Database tests are skipped unless `TEST_DATABASE_URL` points to a separate
PostGIS database.
