"""Emit a checksum-recorded public runtime payload; sends nothing."""
from pathlib import Path
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]
files=[]
for relative in ("app.py","requirements.txt","pyproject.toml","vercel.json"):
    files.append(ROOT/relative)
for folder in ("scopedesk","public","migrations"):
    files.extend(p for p in (ROOT/folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py",".html",".js",".css",".svg",".sql"})
payload=[]
for p in sorted(files):
    content=p.read_text(encoding="utf-8")
    payload.append(dict(file=p.relative_to(ROOT).as_posix(),data=content,encoding="utf-8"))
folder=ROOT/".local/deployment"
folder.mkdir(parents=True,exist_ok=True)
(folder/"runtime-files.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
manifest=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)]
(folder/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(f"Prepared {len(payload)} allowlisted runtime files; no network action performed.")
