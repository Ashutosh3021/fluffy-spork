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
- **User Services**: Configure multiple external URLs with custom endpoints and intervals.
- **Background Engine**: Periodically pings URLs based on their intervals.
- **In-Memory Store**: Easy setup, stores history, auth, and configs in memory.

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
cp .env.example .env          # edit SELF_URL and secrets
python app.py
```

---

## API Documentation

- `POST /api/auth/signup` - Register a new user (`email`, `password` or `pin`).
- `POST /api/auth/login` - Authenticate (`email`, `password`), returns a token.
- `PUT /api/auth/profile` - Update profile (`email`, `password`).

- `GET /api/services` - List services.
- `POST /api/services` - Create a service (`base_url`, `endpoints`, `interval_seconds` or `pings_per_day`).
- `GET /api/services/<id>` - Get service details.
- `PUT /api/services/<id>` - Update service configuration.
- `DELETE /api/services/<id>` - Remove a service.
- `POST /api/services/<id>/test` - Immediately test the service.

- `GET /api/history` - Get recent ping history.
- `GET /api/services/<id>/analytics` - Get ping analytics for a service.

*Note: Endpoints (except signup and login) require a `Authorization: Bearer <token>` header.*

---

## Deployment to Render

1. Connect your repository to Render as a New Web Service.
2. Select **Python 3** environment.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`
5. Set the `SELF_URL` environment variable to your render URL (e.g., `https://your-app-name.onrender.com`).

The service will run the Flask app on the main thread and the background keep-alive task on a separate daemon thread.

---

## Environment Variables

| Variable          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `SELF_URL`        | Yes      | Public URL of this service (for self keep-alive) |
| `PORT`            | No       | Render automatically sets PORT                   |
| `REQUEST_TIMEOUT` | No       | Per-request timeout (default: 15)                |

---

## License

MIT
