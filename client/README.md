# Pirani Leak Test — React Frontend

This is a standalone **React + Tailwind CSS v4 + react-icons** rewrite of the
three Flask/Jinja pages (`fixtures.html`, `recipes.html`, `reports.html`),
which have been removed. This is a **frontend-first** project: none of the
Flask API logic (`db.py`, `config.py`, `test_runner.py`, Modbus workers, SSE
stream, DB schema) was touched. `app.py` only changed to drop the old
`render_template()` calls (the templates no longer exist) and to serve this
app's production build instead — see "Building for production" below.

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

`app.py` already serves `client/dist` directly — once the build exists,
running `python app.py` from the project root serves the React app on `/`,
`/recipes`, `/reports` (client-side routing works on refresh too) **and**
the API on the same port. No extra web server is required, though you can
still put nginx in front of it if you want TLS, caching, etc.
