# Publication preparation and execution status

Publication was already authorised. Vercel team access now works. On 26 October 2026 a separate Flask project `prj_3ZZAml6EwIlwO9DAZTPkS7ip1XjX` was created and linked in the approved team. Its verified assigned hostname is `scopedesk-chi.vercel.app`; no application has been deployed there. Production trusted-host and CRM-origin settings are configured. Neon remains unconnected and no persistent PostgreSQL database has been provisioned.

ScopeDesk includes a Flask WSGI entrypoint, `/health`, public assets, `vercel.json`, production configuration guards and a psycopg path with explicit versioned migrations. Production refuses SQLite and a missing/short secret, sets Secure cookies and HSTS. These are prepared paths, not evidence of a deployed service. All currently recorded runtime verification is SQLite over local HTTP.

Once actual provider access is available:

1. Project creation and linking are complete. Verify the recorded identity and preserve the independent LoopDesk and FollowDesk projects.
2. Provision separate persistent PostgreSQL databases for ScopeDesk and LoopDesk. Confirm any charge before provisioning a paid service. Use separate preview/production databases and secrets.
3. Configure `APP_ENV=production`, `SCOPEDESK_DATABASE_URL` and a random `SCOPEDESK_SECRET_KEY` of at least 32 characters. LoopDesk retains `DATABASE_URL` and `SECRET_KEY`. Never package credentials or print their values.
4. Run the full isolated PostgreSQL suites using dedicated test database URLs. Both fixtures create/drop unique per-test schemas. Record results separately from SQLite. Test rollback, version predicates, composite foreign keys, cascades, duplicate imports and newer-revision locks on PostgreSQL.
5. Apply migrations once before traffic: `python -m flask --app app migrate` in each checkout. Do not execute migrations at import or during deployment builds.
6. Prepare the complete suite with `../followdesk/scripts/prepare-suite.py`. Each checksum manifest and runtime payload is bound to its verified project ID. The output excludes secrets, original databases, private CVs, tests, screenshots, wheels and recordings.
7. Recheck current official Flask deployment settings, deploy to the intended projects, and verify HTTPS `/health`, demo creation, full reviewed handoff journey, cookies, headers, cross-workspace denial and restart persistence. Record exact tested URLs and separate hosted evidence. `SCOPEDESK_LOOPDESK_URL` supplies the validated HTTPS CRM origin. Local development defaults to port 5055; production has no localhost link by default.
8. Only after those checks pass, add a tested public link to the application materials. University submission remains manual.

No PostgreSQL execution, remote CI execution or hosted verification is claimed. Provider authorisation is distinct from the publication permission already granted by the user. The packaged local application remains usable while provider access is pending.

## Security review deployment gate

Apply all pending migrations, including database-backed request buckets and workspace revocation. Set explicit trusted hostnames using the application-specific `*_TRUSTED_HOSTS` variable, a real random secret and PostgreSQL. Cookie security is enforced after configuration overrides. Verify provider edge protection and connecting-client identity before tuning limits; arbitrary forwarding headers are deliberately ignored. Run the PostgreSQL suite, deployed HTTPS/session/host/origin tests and normal handoff journey before publishing. See `../../security-review/README.md` for the local audit and remaining checks. All three projects are to be deployed together later, following completion of the third project.
