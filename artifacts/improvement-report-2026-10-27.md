# ScopeDesk improvement report — 27 October 2026

Implemented in the ScopeDesk working copy only. No push, deployment, provider change, Neon access, runtime dependency, schema migration or handoff-contract change was made. Hosting-status material was left unchanged.

## Changes

- `public/assets/app.css`, `scopedesk/templates/case.html`: original CSV columns have minimum widths, a named focusable scroll region, a visible horizontal-scroll hint and a sticky Record column. Record stays on one line and Unit is reachable at 1440, 1024 and 390 pixels. Print styles constrain brief columns to the page.
- `scopedesk/presentation.py`, `scopedesk/templates/base.html`, `scopedesk/templates/case.html`: findings are grouped by their unchanged codes with plain-English titles and counts. Each message remains visible. Compact source-row/line links lead to evidence; native details expose every exact reference supplied for that finding. The display transformation does not modify findings, source data, clarification-draft generation or export generation.
- `scopedesk/demo.py`, `scopedesk/__init__.py`, `scopedesk/templates/cases.html`: three optional fictional examples use existing case/import/state services. Approximate monitors produce only `approximate_difference`; the register produces two `duplicate_identifier` findings; boxes produce only `unsupported_unit`. Cards explain what each example shows, open an already-loaded example and display workspace capacity. The ordinary atomic 20-case quota applies, including direct POSTs at capacity.
- `scopedesk/services.py`, `scopedesk/__init__.py`, `scopedesk/templates/case.html`: a summary shows blockers, acknowledged assumptions, source documents, scope version and latest reviewed revision, including superseded status. Its primary link leads to findings, review controls or the current reviewed brief. Assumptions are derived using the helper shared with revision creation, including approximate-count bases and referenced assumption sources. Whitespace-only count bases are treated as empty.
- `scopedesk/templates/{base,landing,cases,case,new,mapping,brief,error}.html`, `scopedesk/__init__.py`: concrete headings, distinct page titles, Open Graph title/description, theme color and 404/error recovery links. Unknown addresses return 404 even without a workspace; unexpected-error pages use a fixed redacted message. The CSP and CSRF requirements remain in place.
- `tests/test_improvements.py`: 26 new parameterized service/HTTP checks cover exact findings/source labels, acknowledgement/basis boundaries, duplicate decisions/leading zeros, source-preserving unit corrections, repeat loading, quota boundaries, hostile selections, CSRF/origin checks, workspace isolation, summaries, references, escaped metadata and error recovery. The 24 existing authored domain fixtures remain unchanged.
- `scripts/browser-check.mjs`, `scripts/improvement-checks.mjs`: extended real local browser checks; optional `SCOPEDESK_ONLY=1` retains ScopeDesk journeys while explicitly skipping LoopDesk import. Default artifacts now go to a new dated directory. No frontend/runtime dependency was added; existing Playwright/axe installations were reused.
- `scripts/manage.py`: pytest cache now goes to `.local/pytest-cache`, avoiding the inaccessible existing `.pytest_cache` directory and keeping caches under `.local/`.
- `README.md`, `docs/verification.md`, `docs/architecture.md`: current behavior, limits and local verification counts documented separately from historical/hosted evidence.

## Verification

Full requested suite, with TEMP/TMP/PYTHONPYCACHEPREFIX under this working copy's `.local/`:

```text
.venv\Scripts\python scripts\manage.py test
126 passed in 3.66s
```

Evidence: `artifacts/improvement-tests-2026-10-27.txt` and the updated `artifacts/pytest-sqlite.xml`. No original test was removed, skipped or weakened. Earlier runs observed a mismatch in the existing sibling security-module parity assertion. The final full run passes it without either security module being edited by this task.

Browser command:

```powershell
$env:SCOPEDESK_ONLY = '1'
$env:SCOPEDESK_URL = 'http://localhost:5058'
.venv\Scripts\python scripts\manage.py browser
```

Result: **79 checks passed; 22 accessibility scans; zero detected automated accessibility violations; no recorded JavaScript or HTTP 5xx errors.** Chromium 156.0.8078.4, real local Flask responses and SQLite, no mocked business responses. Result JSON: `artifacts/browser-check-2026-10-27/browser-verification.json`; console output: `artifacts/improvement-browser-2026-10-27.txt`.

The browser checks cover both seeded cases, correction/review, immutable/superseded revisions, standalone HTML and JSON downloads, manual mapping, stale edits and workspace isolation, plus all three new examples. Additional checks cover grouped findings, exact-reference disclosure/navigation, count-basis assumptions, next-step links, CSV scrolling/sticky headers at all three requested widths, printed layout, and an approximate-example review through the JSON fallback with JavaScript disabled.

## Screenshot and print evidence

Before: `artifacts/improvement-before-2026-10-27/`.

After: `artifacts/browser-check-2026-10-27/`, files beginning `improved-`.

Both sets cover landing, cases, case, draft brief, new enquiry, inventory mapping and 404 pages at **1440×900** and **390×844** viewports. Full-page screenshots can be taller than the viewport. Additional case evidence covers **1024×900**; after screenshots show the scrolled Unit column at 1440, 1024 and 390 pixels. Print evidence includes before/after print-media screenshots and `improved-brief-print.pdf` (A4). Historical screenshots were not overwritten. Desktop/mobile case, scrolled-source and print captures were visually inspected in addition to layout assertions and axe scans.

## Limits, deviations and lead review

- The existing domain security cap of **32 exact labels per computed finding** remains intact, together with its explicit additional-reference notice. The supplied two-site case and all new examples fit within the cap and expose their complete finding references. For larger aggregates, overflow evidence remains in original sources/allocations and their exports; this change does not add an uncapped per-finding list or expand the clarification draft beyond its existing cap. This is the retained limitation against the brief's general request for every exact finding reference, to preserve the existing reference-amplification defense. No source/allocation reference was deleted.
- Browser verification used an isolated `.local/improvement-browser.sqlite3` database and an IPv6 loopback listener on port **5058**, reached through `localhost`. Another process was serving older code at `127.0.0.1:5058`; the first browser attempt hit it. It was left alone. All ScopeDesk servers started by this task were stopped after verification.
- The full ScopeDesk → LoopDesk → FollowDesk journey was **not rerun**. `SCOPEDESK_ONLY=1` avoided operating on sibling apps. The existing LoopDesk import checks remain available in the default script, and reviewed ScopeDesk JSON/HTML downloads passed locally. The lead should rerun the cross-app journey after merging.
- PostgreSQL cannot be run on this PC and was not tested. No provider or hosted verification is claimed. The lead should run PostgreSQL CI and the deployed journey separately.
- Examples use existing client/title pairs to find a previously loaded example. Concurrent loads are still bounded by atomic case quotas, but strict uniqueness for simultaneous first loads is not guaranteed by a new database constraint; no schema change was introduced. A manually created case with the same client/title pair will be opened as an existing example.
- Existing semantic-review responsibility remains: resolvable citations do not prove that a free-text statement supports a count, unit correction or duplicate decision. Tests verify preservation and review rules, not domain advice. Automated axe/print checks do not replace a human assistive-technology or physical-printer review.

All requested feature areas were addressed. The retained large-finding reference cap, simultaneous first-load uniqueness, PostgreSQL and cross-app/hosted verification are the remaining review limits above. No new runtime dependencies, contract fields, finding codes, external assets or JavaScript-only feature flows were introduced.
