# fluffy-spork

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render%20Free-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

**Lightweight self-keep-alive service for Render free-tier apps.**

A pure-backend service that keeps itself (and other Render free-tier services) awake by periodic pinging. Users can register, configure services with custom endpoints and intervals, run test pings, and view history — all through a clean REST API.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Render Free Web Service                   │
│                                                              │
│  ┌─────────────┐      ┌──────────────┐      ┌─────────────┐  │
│  │   REST API  │◄────►│  In-Memory   │◄────►│  Background │  │
│  │  (Flask)    │      │   Store      │      │   Pinger    │  │
│  └─────────────┘      └──────────────┘      └──────┬──────┘  │
│         │                     │                     │        │
│         │                     │                     │        │
│    Auth • Services      Users • Services       Self-ping     │
│    History • Test       Ping Records          + User services│
│                                                              │
│  /health  ◄─────────────────────────────────────────────────┘
│     ▲                                                        │
│     │  (self keep-alive every ~14 min)                       │
└─────┼────────────────────────────────────────────────────────┘
      │
      └── Also pings all user-configured services
```

### Key Design Decisions

| Decision              | Choice                          | Reason                                      |
|-----------------------|---------------------------------|---------------------------------------------|
| Deployment            | Single Render Web Service       | Simplest free-tier setup                    |
| Self keep-alive       | Pings its own `/health`         | Prevents the free instance from sleeping    |
| Storage (current)     | In-memory                       | Fast to develop, easy to swap later         |
| Auth                  | Email + Password **or** PIN     | Flexible for personal use                   |
| Frontend              | None (pure backend)             | Focus on API first                          |
| Scheduling            | Fixed interval or pings/day     | Good enough for keep-alive use case         |

---

## Features

- **Single Process**: Only one service to deploy.
- **Pure Backend**: Clean REST API, built with Flask.
- **Auth**: Sign up / Login with email + password or PIN. Change profile.
- **Service Management**: Create, list, update, delete services. Configure base URL, endpoints, and interval (or pings-per-day).
- **Test Run**: Immediately ping a service and see results.
- **Background Engine**: Periodically pings configured services + self keep-alive.
- **History & Analytics**: In-memory ping records with success rate and response-time stats.

---

## Project Structure

```
fluffy-spork/
├── app.py                 # Flask app, models, endpoints & background pinger
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick Start (local)

```bash
git clone https://github.com/Ashutosh3021/fluffy-spork.git
cd fluffy-spork
pip install -r requirements.txt
cp .env.example .env          # edit SELF_URL
python app.py
```

---

## API Documentation

### Auth
- `POST /api/auth/signup` — Register (`email`, `password` or `pin`)
- `POST /api/auth/login` — Authenticate, returns `token`
- `PUT /api/auth/profile` — Update email / password / PIN

### Services
- `GET /api/services` — List your services
- `POST /api/services` — Create service (`base_url`, `endpoints`, `interval_seconds` or `pings_per_day`)
- `GET /api/services/<id>` — Get service details
- `PUT /api/services/<id>` — Update service
- `DELETE /api/services/<id>` — Delete service
- `POST /api/services/<id>/test` — Immediate test run

### Health & Status
- `GET /health` — Simple health check for keep-alive
- `GET /api/status` — Basic status info (version, uptime, user/service counts)

### History & Analytics
- `GET /api/history` — Recent ping history (optional `?service_id=`)
- `GET /api/services/<id>/analytics` — Success rate & avg response time

> All endpoints except signup and login require header:  
> `Authorization: Bearer <token>`

---

## CORS Configuration

CORS is enabled by default to allow requests from the following origins:
- `https://keep-awake1.vercel.app`
- `http://localhost:*` (for local development)

---

## Deployment to Render (Free Tier)

1. Create a new **Web Service** and connect this repository.
2. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`
3. Environment Variables:
   - `SELF_URL` = your public Render URL (e.g. `https://your-app.onrender.com/health`)
   - `REQUEST_TIMEOUT` (optional, default 15)
4. Deploy. The service will automatically keep itself awake.

---

## Environment Variables

| Variable          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `SELF_URL`        | Yes      | Public URL of this service (for self keep-alive) |
| `PORT`            | No       | Injected by Render                               |
| `REQUEST_TIMEOUT` | No       | Per-request timeout in seconds (default: 15)     |

---

## License

MIT
