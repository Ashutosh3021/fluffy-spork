# Fluffy Spork Frontend

This is the pure frontend implementation for the Fluffy Spork keep-alive service.
It is built with pure HTML, CSS, and Vanilla JavaScript. No frameworks or build steps are required.

## Features

- Modern, responsive Dark UI
- Token-based Authentication
- Full CRUD for Keep-Alive Services
- Recent test history and success rates
- Direct manual test run capability
- Profile management

## Structure

```
frontend/
├── index.html              # Login & Signup
├── dashboard.html          # Overview & History
├── new-service.html        # Create new service
├── services.html           # List, manage, and test services
├── profile.html            # Profile updates (email, password, PIN)
├── css/
│   └── style.css           # Global stylesheet
└── js/
    ├── api.js              # Fetch wrapper and API config
    ├── auth.js             # Token and redirect logic
    └── app.js              # UI utilities (loaders, alerts)
```

## How to set the API base URL

The API URL is defined in `js/api.js`. Currently, it points to the live backend:

```javascript
const API_BASE_URL = 'https://fluffy-spork-iy00.onrender.com/api';
```

If you need to point to a local instance for development, change it to:
```javascript
const API_BASE_URL = 'http://localhost:5000/api';
```

## How to Deploy on Vercel

Since this is a static site, deployment is extremely straightforward:

1. Push this repository to GitHub/GitLab/Bitbucket.
2. Go to your [Vercel Dashboard](https://vercel.com/dashboard).
3. Click **Add New** -> **Project**.
4. Import your repository.
5. In the "Configure Project" step:
   - **Framework Preset**: Leave as "Other".
   - **Root Directory**: Select the `frontend` folder (or leave blank if you deploy only the frontend folder content).
   - **Build Command**: Leave empty (no build required).
   - **Output Directory**: Leave empty or set to `.` (current directory).
6. Click **Deploy**.

Vercel will serve the HTML files statically. Since routing is handled by standard HTML file links (e.g., `<a href="dashboard.html">`), everything works out of the box.