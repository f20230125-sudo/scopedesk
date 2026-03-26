import copy
import io
import json
import pytest
from werkzeug.exceptions import NotFound
from scopedesk import domain as d, services as s
from scopedesk.db import Database,migrate
from scopedesk.demo import create_demo,resolve_demo,CSV
from scopedesk.contract import read_handoff


def test_worked_conflicts_resolve_and_review_is_immutable(db,wid):
    cid=create_demo(db,wid)
    before=s.sources(db,wid,cid)
    codes={f["code"] for f in d.findings(s.rows(db,wid,cid),s.case(db,wid,cid)["state"])}
    assert {"equipment_overlap","count_mismatch","onsite_conflict"}<=codes
    resolve_demo(db,wid,cid)
    c=s.case(db,wid,cid)
    assert d.findings(s.rows(db,wid,cid),c["state"])==[]
    assert s.sources(db,wid,cid)[:2]==before
    number=s.review(db,wid,cid,c["version"])
    raw=s.export_handoff(db,wid,cid,number)
    payload=read_handoff(raw.encode())
    assert sum(r["quantity"] for r in payload["scope"] if r["kind"]=="equipment")==120
    assert sum(r["quantity"] for r in payload["scope"] if r["kind"]=="loose_media")==20
    assert sum(r["quantity"] for r in payload["scope"] if r["kind"]=="embedded_media")==120
    assert "0001" not in raw and CSV.decode() not in raw
    assert s.export_handoff(db,wid,cid,number)==raw
    snapshot=s.get_revision(db,wid,cid,number)["snapshot"]
    c=s.case(db,wid,cid)
    sid=s.add_statement(db,wid,cid,c["version"],"reviewer statement","Access windows remain unconfirmed.")
    assert sid=="S4"
    assert s.revision_list(db,wid,cid)[0]["superseded"]
    assert s.get_revision(db,wid,cid,number)["snapshot"]==snapshot
    with pytest.raises(d.Conflict):s.export_handoff(db,wid,cid,number)
    assert s.review(db,wid,cid,s.case(db,wid,cid)["version"])==2


def test_blockers_prevent_review(db,wid):
    cid=create_demo(db,wid)
    version=s.case(db,wid,cid)["version"]
    with pytest.raises(d.ValidationError):s.review(db,wid,cid,version)
    assert s.case(db,wid,cid)["version"]==version
    assert s.revision_list(db,wid,cid)==[]


def test_assumptions_and_count_basis_stay_in_handoff(db,wid):
    cid=create_demo(db,wid,valid=True)
    c=s.case(db,wid,cid)
    state=c["state"]
    state["assumptions"]=[dict(text="Customer access window to be confirmed.",refs=["S1:L5"])]
    state["requirements"][0].update(precision="approximate",quantity=121,acknowledged=True,basis="Inventory allocations total 120, pending final on-site check.")
    s.save_state(db,wid,cid,c["version"],state,"Accepted approximate count with basis; access uncertainty remains visible.")
    rev=s.review(db,wid,cid,s.case(db,wid,cid)["version"])
    p=read_handoff(s.export_handoff(db,wid,cid,rev).encode())
    assert p["review_status"]=="Reviewed with assumptions" and len(p["assumptions"])==2


def test_stale_edit_and_atomic_rollback(db,wid,monkeypatch):
    cid=create_demo(db,wid,True)
    c=s.case(db,wid,cid)
    s.add_statement(db,wid,cid,c["version"],"reviewer statement","Reviewed schedule.")
    with pytest.raises(d.Conflict):s.save_state(db,wid,cid,c["version"],c["state"],"Stale correction")
    current=s.case(db,wid,cid)
    count=len(s.sources(db,wid,cid))
    def fail(*args):raise RuntimeError("Injected audit failure")
    monkeypatch.setattr(s,"audit",fail)
    with pytest.raises(RuntimeError):s.add_statement(db,wid,cid,current["version"],"customer clarification","New source")
    assert s.case(db,wid,cid)==current and len(s.sources(db,wid,cid))==count


def test_all_references_resolve(db,wid):
    cid=create_demo(db,wid,True)
    c=s.case(db,wid,cid)
    refs=d.ref_index(s.sources(db,wid,cid))
    d.validate_shape(c["state"],s.rows(db,wid,cid),refs)
    for group in ("allocations","requirements","media_actions","assumptions","followups"):
        assert all(ref in refs for r in c["state"][group] for ref in r["refs"])
    assert refs["S2:R1:identifier"]=="0001"
    assert "80 laptops" in refs["S3:L1"]


def test_http_intake_mapping_and_exports(client,db,wid):
    data=dict(csrf_token="fixture",client="Example <script>bad()</script>",title="Manual scope",enquiry="Two laptops.\nReuse equipment, no media included.")
    response=client.post("/cases/new",data=data)
    assert response.status_code==303
    url=response.headers["Location"]
    cid=url.rsplit("/",1)[1]
    response=client.post(url+"/preview",data=dict(csrf_token="fixture",inventory=(io.BytesIO(b"item;qty;id;site\nLaptop;2;0001;Dubai"),"inventory.csv"),delimiter=";",mode="quantity"))
    assert response.status_code==303
    mapping_url=response.headers["Location"]
    mapped=dict(csrf_token="fixture",version=1,item="item",quantity="qty",identifier="id",site="site",default_category="equipment",action="preview")
    assert b"0001" in client.post(mapping_url,data=mapped).data
    mapped["action"]="commit"
    assert client.post(mapping_url,data=mapped).status_code==303
    html=client.get(url).data
    assert b"&lt;script&gt;bad()&lt;/script&gt;" in html and b"<script>bad()" not in html
    state=s.case(db,wid,cid)["state"]
    state["allocations"][0]["outcome"]="reuse"
    state["requirements"]=[dict(kind="equipment",item="Laptop",quantity=2,site="",precision="exact",acknowledged=False,basis="",refs=["S1:L1"])]
    assert client.post(url+"/scope",data=dict(csrf_token="fixture",version=2,state=json.dumps(state),reason="Confirmed source-linked scope")).status_code==303
    response=client.post(url+"/review",data=dict(csrf_token="fixture",version=3))
    assert response.status_code==303
    brief=client.get(response.headers["Location"])
    assert b"Revision 1" in brief.data
    download=client.get(url+"/brief?revision=1&download=1")
    assert "attachment" in download.headers["Content-Disposition"]
    assert client.get(url+"/handoff/1.json").status_code==200
    assert b"DRAFT" in client.get(url+"/brief").data
    assert "DRAFT" in client.get(url+"/allocations.csv").headers["Content-Disposition"]


def test_workspace_denies_all_record_types(client,db,wid):
    other=s.workspace(db)
    cid=create_demo(db,other,True)
    rev=s.review(db,other,cid,s.case(db,other,cid)["version"])
    for url in [f"/cases/{cid}",f"/cases/{cid}/brief?revision={rev}",f"/cases/{cid}/allocations.csv",f"/cases/{cid}/handoff/{rev}.json"]:
        assert client.get(url).status_code==404
    for action in ("statement","scope","review"):
        response=client.post(f"/cases/{cid}/{action}",data=dict(csrf_token="fixture",version=1,kind="reviewer statement",text="Forged",state="{}",reason="Forged"))
        assert response.status_code==404


def test_csrf_expiry_size_and_cookie(client,db,wid,app):
    assert client.post("/cases/new",data={}).status_code==400
    assert app.config["SESSION_COOKIE_NAME"]=="scopedesk_session"
    with pytest.raises(d.ValidationError):s.create_case(db,wid,"Client","Title","x"*32769)
    assert client.post("/cases/new",data=b"a"*(601*1024),content_type="application/octet-stream").status_code==413
    with db.transaction():db.execute("UPDATE workspaces SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(wid,))
    assert client.get("/cases").status_code==303
    s.workspace(db)
    assert not db.one("SELECT id FROM workspaces WHERE id=?",(wid,))


def test_restart_persistence(db,wid,app):
    cid=create_demo(db,wid,True)
    reopened=Database(app.config["DATABASE_URL"],app.config.get("DATABASE_SCHEMA"))
    try:assert s.case(reopened,wid,cid)["client"]=="Acacia Demo Systems"
    finally:reopened.close()


def test_assumption_origin_in_scope_cannot_hide_as_fact(db,wid):
    cid=create_demo(db,wid,True)
    c=s.case(db,wid,cid)
    sid=s.add_statement(db,wid,cid,c["version"],"assumption","Laptop counts are provisional pending the final count.")
    c=s.case(db,wid,cid)
    state=c["state"]
    state["allocations"][0]["refs"]=[f"{sid}:L1"]
    s.save_state(db,wid,cid,c["version"],state,"Recorded an assumption as the equipment allocation basis.")
    r=s.review(db,wid,cid,s.case(db,wid,cid)["version"])
    p=read_handoff(s.export_handoff(db,wid,cid,r).encode())
    assert p["review_status"]=="Reviewed with assumptions"
    assert p["assumptions"][0]["text"]=="Laptop counts are provisional pending the final count."


def test_mapping_must_match_actual_preview(db,wid):
    cid=s.create_case(db,wid,"Client","New inventory","Two laptops.")
    pid=s.preview(db,wid,cid,b"item,qty\nLaptop,2",",","quantity","input.csv")
    mapping=dict(item="item",quantity="qty",default_category="equipment")
    with pytest.raises(d.ValidationError,match="Preview this exact mapping"):
        s.commit_import(db,wid,cid,pid,mapping,1)
    s.map_preview(db,wid,cid,pid,mapping,1)
    changed=dict(mapping,default_category="media")
    with pytest.raises(d.ValidationError):s.commit_import(db,wid,cid,pid,changed,1)
    s.commit_import(db,wid,cid,pid,mapping,1)
    assert len(s.rows(db,wid,cid))==1


def test_failed_import_rolls_back_version_sources_and_rows(db,wid,monkeypatch):
    cid=s.create_case(db,wid,"Client","Atomic import","Two laptops.")
    pid=s.preview(db,wid,cid,b"item,qty\nLaptop,2",",","quantity","input.csv")
    mapping=dict(item="item",quantity="qty",default_category="equipment")
    s.map_preview(db,wid,cid,pid,mapping,1)
    def fail(*args):raise RuntimeError("Injected import audit failure")
    monkeypatch.setattr(s,"audit",fail)
    with pytest.raises(RuntimeError):s.commit_import(db,wid,cid,pid,mapping,1)
    assert s.case(db,wid,cid)["version"]==1
    assert len(s.sources(db,wid,cid))==1 and not s.rows(db,wid,cid)
    assert s.get_preview(db,wid,cid,pid)
