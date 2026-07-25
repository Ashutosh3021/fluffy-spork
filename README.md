# fluffy-spork

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render%20Free-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

**Lightweight self-keep-alive service for Render free-tier apps.**

Users register, configure services (base URL, endpoints, HTTP method, interval), run test pings, and view **Recent History** (Time / Service / Status / Duration). Data is persisted with the official **[pyronites](https://pypi.org/project/pyronites/)** client against your Pyronites backend.

---

## What is stored in the DB

| Area | Fields |
|------|--------|
| **Auth (signup / login)** | email, password or pin |
| **Services** | base_url, endpoints, HTTP method, interval, last_pinged_at |
| **Recent History** | timestamp (Time), service_id, success/status (Status), response_time_ms (Duration), endpoint, error |

Tables: `fs_users`, `fs_tokens`, `fs_services`, `fs_ping_records` (created automatically on startup if the API key has admin SQL access).

---

## Quick Start (local)

```bash
git clone https://github.com/Ashutosh3021/fluffy-spork.git
cd fluffy-spork
pip install -r requirements.txt
cp .env.example .env
# set PYRONITES_URL, PYRONITES_KEY, SELF_URL
python app.py
```

---

## Deployment env vars (Render)

Set these in the Render dashboard → Environment:

| Variable | Required | Description |
|----------|----------|-------------|
| **`PYRONITES_URL`** | **Yes** | Your Pyronites backend base URL (no trailing slash), e.g. `https://pyrocore-backend.onrender.com` |
| **`PYRONITES_KEY`** | **Yes** | API key from the Pyronites dashboard (API Keys page), e.g. `pyro_live_...` |
| **`SELF_URL`** | **Yes** | Public health URL of *this* fluffy-spork service, e.g. `https://your-fluffy-spork.onrender.com/health` |
| `PORT` | No | Set by Render automatically |
| `REQUEST_TIMEOUT` | No | Ping timeout in seconds (default `15`) |

### Render service settings

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`

### One-time Pyronites setup

1. Deploy / open your **Pyronites** backend.
2. In the dashboard, create an API key (prefer a key that can write; admin helps auto-create tables).
3. Put `PYRONITES_URL` + `PYRONITES_KEY` on the fluffy-spork service.
4. Redeploy fluffy-spork. On boot it tries `CREATE TABLE IF NOT EXISTS` for the four tables via `client.sql`.
5. If bootstrap fails (non-admin key), create these tables manually in the dashboard:

   - `fs_users` — columns: `id`, `email`, `password` (TEXT)
   - `fs_tokens` — columns: `id`, `user_id` (TEXT)
   - `fs_services` — columns: `id`, `user_id`, `base_url`, `endpoints`, `interval_seconds`, `method`, `last_pinged_at` (TEXT)
   - `fs_ping_records` — columns: `id`, `user_id`, `service_id`, `timestamp`, `endpoint`, `status_code`, `success`, `response_time_ms`, `error` (TEXT)

---

## API (unchanged paths)

### Auth
- `POST /api/auth/signup` — `email`, `password` or `pin`
- `POST /api/auth/login` — returns `token`
- `PUT /api/auth/profile` — update email / password / PIN

### Services
- `GET/POST /api/services`
- `GET/PUT/DELETE /api/services/<id>`
- `POST /api/services/<id>/test`

### History
- `GET /api/history` — recent pings (optional `?service_id=`)
- `GET /api/services/<id>/analytics`

### Health
- `GET /health`
- `GET /api/status` — includes `"storage": "pyronites"`

All endpoints except signup/login need: `Authorization: Bearer <token>`

---

## License

MIT
