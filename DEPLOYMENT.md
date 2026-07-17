# Render.com Deployment Guide — Mutual Keep-Alive System

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   keep_alive.py  ──pings──►  your other Render services    │
│        ▲                                                    │
│        │ pings /health                                      │
│        │                                                    │
│   watcher.py  ◄──────── keep_alive.py also pings watcher   │
│        │                                                    │
│        └──────── keep_alive.py keeps watcher alive         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- **keep_alive.py** pings all your services (including the watcher) every 14 minutes.
- **watcher.py** pings keep_alive's `/health` endpoint every 14 minutes.
- Both are deployed as separate Render web services, so if one goes cold the other
  wakes it back up on its next cycle.

---

## Prerequisites

- A [Render.com](https://render.com) account (free tier is fine).
- Your code pushed to a GitHub or GitLab repository.
- The three files at the **repository root**: `keep_alive.py`, `watcher.py`, `requirements.txt`.

---

## Step 1 — Deploy the Main Pinger (keep_alive.py)

1. Log in to Render and click **New → Web Service**.
2. Connect your GitHub/GitLab repository.
3. Fill in the service settings:

   | Field            | Value                          |
   |------------------|--------------------------------|
   | **Name**         | `keep-alive-pinger` (or anything you like) |
   | **Region**       | Choose the one closest to your users |
   | **Branch**       | `main` (or your default branch) |
   | **Runtime**      | `Python 3`                     |
   | **Build Command**| `pip install -r requirements.txt` |
   | **Start Command**| `gunicorn keep_alive:app --bind 0.0.0.0:$PORT --workers 1 --threads 2` |
   | **Instance Type**| `Free`                         |

4. Under **Environment Variables**, add:

   | Key             | Value (example)                                      |
   |-----------------|------------------------------------------------------|
   | `SITES_URLS`    | `https://service-a.onrender.com,https://service-b.onrender.com,https://keep-alive-watcher.onrender.com` |
   | `PING_INTERVAL` | `840`  *(optional — defaults to 840 s / 14 min)*     |
   | `REQUEST_TIMEOUT` | `15` *(optional — defaults to 15 s)*               |

   > **Tip:** Include the watcher's URL in `SITES_URLS` so the pinger keeps the
   > watcher alive too.

5. Click **Create Web Service**. Render will build and deploy automatically.
6. Once deployed, note the public URL, e.g. `https://keep-alive-pinger.onrender.com`.
   Verify it works by opening `https://keep-alive-pinger.onrender.com/health` in your browser.

---

## Step 2 — Deploy the Watcher (watcher.py)

1. Click **New → Web Service** again.
2. Connect the **same repository**.
3. Fill in the service settings:

   | Field            | Value                          |
   |------------------|--------------------------------|
   | **Name**         | `keep-alive-watcher`           |
   | **Region**       | Same as Step 1                 |
   | **Branch**       | `main`                         |
   | **Runtime**      | `Python 3`                     |
   | **Build Command**| `pip install -r requirements.txt` |
   | **Start Command**| `gunicorn watcher:app --bind 0.0.0.0:$PORT --workers 1 --threads 2` |
   | **Instance Type**| `Free`                         |

4. Under **Environment Variables**, add:

   | Key               | Value                                                    |
   |-------------------|----------------------------------------------------------|
   | `MAIN_PINGER_URL` | `https://keep-alive-pinger.onrender.com/health`          |
   | `PING_INTERVAL`   | `840`  *(optional)*                                      |
   | `REQUEST_TIMEOUT` | `15`   *(optional)*                                      |

5. Click **Create Web Service**.
6. Once deployed, open `https://keep-alive-watcher.onrender.com/health` to confirm it's running.

---

## Step 3 — Close the mutual keep-alive loop

Go back to the **keep-alive-pinger** service on Render:

1. Open **Environment → Edit Variables**.
2. Make sure `SITES_URLS` includes the watcher's root URL, e.g.:
   ```
   https://service-a.onrender.com,https://keep-alive-watcher.onrender.com
   ```
3. Save — Render will redeploy automatically.

Now each service wakes the other up on every 14-minute cycle. ✅

---

## Environment Variable Reference

### keep_alive.py

| Variable         | Required | Default | Description                                   |
|------------------|----------|---------|-----------------------------------------------|
| `SITES_URLS`     | ✅ Yes   | —       | Comma-separated URLs to ping                  |
| `PING_INTERVAL`  | No       | `840`   | Seconds between ping cycles (840 = 14 min)    |
| `REQUEST_TIMEOUT`| No       | `15`    | Per-request timeout in seconds                |
| `PORT`           | No       | `8080`  | Injected automatically by Render              |

### watcher.py

| Variable          | Required | Default | Description                                  |
|-------------------|----------|---------|----------------------------------------------|
| `MAIN_PINGER_URL` | ✅ Yes   | —       | Full URL of pinger's `/health` endpoint      |
| `PING_INTERVAL`   | No       | `840`   | Seconds between checks                       |
| `REQUEST_TIMEOUT` | No       | `15`    | Per-request timeout in seconds               |
| `PORT`            | No       | `8080`  | Injected automatically by Render             |

---

## Verifying everything works

1. Open the Render dashboard and click **Logs** on each service.
2. You should see log lines like:
   ```
   2026-07-17 10:00:00 [INFO] ✅  PING OK   | https://service-a.onrender.com | HTTP 200
   2026-07-17 10:14:00 [INFO] ✅  PING OK   | https://service-a.onrender.com | HTTP 200
   ```
3. For the watcher:
   ```
   2026-07-17 10:00:00 [INFO] ✅  PINGER OK  | HTTP 200 | https://keep-alive-pinger.onrender.com/health
   ```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `❌  BAD URL` in logs | URL missing `https://` | Check `SITES_URLS` / `MAIN_PINGER_URL` |
| `❌  CONN ERR` in logs | Target service is cold-starting | Normal on first ping; it will recover |
| `❌  TIMEOUT` in logs | Target taking > 15 s to wake | Increase `REQUEST_TIMEOUT` to `30` |
| Health endpoint returns 502 | Gunicorn not started | Check **Start Command** spelling |
| Services still sleeping | Ping interval too long | Lower `PING_INTERVAL` to `780` |

---

## File structure

```
your-repo/
├── keep_alive.py      # Main pinger service
├── watcher.py         # Watcher service
├── requirements.txt   # Python dependencies
└── DEPLOYMENT.md      # This file
```
