# Deployment runbook

Hosted since 27 October 2026 at <https://scopedesk-chi.vercel.app>.

## Where it runs

- **Application:** a Vercel project on the free Hobby plan (Python/Flask runtime; `app.py` exports `app`, `pyproject.toml` declares the entrypoint and the dependencies Vercel installs, `vercel.json` sets a 30-second maximum duration and bundles `public/assets/**` into the function).
- **Database:** a Neon PostgreSQL database on Neon's free plan, added through the Vercel Marketplace and separate from LoopDesk's and FollowDesk's. The app uses Neon's pooled endpoint; migrations use the direct, unpooled endpoint.

Nothing here needs a paid plan. If a free limit blocks a step, stop and change the design instead of upgrading.

## Environment

| Name | Purpose |
| --- | --- |
| `APP_ENV=production` | Turns on the production guards below. |
| `SCOPEDESK_DATABASE_URL` | PostgreSQL connection string with TLS. SQLite is refused in production. |
| `SCOPEDESK_SECRET_KEY` | Random session secret, at least 32 characters. Stored as a write-only (sensitive) variable. |
| `SCOPEDESK_TRUSTED_HOSTS` | Exact host names the app answers to. |
| `SCOPEDESK_LOOPDESK_URL` | Validated HTTPS origin of LoopDesk for the navigation link. Production has no localhost default. |

Credentials live in the provider's settings, never in source, chat or logs. Production and preview must use separate databases and secrets.

## Release procedure, in order

1. Run the test suites (`python scripts/manage.py test`; the PostgreSQL job runs in GitHub Actions) and the local browser journey.
2. Apply migrations before deploying code that needs them: `python -m flask --app app migrate` with `SCOPEDESK_DATABASE_URL` set to the unpooled Neon URL. Migrations never run at import or during a build.
3. Build the allowlisted runtime payload with `scripts/prepare-deployment.py` (or `../followdesk/scripts/prepare-suite.py` for all three apps). It contains only runtime code, assets, migrations and dependency configuration, with a checksum manifest, and excludes tests, examples, screenshots, databases and credentials. Deploy it to the production project through Vercel's deployments API.
4. Verify the hosted app: `python scripts/live-smoke.py`, then the browser journey with `SCOPEDESK_URL=https://scopedesk-chi.vercel.app SCOPEDESK_ONLY=1 node scripts/browser-check.mjs`. Record the results in [verification](verification.md).

A weekly GitHub Actions workflow (`live-smoke.yml`) runs the smoke check against the hosted app.

## Defects that only showed up when hosted

- Vercel installs from `pyproject.toml`, not `requirements.txt`, so the dependency list is duplicated there.
- On Vercel `public/` is served by the CDN and is not part of the function bundle. The reviewed-brief page reads `public/assets/app.css` at request time to embed its styles, so `vercel.json` lists `public/assets/**` in `includeFiles`. Without it that page returned a 500 on the hosted app and nowhere else.

## Production configuration guards

Production refuses SQLite, an absent or short secret and missing trusted hosts; it enables Secure, HttpOnly, SameSite=Lax session cookies and HSTS. Request limits are keyed on the visitor's address: behind Vercel that is the platform-set `X-Vercel-Forwarded-For` header (Vercel overwrites client-supplied values), elsewhere forwarding headers are ignored because anyone could spoof them.

## Free-tier behaviour

Neon suspends an idle database, so the first request after a quiet period can take a second or two longer. The demo keeps a workspace for 24 hours, and expired workspaces are removed opportunistically when a new one is created.
