# Reviewed handoff contract, version 1

Both applications validate the exact object fields in `scopedesk/contract.py` / `loopdesk/scope_contract.py`. Upload must be UTF-8 JSON, at most 48 KiB, with no duplicate object keys, non-finite numbers or unsupported fields.

| Field | Meaning |
| --- | --- |
| schema_version / source_system | Integer `1` / literal `ScopeDesk` |
| case_id / revision | Stable case identity / positive integer, scoped to the receiving workspace |
| review_status / reviewed_at | `Reviewed` or `Reviewed with assumptions` / ISO 8601 UTC timestamp |
| client_display_name | Display text; never used to auto-match a CRM organisation |
| scope | Grouped equipment, loose_media and embedded_media quantities by item, site, outcome/action and media location/collection sequence |
| assumptions / followups | Text with resolvable source-reference labels |
| source_references | Reference labels and explicit origin: enquiry, csv, customer clarification, reviewer statement or assumption |
| digest | Lowercase hexadecimal SHA-256 of canonical payload excluding digest |

Canonical form is UTF-8, Unicode characters unescaped, object keys sorted, no optional whitespace, JSON finite numbers only (`json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)`). Array order is preserved. Quantity/revision booleans and numeric strings are rejected. Raw documents, serial registers, prices, certificate claims and unsupported fields are excluded. Hashes provide integrity checking and are easy to recompute; they are not a signature, identity proof or customer approval.

The salesperson previews the file, then selects existing active organisation/contact records and an owner in LoopDesk. New opportunity defaults are IT asset disposition / New / unknown value. The first next action derives from follow-ups and assumptions, or a fixed customer-discussion template. Later revisions add history to the existing opportunity without changing any CRM field. Same latest revision with identical canonical content is idempotent; changed content for the same revision, and revisions older than the latest received, are rejected. Case mappings never cross workspaces.

Offline import cannot detect a newer revision that has never been exported. A previously exported file can also remain on disk after ScopeDesk supersedes it. The user must obtain the current reviewed revision before relying on an offline handoff.
