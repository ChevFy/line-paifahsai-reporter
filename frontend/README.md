# line-paifahsai-frontend

Frontend for [`line-paifahsai-backend`](../line-paifahsai-backend), the wildfire
reporting service of the Pai Fah Sai club (ชมรมปายฟ้าใส) in **Pai District, Mae Hong Son**.

People report a wildfire from LINE, and the backend dispatches the report to
approved volunteer firefighters in the district.

> This service is not an emergency hotline. For urgent fires, call **1362**
> (Thailand's wildfire reporting center). Every report screen shows this number.

The repository contains **two separate web apps** built with React, TypeScript and Vite:

| App | Who uses it | Source | Dev URL |
|---|---|---|---|
| LIFF app | The public and volunteers, inside LINE | `src/liff/`, `src/main.tsx` | http://localhost:5173 |
| Admin dashboard | Club admins, in a desktop browser | `src/app/` | http://localhost:5174 |

## Features

### LIFF app (inside LINE)

- **Report a wildfire** (`/`)
  - Pin the fire location on a map (Leaflet + OpenStreetMap), or use the current GPS position.
  - Add a description and an optional photo (JPEG/PNG/WebP, max 10 MB). The photo is compressed in the browser before upload.
  - The report is submitted first and the photo is uploaded second. If the photo upload fails, the report is kept and the user can retry the upload.
  - The user is identified by their LINE login, so there is no separate sign-up.
- **Volunteer registration** (`/register`)
  - Shows the user's current status: pending, approved, rejected or suspended.
  - A user who has not registered yet gets a form for full name and phone number. Phone numbers are normalised, so `081-234-5678` and `+66 81 234 5678` are both accepted.
- **Thai / English** language switch. The choice is remembered on the device.

### Admin dashboard

- **Login / logout** with a session cookie. When the 12-hour session expires, the admin is sent back to the login page.
- **Volunteers** (`/volunteers`)
  - Paginated table, filtered by status and district. The "pending" tab is the default.
  - Approve, reject or suspend a volunteer. Reject and suspend ask for confirmation first. The backend notifies the volunteer in LINE.
- **Incident map** (`/map`)
  - Active incidents on a map and in a list. Incidents nobody has accepted yet come first.
  - Filter by district. The page refreshes itself every minute and warns when the data may be out of date.

## Prerequisites

- **Node.js** 20.19+ or 22.12+ (required by Vite 8)
- **pnpm** (the repo includes `pnpm-lock.yaml`)
- A running **[line-paifahsai-backend](../line-paifahsai-backend)** on `http://127.0.0.1:8000`
- For the LIFF app inside LINE:
  - a LINE Login channel with a LIFF app, with scopes `openid` and `profile`
  - an **HTTPS** tunnel to your machine, for example cloudflared or ngrok, because LINE only opens HTTPS endpoint URLs

## Setup

```bash
pnpm install
cp .env.example .env
```

Edit `.env`:

| Variable | Used by | Description |
|---|---|---|
| `VITE_LIFF_ID` | LIFF app | LIFF ID from the LINE Developers Console |
| `VITE_BACKEND_API` | LIFF app | Base URL of the backend. In development, use `/api` so requests go through the Vite proxy (see below). |

`.env` is git-ignored. Do not commit real IDs or secrets.

## Running the LIFF app

```bash
pnpm dev            # http://localhost:5173
```

In development, set `VITE_BACKEND_API=/api`. The dev server forwards `/api/*` to
`http://localhost:8000`, so the browser only talks to one origin and CORS is not an issue.

To open it inside LINE:

1. Expose port 5173 with an HTTPS tunnel, for example `cloudflared tunnel --url http://localhost:5173`.
2. In the LINE Developers Console, set the LIFF **Endpoint URL** to the tunnel URL.
3. Open the app from LINE:
   - Report form: `https://liff.line.me/<LIFF_ID>`
   - Volunteer registration: `https://liff.line.me/<LIFF_ID>/register`

## Running the admin dashboard

```bash
pnpm dev:admin      # http://localhost:5174
```

The admin session is an `HttpOnly`, `SameSite=Strict` cookie scoped to `/admin`,
so the dashboard **must be served from the same origin as the API**. The admin dev
server (`vite.admin.config.ts`) proxies these paths to `http://127.0.0.1:8000`:

- `/admin`
- `/districts`
- `/incidents/active`

For this reason, page routes in the dashboard never start with `/admin`.

The cookie is marked `Secure`. Chrome and Firefox accept it on `http://localhost`,
but Safari may not. If login does not stick in Safari, use an HTTPS tunnel.

## Scripts

| Command | What it does |
|---|---|
| `pnpm dev` | Start the LIFF app dev server (port 5173) |
| `pnpm dev:admin` | Start the admin dashboard dev server (port 5174) |
| `pnpm build` | Type-check and build the LIFF app into `dist/` |
| `pnpm build:admin` | Type-check and build the admin dashboard into `dist-admin/` |
| `pnpm preview` | Serve the built LIFF app locally |
| `pnpm lint` | Run ESLint |
| `pnpm test` | Run all unit tests once (Vitest + Testing Library + jsdom) |
| `pnpm test:watch` | Run tests in watch mode |

Before opening a pull request, run all checks:

```bash
npx tsc -b && pnpm lint && pnpm test && pnpm build && pnpm build:admin
```

## Deployment notes

- Both apps are single-page apps. The web server must fall back to `index.html` for unknown paths, such as `/register`, `/volunteers` or `/map`.
- **LIFF app:** serve `dist/` over HTTPS at the LIFF endpoint URL. Set `VITE_BACKEND_API` to the public backend URL at build time.
- **Admin dashboard:** serve `dist-admin/` behind the **same reverse proxy** as the backend. Forward `/admin/*`, `/districts` and `/incidents/active` to the backend, and send every other path to `index.html`.

## Project structure

```
src/
├── main.tsx, App.tsx        LIFF app entry + routes (/ and /register)
├── liff.ts                  shared LIFF instance and one-time init
├── liff/                    LIFF app
│   ├── pages/               ReportPage, VolunteerRegisterPage
│   ├── components/          LocationMap, ImagePicker, PageShell, LanguageSwitcher
│   ├── services/            API calls (reports, volunteers) + api-client
│   ├── hooks/               language provider, useMyVolunteer
│   ├── locales/             th.json, en.json
│   ├── types/  utils/  config/
├── app/                     Admin dashboard (separate Vite root)
│   ├── index.html, main.tsx, App.tsx
│   ├── pages/               LoginPage, VolunteersPage, IncidentsMapPage
│   ├── components/          AdminLayout, IncidentMap, ConfirmDialog, ...
│   ├── services/            API calls + api-client (401 → back to login)
│   ├── hooks/               AuthProvider, useVolunteerPage, useActiveIncidents
│   ├── types/  utils/
├── styles/shared.css        styles shared by both apps
└── test/setup.ts            Vitest setup
```

Tests live next to the code they cover (`*.test.ts` / `*.test.tsx`).
