CREATE TABLE workspaces (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE cases (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 client TEXT NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, UNIQUE(workspace_id,id)
);
CREATE TABLE sources (
 id TEXT NOT NULL, workspace_id TEXT NOT NULL, case_id TEXT NOT NULL, kind TEXT NOT NULL,
 name TEXT NOT NULL, raw_text TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(workspace_id,case_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE source_rows (
 id TEXT NOT NULL, workspace_id TEXT NOT NULL, case_id TEXT NOT NULL, source_id TEXT NOT NULL,
 position INTEGER NOT NULL, cells TEXT NOT NULL, interpreted TEXT NOT NULL,
 PRIMARY KEY(workspace_id,case_id,id),
 FOREIGN KEY(workspace_id,case_id,source_id) REFERENCES sources(workspace_id,case_id,id) ON DELETE CASCADE
);
CREATE TABLE import_previews (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, case_id TEXT NOT NULL,
 raw_text TEXT NOT NULL, parsed TEXT NOT NULL, mode TEXT NOT NULL, filename TEXT NOT NULL,
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE revisions (
 workspace_id TEXT NOT NULL, case_id TEXT NOT NULL, revision INTEGER NOT NULL,
 case_version INTEGER NOT NULL, reviewed_at TEXT NOT NULL, status TEXT NOT NULL,
 snapshot TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(workspace_id,case_id,revision),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE audit_events (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, case_id TEXT NOT NULL,
 kind TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX ix_scope_expiry ON workspaces(expires_at);
