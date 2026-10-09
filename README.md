# LINE PAI FAH SAI Reporter

> **Demo project for presenting an idea to the PAI FAH SAI group.**

LINE PAI FAH SAI Reporter is a demo concept for reporting wildfire incidents
and coordinating local volunteer responses through LINE. It is intended only
for discussion and idea presentation, not as a production emergency service.

This project is **not an emergency hotline**. For urgent wildfire reports in
Thailand, call **1362**.

## Project overview

The repository contains two parts:

- **Frontend** — React, TypeScript, and Vite applications:
  - A LINE LIFF app for submitting wildfire reports and registering as a
    volunteer.
  - An admin dashboard for reviewing volunteers and monitoring active
    incidents.
- **Backend** — A FastAPI service that receives reports, manages incidents and
  volunteers, and sends notifications through the LINE Messaging API.

The frontend and backend are designed to work together, but each part can be
developed independently.

## Main idea

1. A person reports a possible wildfire through the LINE LIFF app.
2. The report includes a location, description, and optionally a photo.
3. The backend groups nearby reports into an incident.
4. Approved local volunteers receive a LINE notification.
5. Volunteers and administrators can follow the incident response.

## Repository structure

```text
.
├── frontend/   # LINE LIFF app and admin dashboard
└── backend/    # API, database models, jobs, and LINE integration
```

## Getting started

See the README in each project directory for setup instructions:

- [Frontend README](./frontend/README.md)
- [Backend README](./backend/README.md)

In general, the frontend requires Node.js and pnpm, while the backend uses
Python, PostgreSQL/PostGIS, and LINE API credentials.

## Demo scope

This repository is a **proof of concept** for the PAI FAH SAI group. It is
provided to demonstrate a possible workflow and technical direction. It may
require additional security review, operational planning, infrastructure, and
testing before it could be used in a real emergency-response environment.

## Next step

The idea has been approved for the next stage of discussion. The next step is
to meet with the PAI FAH SAI group and the relevant stakeholders to discuss
requirements, responsibilities, infrastructure, security, operations, and the
technical plan for building a real production system.
