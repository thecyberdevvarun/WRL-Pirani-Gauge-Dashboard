# Pirani Leak Test — React Frontend

The **React + Tailwind CSS v4 + react-icons** frontend. It talks to the Flask
API in `app.py` (login, line selection, fixtures/SSE, live gauge status,
reports); the production build is served by the same Flask process — see
"Building for production" below. Login is checked by the backend, which also
decides which production line a session may see: the browser keeps no
credentials and never chooses a line on its own.

## Pages

| Route          | Notes |
|----------------|-------|
| `/login`       | Username + password; the backend maps the login to its production line(s). |
| `/select-line` | Only for logins authorised for several lines: choose which line to work on (also reachable from "Switch line" in the header). |
| `/`            | Live conveyor view for the selected line, scan/start panel, gauge detail (value, freshness, USR id/IP, connection / polling / communication status, last error) with a live vacuum chart, last 10 results. Subscribes to `/api/fixtures/stream` (SSE) with polling fallback. |
| `/reports`     | Date/field filters, summary cards, results table, vacuum trend, Excel and PDF export — always limited to the selected line. |
| `/settings`    | Read-only: the line's network, USR devices and gauges with live health. Admins can test a USR connection. Configuration itself is edited in the server's `.env`. |

## Stack

- **Vite** + **React 19**
- **Tailwind CSS v4** via `@tailwindcss/vite` (CSS-first config in `src/index.css`, no `tailwind.config.js` needed)
- **react-router-dom** for the routes
- **react-icons** (`react-icons/fi`) instead of emoji
- **recharts** instead of Chart.js for the live vacuum gauge chart and the trend modal chart
 - **react-hot-toast** for lightweight toasts

## Project layout

```
client/
  src/
    api/client.js        # every fetch() call to the Flask API lives here
   (toasts handled by `react-hot-toast`)
    components/          # presentational + small stateful pieces
    pages/                # LoginPage, SelectLinePage, FixturesPage, ReportsPage, SettingsPage
    store/                # Redux: auth (user, role, line) and the selected line's config
```

## Running in development

The Flask app runs on port 5000:

```bash
# terminal 1 — backend
cd ..
python app.py

# terminal 2 — frontend
cd client
npm install
npm run dev          # http://localhost:5173
```

`vite.config.js` proxies `/api`, `/start-test` and `/stop-test` to
`http://localhost:5000`, so the React app talks to the real Flask backend
while you develop, with hot reload.

## Building for production

```bash
cd client
npm run build         # outputs client/dist
```

`app.py` already serves `client/dist` directly — once the build exists,
running `python app.py` from the project root serves the React app on `/`,
`/reports`, `/settings` (client-side routing works on refresh too) **and**
the API on the same port. No extra web server is required, though you can
still put nginx in front of it if you want TLS, caching, etc.
