Security follow-up, 26 October 2026: current suite **92 passing checks** (`artifacts/security-pytest.xml`). The earlier figures below document the initial release. The focused 17-probe retest, 1,009 mutation/parser cases and 40-check attack browser journey are recorded in `../../security-review/README.md`. Both original browser journeys pass after the fixes. PostgreSQL and hosted verification remain pending.

# Verification report — 26 October 2026

## Local SQLite: passed

| Layer | Result | Evidence |
| --- | --- | --- |
| Authored domain fixtures | 24: eight valid, eight conflicting, eight boundary | `tests/fixtures.json`, exact expected findings and source labels authored before final UI verification |
| ScopeDesk automated checks | 51 passed | `artifacts/pytest-sqlite.xml` |
| LoopDesk automated checks | 71 passed, including the original 51 regression checks | `../loopdesk/artifacts/pytest-sqlite.xml` |
| ScopeDesk → LoopDesk browser journey | 43 checks passed using real local HTTP/service/database responses | `artifacts/browser-verification.json` |
| New desktop/mobile accessibility scans | 11 scans, zero automated violations | Same report and individual `*-axe.json` files |
| Original LoopDesk browser regression | 20 checks passed, ten scans, zero automated violations | `../loopdesk/artifacts/browser-verification.json` |
| Recording | Playable 71.32 seconds, 1440 × 960 | `artifacts/ScopeDesk-Demo.webm`, `video-verification.json`, chapter timings |

The original LoopDesk business/security checks remain. Its migration-idempotency assertion now expects the existing `001_initial` plus the additive `002_scopedesk`; it still verifies the exact installed migration set after repeated application. LoopDesk retains its original cookie name, and ScopeDesk uses `scopedesk_session`.

The fixtures cover equipment reuse with embedded-media destruction, quantity conservation and overlapping equipment allocations, matching overall totals with incorrect site counts, exact/approximate/missing/malformed/zero counts, loose versus embedded media, duplicate identifiers and reviewed decisions, leading zeros, unsupported units, on-site restrictions, collection sequencing, exclusions and missing requirements. Expected finding codes, blocking status and source locations are compared exactly. Valid fixtures produce no incorrect blocking findings.

Service/HTTP checks cover immutable input sources, every confirmed reference resolving, clarification corrections, old revisions superseded by later sources/edits, deterministic canonical JSON export, source-assumption origin appearing in review status and handoff, stale versions, transaction rollback including audit/source/import writes, isolated workspace access, expiry cleanup, CSRF failures, escaped HTML, formula-safe CSV, source-preserving delimiters and encoding/size/record/column limits. CSV commits are bound to the exact mapping actually previewed.

Importer checks cover strict schema/UTF-8/48 KiB validation, duplicate JSON keys, malformed nested values, digest failure, absent/unresolved references, extra raw-register fields, UTC timestamps and integer types. They also verify latest-revision idempotency, conflicting content, rejection of older revisions, newer history on one opportunity, preserved stage/owner/value/other CRM fields, active organisation/contact ownership, workspace denial and transactional rollback. Both contract copies are checked for byte parity when both local projects are available.

The real Chromium journey follows all planted blocker types through source navigation, editable clarification download, recorded customer response, source-linked corrections, immutable review, printable brief, standalone HTML download and reviewed JSON import. It repeats confirmation, edits existing CRM fields, imports a second reviewed revision with an assumption and confirms preserved CRM fields plus two history records. It also creates a manual case, uploads a semicolon CSV, previews the mapping, confirms leading-zero preservation, rejects a stale browser tab and denies another workspace access. There are no mocked business responses, JavaScript exceptions or HTTP 5xx responses.

Keyboard checks include the skip link, native form controls, native details elements, source links and focusable horizontally scrollable tables. Screenshots cover 1440-pixel desktop and 390-pixel mobile layouts without page overflow. Print media hides application controls. Automated accessibility evidence is limited to detectable issues; it is not a full accessibility certification. A human assistive-technology review was not performed.

The worked workflow is designed for approximately five minutes. The automated run completes it much faster, including screenshot/audit overhead, but **no human five-minute usability study or measured business improvement is claimed**. The recording is a paced real demonstration with added presentation captions.

## Offline Windows package

`scripts/package-release.py` builds allowlisted public-source and Windows offline archives including both apps and matching cached pinned wheels. It extracts to a fresh D: directory, creates two clean virtual environments, installs with `--no-index`, runs migrations, starts both apps on temporary ports, reviews a valid scope over HTTP, exports its JSON, imports it into LoopDesk and repeats confirmation with the same opportunity result. It checks separate cookies in one cookie jar. See the release's `OFFLINE-VERIFICATION.json` and `ScopeDesk-Release.json` for the actual execution result/checksum. The package is intended for the existing Windows x64/Python 3.14 installation; no claim is made about offline wheels for other operating systems or Python ABIs.

## PostgreSQL: not executed

Both database adapters and forward-only migrations support a psycopg path. Tests can create/drop unique per-test schemas on dedicated PostgreSQL databases. No PostgreSQL connection is available here, so locking, constraints and all workflows still require execution on that backend. Prepared CI jobs have not been run remotely. SQLite success does not establish PostgreSQL success.

## Hosted HTTPS: not executed

A fresh Vercel project read returned team-access HTTP 403. No ScopeDesk deployment or provisioned persistent PostgreSQL database exists. Secure-cookie/HSTS guards are prepared; no hosted availability, persistence, HTTPS journey or public URL is claimed. See `deployment.md` for the remaining provider-dependent work. Publication permission is already recorded; university submission remains manual.
