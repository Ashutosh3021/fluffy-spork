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

## Features (Target)

- **Auth**
  - Sign up / Login with email + password or PIN
  - Change password, PIN, or email

- **Service Management**
  - Create service with base URL + endpoints (`/health`, `/docs`, `/`, or custom)
  - Set interval (seconds) **or** pings-per-day
  - Test-run any service instantly
  - List / Update / Delete services

- **Execution**
  - Background pinger keeps the service itself alive
  - Also pings all configured user services
  - Optional wake-up logic for cold starts

- **History & Analytics**
  - Every ping result stored in memory
  - Recent history + basic success-rate / response-time stats

---

## Project Structure (Target)

```
fluffy-spork/
├── app.py                 # Flask entry point + routes
├── auth.py                # Signup, login, password/PIN handling
├── models.py              # In-memory data classes & stores
├── services.py            # Service CRUD + test-run
├── pinger.py              # Background execution engine
├── history.py             # Ping records & simple analytics
├── requirements.txt
├── .env.example
├── DEPLOYMENT.md
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

## Render Free Deployment

1. Create a new **Web Service** on Render and connect this repo.
2. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`
3. Add environment variables (see `.env.example`).
4. Set `SELF_URL` to the public URL Render gives you (e.g. `https://your-service.onrender.com`).
5. Deploy. The service will keep itself awake automatically.

---

## Environment Variables

| Variable          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `SELF_URL`        | Yes      | Public URL of this service (for self keep-alive) |
| `SECRET_KEY`      | Yes      | Flask/JWT secret                                 |
| `PING_INTERVAL`    | No       | Default interval in seconds (default: 840)       |
| `REQUEST_TIMEOUT` | No       | Per-request timeout (default: 15)                |

---

## License

MIT
