# QuantTrade Dashboard

A React + Vite + TypeScript trading terminal for the QuantTrade platform.

## Run (development)

```bash
cd dashboard
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` and `/ws` to the FastAPI backend on
`http://localhost:8000` (see `vite.config.ts`). Start the backend first:

```bash
uvicorn quanttrade.api.app:app --reload
```

If the backend is down the UI still renders with empty/placeholder data.

## Build (production)

```bash
npm run build        # outputs static assets to dist/
npm run preview      # preview the production build
```

Serve `dist/` behind any static host / reverse proxy, pointing `/api` and `/ws`
at the QuantTrade API service.

## Structure

- `src/api/` — typed REST client + response types
- `src/hooks/useWebSocket.ts` — auto-reconnecting WebSocket for live updates
- `src/components/` — Portfolio summary, equity chart, positions, trades,
  strategy performance, risk metrics, AI predictions, market scanner
- `src/App.tsx` — tabbed terminal layout wiring it together
