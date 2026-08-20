# Mission Control UI

TractusMind Mission Control is the Next.js control surface for the source-grounded backend.

## Stack

- Next.js 16.3 + React 19.2
- Tailwind CSS 4.3
- shadcn-compatible local component layer
- Motion for tactile transitions
- Lucide icons

The visual language is modern industrial skeuomorphism: graphite chassis, recessed evidence wells,
tactile controls, status LEDs, and restrained cyan/amber instrumentation. Chat content remains
comparatively flat for readability.

## Security boundary

The browser never stores the bearer credential in localStorage. `POST /api/session` validates the
credential against backend `/v1/me` and writes an HttpOnly, SameSite session cookie. Browser API
requests go through `/api/backend/*`; the Next.js server adds the credential and proxies only
allowlisted `v1` and `health` backend paths.

## Functional consoles

- `/` — grounded chat, citation markers, route/verification metadata, feedback
- `/sources` — source registry, snapshot commits, sync state, admin sync action
- `/ops` — ingestion summary and run channel
- `/quality` — human review queue and regression summary
- `/admin` — API-key identity provisioning and enable/disable controls

Navigation is role-aware: users see Copilot, operators gain Sources/Ops/Quality, admins gain Access.

## Local development

Run the backend stack plus the UI overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.ui.yml up --build
```

Mission Control is served at `http://localhost:3100`. Grafana keeps `http://localhost:3000`.

Or run the frontend directly:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## Production

Use the hardened backend compose plus the UI overlay:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.ui.prod.yml \
  up -d --build
```

The UI overlay replaces Caddy's upstream with the frontend container. The frontend talks to the API
only over the private backend network. Caddy remains the sole public edge on 443.

## Validation

`.github/workflows/frontend.yml` runs:

1. production dependency audit at HIGH severity,
2. TypeScript typecheck,
3. Next.js production build,
4. runtime Docker image build.

The workflow pins checkout/setup-node actions to immutable commit SHAs and uses Node 24.19.0 LTS.
