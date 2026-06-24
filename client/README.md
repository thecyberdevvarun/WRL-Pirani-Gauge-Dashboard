# Pirani Leak Test — React Frontend

This is a standalone **React + Tailwind CSS v4 + react-icons** rewrite of the
three Flask/Jinja pages (`fixtures.html`, `recipes.html`, `reports.html`).
It is a **frontend-only** project: nothing in the Flask app (`app.py`, `db.py`,
`config.py`, `test_runner.py`, Modbus workers, SSE stream, DB schema) was
touched. This app only *calls* the existing API routes.

## Pages

| Route       | Replaces                  | Notes |
|-------------|----------------------------|-------|
| `/`         | `templates/fixtures.html` | Live conveyor view, scan/start panel, gauge detail + live vacuum chart (recharts), last 10 results. Subscribes to `/api/fixtures/stream` (SSE) with polling fallback. |
| `/recipes`  | `templates/recipes.html`  | Recipe master CRUD table + add/edit/clone modal. |
| `/reports`  | `templates/reports.html`  | Date/field filters, summary cards, results table, vacuum trend modal, Excel export. |

## Stack

- **Vite** + **React 19**
- **Tailwind CSS v4** via `@tailwindcss/vite` (CSS-first config in `src/index.css`, no `tailwind.config.js` needed)
- **react-router-dom** for the 3 routes
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
    pages/                # FixturesPage, RecipesPage, ReportsPage
```

## Running in development

The Flask app still runs on port 5000, unchanged:

```bash
# terminal 1 — backend (unchanged)
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

Two ways to serve the build, your choice:

1. **Same Flask server (recommended, zero extra infra):**
   Point Flask's static handling at `client/dist` (or copy `dist/*` into
   `static/` and `dist/index.html` into `templates/`), and add a catch-all
   Flask route that returns that `index.html` for `/`, `/recipes`, `/reports`
   so client-side routing works on refresh. No existing API routes change.
2. **Separate static host / nginx:** serve `client/dist` from any static
   file server or CDN, and reverse-proxy `/api`, `/start-test`,
   `/stop-test` to the Flask app's port 5000.

Either way, the backend code in this repository is unmodified.
