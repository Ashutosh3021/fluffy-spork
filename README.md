# Keep-Alive Service

A pure-backend, single-process keep-alive service designed to run on a single Render free-tier Web Service.

It automatically pings itself and user-configured services to keep them from spinning down.

## Features

- **Single Process**: Only one service to deploy.
- **Pure Backend**: Clean REST API, built with Flask.
- **User Services**: Configure multiple external URLs with custom endpoints and intervals.
- **Background Engine**: Periodically pings URLs based on their intervals.
- **In-Memory Store**: Easy setup, stores history, auth, and configs in memory.

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

## Deployment to Render

1. Connect your repository to Render as a New Web Service.
2. Select **Python 3** environment.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`
5. Set the `SELF_URL` environment variable to your render URL (e.g., `https://your-app-name.onrender.com`).

The service will run the Flask app on the main thread and the background keep-alive task on a separate daemon thread.
