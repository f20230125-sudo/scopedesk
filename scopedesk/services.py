"""Transactional workspace commands and immutable sources/review snapshots."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.exceptions import NotFound
from . import domain as d
from .contract import canonical, digest, read_handoff, HandoffError
from .security import positive_integer, quota, byte_quota


def uid():
    return uuid.uuid4().hex


def stamp():
    return datetime.now(timezone.utc).isoformat()


def workspace(db):
    wid = uid()
    with db.transaction():
        db.execute("DELETE FROM workspaces WHERE expires_at<=?", (stamp(),))
        if db.one("SELECT count(*) AS n FROM workspaces")["n"] >= 250:
            raise d.ValidationError("Demo capacity reached. Try again after an existing workspace expires.")
        db.execute("INSERT INTO workspaces VALUES (?,?,?)", (wid, stamp(), (datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()))
    return wid


def case(db, wid, cid):
    value = db.one("SELECT * FROM cases WHERE workspace_id=? AND id=?", (wid,cid))
    if not value:
        raise NotFound("Case not available in this workspace.")
    value["state"] = json.loads(value["state"])
    return value


def sources(db, wid, cid):
    case(db,wid,cid)
    result = db.all("SELECT * FROM sources WHERE workspace_id=? AND case_id=? ORDER BY created_at,id", (wid,cid))
    for row in result:
        row["metadata"] = json.loads(row["metadata"])
    return result


def rows(db, wid, cid):
    case(db,wid,cid)
    return [json.loads(r["interpreted"]) for r in db.all("SELECT interpreted FROM source_rows WHERE workspace_id=? AND case_id=? ORDER BY source_id,position", (wid,cid))]


def audit(db,wid,cid,kind,body):
    quota(db,"audit_events",wid,1000)
    db.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?)",(uid(),wid,cid,kind,body,stamp()))


def source_insert(db,wid,cid,kind,text,name="",metadata=None):
    quota(db,"sources",wid,40,case_id=cid)
    byte_quota(db,"sources","raw_text",wid,len(text.encode("utf-8")),1024*1024)
    sid = "S" + str(db.one("SELECT count(*) AS n FROM sources WHERE workspace_id=? AND case_id=?",(wid,cid))["n"]+1)
    db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)",(sid,wid,cid,kind,name or kind,text,canonical(metadata or {}),stamp()))
    return sid


def bump(db,wid,cid,version,state=None):
    version = positive_integer(version)
    if version is None:
        raise d.Conflict("Missing or invalid version. Reload the case.")
    sql = "UPDATE cases SET version=version+1" + (",state=?" if state is not None else "") + " WHERE workspace_id=? AND id=? AND version=?"
    args = ((canonical(state),) if state is not None else ()) + (wid,cid,version)
    if db.execute(sql,args).rowcount != 1:
        raise d.Conflict("The case changed after you opened it. Reload before saving; your edit was not applied.")


def create_case(db,wid,client,title,enquiry):
    if not client.strip() or not title.strip() or max(len(client),len(title)) > 160:
        raise d.ValidationError("Client and title are required, at most 160 characters each.")
    if not enquiry.strip() or len(enquiry.encode("utf-8")) > 32768 or "\x00" in enquiry:
        raise d.ValidationError("Enquiry must contain text and be at most 32 KiB without null characters.")
    cid = uid()
    with db.transaction():
        quota(db,"cases",wid,20)
        db.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?)",(cid,wid,client.strip(),title.strip(),canonical(d.empty_state()),1,stamp()))
        source_insert(db,wid,cid,"enquiry",enquiry,"Customer enquiry")
        audit(db,wid,cid,"created","Case created; original enquiry preserved.")
    return cid


def preview(db,wid,cid,raw,delimiter,mode,filename):
    case(db,wid,cid)
    if mode not in {"register","quantity"}:
        raise d.ValidationError("Select asset register or quantity list explicitly.")
    text,parsed = d.parse_csv(raw,delimiter)
    pid = uid()
    with db.transaction():
        quota(db,"import_previews",wid,10,case_id=cid)
        quota(db,"import_previews",wid,30)
        byte_quota(db,"import_previews","raw_text",wid,len(text.encode("utf-8")),1024*1024)
        db.execute("INSERT INTO import_previews VALUES (?,?,?,?,?,?,?)",(pid,wid,cid,text,canonical(parsed),mode,filename[:160]))
    return pid


def get_preview(db,wid,cid,pid):
    case(db,wid,cid)
    value = db.one("SELECT * FROM import_previews WHERE workspace_id=? AND case_id=? AND id=?",(wid,cid,pid))
    if not value:
        raise NotFound("Import preview is not available.")
    value["parsed"] = json.loads(value["parsed"])
    return value


def commit_import(db,wid,cid,pid,mapping,version):
    with db.transaction():
        c = case(db,wid,cid)
        p = get_preview(db,wid,cid,pid)
        if len(rows(db,wid,cid))+len(p["parsed"]["rows"]) > 1000:
            raise d.ValidationError("A case may include at most 1,000 inventory records across all imports.")
        if p["parsed"].get("mapped_preview") != mapping or str(p["parsed"].get("mapped_version")) != str(version):
            raise d.ValidationError("Preview this exact mapping before confirming the import.")
        bump(db,wid,cid,version)
        # Validate before source insertion. A failed import rolls back source and version together.
        d.interpret(p["parsed"],mapping,p["mode"],"preview")
        sid = source_insert(db,wid,cid,"csv",p["raw_text"],p["filename"],dict(p["parsed"],mapping=mapping,mode=p["mode"]))
        interpreted = d.interpret(p["parsed"],mapping,p["mode"],sid)
        state = c["state"]
        for row in interpreted:
            db.execute("INSERT INTO source_rows VALUES (?,?,?,?,?,?,?)",(row["id"],wid,cid,sid,row["position"],canonical(row["cells"]),canonical(row)))
            if row["category"] == "equipment":
                state["allocations"].append(dict(row_id=row["id"],quantity=row["quantity"],site=row["site"],outcome="undecided",refs=row["refs"]))
            elif row["category"] == "media":
                state["media_actions"].append(dict(row_id=row["id"],quantity=row["quantity"],site=row["site"],action="undecided",location="unknown",collection="none",refs=row["refs"]))
        db.execute("UPDATE cases SET state=? WHERE workspace_id=? AND id=?",(canonical(state),wid,cid))
        db.execute("DELETE FROM import_previews WHERE workspace_id=? AND case_id=? AND id=?",(wid,cid,pid))
        audit(db,wid,cid,"import",f"Imported {len(interpreted)} records as {p['mode']}; original cells preserved in {sid}.")


def map_preview(db,wid,cid,pid,mapping,version):
    p = get_preview(db,wid,cid,pid)
    interpreted = d.interpret(p["parsed"],mapping,p["mode"],"preview")
    parsed = dict(p["parsed"],mapped_preview=mapping,mapped_version=str(version))
    with db.transaction():
        db.execute("UPDATE import_previews SET parsed=? WHERE workspace_id=? AND case_id=? AND id=?",(canonical(parsed),wid,cid,pid))
    return interpreted


def add_statement(db,wid,cid,version,kind,text):
    if kind not in {"customer clarification","reviewer statement","assumption"} or not text.strip() or len(text.encode()) > 32768:
        raise d.ValidationError("Choose an origin and enter a statement up to 32 KiB.")
    with db.transaction():
        case(db,wid,cid)
        bump(db,wid,cid,version)
        sid = source_insert(db,wid,cid,kind,text)
        audit(db,wid,cid,"clarification",f"{kind.capitalize()} recorded as {sid}. Structured corrections still require saving.")
    return sid


def save_state(db,wid,cid,version,state,reason):
    if not reason.strip() or len(reason) > 500:
        raise d.ValidationError("Describe the correction or review decision in 1–500 characters.")
    d.validate_shape(state,rows(db,wid,cid),d.ref_index(sources(db,wid,cid)))
    with db.transaction():
        bump(db,wid,cid,version,state)
        audit(db,wid,cid,"scope_edit",reason)


def revision_list(db,wid,cid):
    c = case(db,wid,cid)
    result = db.all("SELECT revision,case_version,reviewed_at,status FROM revisions WHERE workspace_id=? AND case_id=? ORDER BY revision DESC",(wid,cid))
    for r in result:
        r["superseded"] = r["case_version"] != c["version"]
    return result


def get_revision(db,wid,cid,revision):
    c = case(db,wid,cid)
    revision = positive_integer(revision,1000000)
    if revision is None:
        raise d.ValidationError("Revision must be a positive integer of at most 1,000,000.")
    r = db.one("SELECT * FROM revisions WHERE workspace_id=? AND case_id=? AND revision=?",(wid,cid,revision))
    if not r:
        raise NotFound("Revision is not available.")
    r.update(snapshot=json.loads(r["snapshot"]),payload=json.loads(r["payload"]),superseded=r["case_version"] != c["version"])
    return r


def review_assumptions(state,origin):
    assumptions = list(state["assumptions"])
    referenced = {ref for key in ("allocations","requirements","media_actions","assumptions","followups") for row in state[key] for ref in row["refs"]}
    referenced.update(ref for row in list(state["overrides"].values())+list(state["duplicate_decisions"].values()) for ref in row["refs"])
    index = d.ref_index(origin)
    assumption_sources = {source["id"] for source in origin if source["kind"] == "assumption"}
    for ref in sorted(referenced):
        if ref.split(":")[0] in assumption_sources and not any(ref in a["refs"] for a in assumptions):
            assumptions.append(dict(text=index[ref],refs=[ref]))
    for req in state["requirements"]:
        if req["precision"] == "approximate" and req["acknowledged"] and req["basis"].strip():
            assumptions.append(dict(text=f"Approximate count basis: {req['basis']}",refs=req["refs"]))
    return assumptions,referenced


def review(db,wid,cid,version):
    with db.transaction():
        c = case(db,wid,cid)
        inventory, origin = rows(db,wid,cid), sources(db,wid,cid)
        d.validate_shape(c["state"],inventory,d.ref_index(origin))
        if any(f["blocking"] for f in d.findings(inventory,c["state"])):
            raise d.ValidationError("Resolve all blocking findings before review.")
        # Lock also prevents simultaneous reviews and makes any prior revision superseded.
        bump(db,wid,cid,version)
        latest = db.one("SELECT max(revision) AS n FROM revisions WHERE workspace_id=? AND case_id=?",(wid,cid))
        number = (latest["n"] or 0)+1
        state = c["state"]
        assumptions,referenced = review_assumptions(state,origin)
        reviewed_at = stamp()
        review_status = "Reviewed with assumptions" if assumptions else "Reviewed"
        scope = d.grouped_scope(inventory,state)
        used_refs = {ref for row in scope for ref in row["source_refs"]}
        used_refs.update(ref for row in assumptions+state["followups"] for ref in row["refs"])
        used_refs.update(referenced)
        payload = dict(schema_version=1,source_system="ScopeDesk",case_id=cid,revision=number,review_status=review_status,reviewed_at=reviewed_at,client_display_name=c["client"],scope=scope,assumptions=assumptions,followups=state["followups"],source_references=[dict(ref=ref,origin=next(s["kind"] for s in origin if s["id"] == ref.split(":")[0])) for ref in sorted(used_refs)])
        payload["digest"] = digest(payload)
        try:
            read_handoff(canonical(payload).encode())
        except HandoffError as exc:
            raise d.ValidationError(f"Scope cannot be handed off: {exc}") from None
        snapshot = dict(case=dict(c,version=int(version)+1),rows=inventory,sources=origin,findings=d.findings(inventory,state),scope=scope,assumptions=assumptions)
        quota(db,"revisions",wid,20,case_id=cid)
        byte_quota(db,"revisions","snapshot",wid,len(canonical(snapshot).encode("utf-8")),8*1024*1024)
        db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)",(wid,cid,number,int(version)+1,reviewed_at,review_status,canonical(snapshot),canonical(payload)))
        audit(db,wid,cid,"review",f"Immutable revision {number}: {review_status}.")
    return number


def export_handoff(db,wid,cid,revision):
    r = get_revision(db,wid,cid,revision)
    if r["superseded"]:
        raise d.Conflict("This revision is superseded. Review the current scope before creating a new handoff.")
    return canonical(r["payload"])
