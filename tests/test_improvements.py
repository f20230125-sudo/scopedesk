import copy
import io
import json
import re
import pytest
from scopedesk import domain as d, services as s
from scopedesk.demo import EXAMPLES,create_demo,create_example
from scopedesk.presentation import finding_groups,reference_summary


@pytest.mark.parametrize("key,expected",[
    ("approximate-monitors",[("approximate_difference",True,["S1:L1","S2:R1:item","S2:R1:quantity","S2:R1:site","S2:R1:identifier","S2:R1:category","S2:R1:unit"])]),
    ("duplicate-register",[("duplicate_identifier",True,[f"S2:R{i}:{field}" for field in ("item","site","identifier","category","unit")]) for i in (1,2)]),
    ("unsupported-unit",[("unsupported_unit",True,[f"S2:R1:{field}" for field in ("item","quantity","site","identifier","category","unit")])]),
])
def test_examples_have_exact_findings_and_source_labels(db,wid,key,expected):
    cid=create_example(db,wid,key)
    c=s.case(db,wid,cid)
    found=d.findings(s.rows(db,wid,cid),c["state"])
    assert [(f["code"],f["blocking"],f["refs"]) for f in found]==expected
    sources=s.sources(db,wid,cid)
    assert [(src["id"],src["kind"]) for src in sources]==[("S1","enquiry"),("S2","csv")]
    assert sources[0]["raw_text"]==EXAMPLES[key]["enquiry"]
    assert sources[1]["raw_text"]==EXAMPLES[key]["csv"].decode()
    assert all(ref in d.ref_index(sources) for f in found for ref in f["refs"])
    with pytest.raises(d.ValidationError):s.review(db,wid,cid,c["version"])


@pytest.mark.parametrize("acknowledged,basis,blocked",[(False,"Inventory counts 192 monitors.",True),(True,"",True),(True,"   ",True),(True,"Use the 192 listed monitors pending final count.",False)])
def test_approximate_example_needs_acknowledgement_and_basis(db,wid,acknowledged,basis,blocked):
    cid=create_example(db,wid,"approximate-monitors")
    c=s.case(db,wid,cid)
    c["state"]["requirements"][0].update(acknowledged=acknowledged,basis=basis)
    s.save_state(db,wid,cid,c["version"],c["state"],"Record the count basis decision.")
    found=d.findings(s.rows(db,wid,cid),c["state"])
    assert [f["blocking"] for f in found]==[blocked]
    if not blocked:
        rev=s.review(db,wid,cid,s.case(db,wid,cid)["version"])
        payload=json.loads(s.export_handoff(db,wid,cid,rev))
        assert payload["review_status"]=="Reviewed with assumptions"
        assert payload["assumptions"]==[dict(text="Approximate count basis: "+basis,refs=["S1:L1"])]


def test_register_decision_preserves_every_identifier(db,wid):
    cid=create_example(db,wid,"duplicate-register")
    original=s.rows(db,wid,cid)
    assert [r["identifier"] for r in original]==["000042","000042","000007"]
    c=s.case(db,wid,cid)
    c["state"]["duplicate_decisions"]["000042"]=dict(text="Retain both entries pending customer verification; do not merge.",refs=["S1:L2","S2:R1:identifier","S2:R2:identifier"])
    s.save_state(db,wid,cid,c["version"],c["state"],"Retain both register entries with a recorded review decision.")
    assert d.findings(original,c["state"])==[]
    assert s.rows(db,wid,cid)==original
    rev=s.review(db,wid,cid,s.case(db,wid,cid)["version"])
    assert s.get_revision(db,wid,cid,rev)["snapshot"]["case"]["state"]["duplicate_decisions"]==c["state"]["duplicate_decisions"]


def test_unit_example_requires_source_linked_correction(db,wid):
    cid=create_example(db,wid,"unsupported-unit")
    c=s.case(db,wid,cid)
    sid=s.add_statement(db,wid,cid,c["version"],"customer clarification","Confirmed: the four boxes contain eight monitors in total at Dubai for reuse.")
    c=s.case(db,wid,cid)
    c["state"]["overrides"]["S2-1"]=dict(quantity=8,unit="items",reason="Customer confirmed the item count.",refs=[f"{sid}:L1"])
    c["state"]["allocations"][0].update(quantity=8,refs=[f"{sid}:L1"])
    c["state"]["requirements"][0].update(quantity=8,refs=[f"{sid}:L1"])
    s.save_state(db,wid,cid,c["version"],c["state"],"Correct box quantity to the confirmed monitor count.")
    assert d.findings(s.rows(db,wid,cid),c["state"])==[]
    assert s.rows(db,wid,cid)[0]["unit"]=="boxes"
    assert s.sources(db,wid,cid)[1]["raw_text"]==EXAMPLES["unsupported-unit"]["csv"].decode()


@pytest.mark.parametrize("key",list(EXAMPLES))
def test_load_example_route_and_repeat_open_existing(client,db,wid,key):
    response=client.post("/cases/examples",data=dict(csrf_token="fixture",example=key))
    assert response.status_code==303
    cid=response.location.rsplit("/",1)[1]
    assert s.case(db,wid,cid)["title"]==EXAMPLES[key]["title"]
    assert client.post("/cases/examples",data=dict(csrf_token="fixture",example=key)).location==response.location
    assert db.one("SELECT count(*) AS n FROM cases WHERE workspace_id=?",(wid,))["n"]==1
    page=client.get("/cases").get_data(as_text=True)
    assert "Open loaded example" in page and EXAMPLES[key]["shows"] in page


@pytest.mark.parametrize("key",[None,"","unknown","../demo","<script>alert(1)</script>","x"*161,"x"*4096])
def test_invalid_example_rejected_without_writes(client,db,wid,key):
    data=dict(csrf_token="fixture")
    if key is not None:data["example"]=key
    response=client.post("/cases/examples",data=data)
    assert response.status_code==422
    assert "Choose one of the three" in response.get_data(as_text=True)
    assert db.one("SELECT count(*) AS n FROM cases WHERE workspace_id=?",(wid,))["n"]==0


def test_example_csrf_and_cross_workspace_isolation(client,db,wid):
    other=s.workspace(db)
    theirs=create_example(db,other,"duplicate-register")
    before=s.case(db,other,theirs)
    assert client.get("/cases/examples").status_code==404
    assert client.post("/cases/examples",data=dict(example="duplicate-register")).status_code==400
    assert client.post("/cases/examples",data=dict(csrf_token="fixture",example="duplicate-register"),headers={"Origin":"https://attacker.example"}).status_code==403
    response=client.post("/cases/examples",data=dict(csrf_token="fixture",example="duplicate-register",workspace_id=other,cid=theirs))
    assert response.status_code==303 and theirs not in response.location
    assert client.get("/cases/"+theirs).status_code==404
    assert s.case(db,other,theirs)==before
    assert s.case(db,wid,response.location.rsplit("/",1)[1])["title"]==EXAMPLES["duplicate-register"]["title"]


def test_example_last_slot_and_full_workspace(client,db,wid):
    for i in range(19):s.create_case(db,wid,"Fictional Example",f"Manual case {i}","Synthetic enquiry.")
    loaded=client.post("/cases/examples",data=dict(csrf_token="fixture",example="approximate-monitors"))
    assert loaded.status_code==303
    before=db.one("SELECT count(*) AS n FROM sources WHERE workspace_id=?",(wid,))["n"]
    assert client.post("/cases/examples",data=dict(csrf_token="fixture",example="unsupported-unit")).status_code==429
    assert db.one("SELECT count(*) AS n FROM cases WHERE workspace_id=?",(wid,))["n"]==20
    assert db.one("SELECT count(*) AS n FROM sources WHERE workspace_id=?",(wid,))["n"]==before
    page=client.get("/cases").get_data(as_text=True)
    assert "20-case workspace limit is reached" in page
    assert page.count('class="secondary" disabled')==2
    assert client.post("/cases/examples",data=dict(csrf_token="fixture",example="approximate-monitors")).location==loaded.location


def test_compact_references_and_groups_preserve_findings(client,db,wid):
    cid=create_demo(db,wid)
    c=s.case(db,wid,cid)
    found=d.findings(s.rows(db,wid,cid),c["state"])
    before=copy.deepcopy(found)
    groups=finding_groups(found)
    assert {g["code"] for g in groups}=={f["code"] for f in found}
    assert sum(len(g["items"]) for g in groups)==len(found)
    page=client.get("/cases/"+cid).get_data(as_text=True)
    assert "Counts do not agree" in page and "On-site restriction conflict" in page
    assert 'aria-label="S2 original CSV records"' in page
    assert 'href="#ref-S2:R1:item">S2 row 1</a>' in page
    assert 'All 7 references' in page
    for finding in found:
        assert finding["message"].replace("'","&#39;") in page
        assert all(f'href="#ref-{ref}"' in page for ref in finding["refs"])
        assert all(ref in d.clarification_draft(found) for ref in finding["refs"])
    assert found==before
    assert reference_summary(["S2:R1:item","S2:R1:identifier","S1:L3","S2:R2:unit","S2:R1:item"])==[
        dict(ref="S2:R1:item",label="S2 row 1"),dict(ref="S1:L3",label="S1 line 3"),dict(ref="S2:R2:unit",label="S2 row 2")]


def test_summary_reflects_derived_state_and_superseded_revision(client,db,wid):
    cid=create_example(db,wid,"approximate-monitors")
    url="/cases/"+cid
    page=client.get(url).get_data(as_text=True)
    assert "Resolve 1 blocking finding" in page and "<dd>None</dd>" in page
    c=s.case(db,wid,cid)
    c["state"]["requirements"][0].update(acknowledged=True,basis="Use 192 listed monitors pending confirmation.")
    c["state"]["assumptions"]=[dict(text="Final access window is unconfirmed.",refs=["S1:L2"])]
    s.save_state(db,wid,cid,c["version"],c["state"],"Acknowledge the count basis and access-window uncertainty.")
    page=client.get(url).get_data(as_text=True)
    assert "Acknowledged assumptions</dt><dd>2</dd>" in page
    assert 'href="#revisions">Review & create revision' in page
    rev=s.review(db,wid,cid,s.case(db,wid,cid)["version"])
    assert len(s.get_revision(db,wid,cid,rev)["snapshot"]["assumptions"])==2
    page=client.get(url).get_data(as_text=True)
    assert "Open reviewed revision 1" in page
    c=s.case(db,wid,cid)
    sid=s.add_statement(db,wid,cid,c["version"],"assumption","Collection date remains provisional.")
    c=s.case(db,wid,cid)
    c["state"]["followups"]=[dict(text="Confirm the provisional date.",refs=[f"{sid}:L1"])]
    s.save_state(db,wid,cid,c["version"],c["state"],"Use the recorded scheduling assumption.")
    page=client.get(url).get_data(as_text=True)
    assert "Acknowledged assumptions</dt><dd>3</dd>" in page
    assert "Source documents</dt><dd>3</dd>" in page
    assert "Latest reviewed revision</dt><dd>1 (superseded)</dd>" in page


def test_specific_page_titles_metadata_and_errors(client,db,wid):
    cid=create_demo(db,wid,True)
    pages=["/","/cases","/cases/new","/cases/"+cid,"/cases/"+cid+"/brief","/missing-page"]
    titles=[]
    for url in pages:
        response=client.get(url)
        assert response.status_code==(404 if url=="/missing-page" else 200)
        html=response.get_data(as_text=True)
        title=re.search(r"<title>(.*?)</title>",html).group(1)
        titles.append(title)
        assert f'property="og:title" content="{title}"' in html
        assert 'property="og:description"' in html and 'name="theme-color" content="#164c3b"' in html
        assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert len(set(titles))==len(titles)
    error=client.get("/missing-page").get_data(as_text=True)
    assert "Page or case not found" in error and 'href="/cases">Return to cases' in error
    anonymous=client.application.test_client().get("/missing-page")
    assert anonymous.status_code==404 and b"Open a demo workspace" in anonymous.data


def test_mapping_title_and_hostile_metadata_remain_escaped(client,db,wid):
    title='Fictional " scope <script>alert(1)</script>'
    cid=s.create_case(db,wid,"Fictional Example",title,"Two monitors at Dubai.")
    pid=s.preview(db,wid,cid,b"item,quantity\nMonitor,2\n",",","quantity","fictional.csv")
    mapping=client.get(f"/cases/{cid}/imports/{pid}")
    assert mapping.status_code==200
    html=mapping.get_data(as_text=True)
    assert "Map inventory columns" in html and "Map and preview 1 inventory records" in html
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html and '&#34;' in html
    page=client.get("/cases/"+cid).get_data(as_text=True)
    assert '<script>alert(1)</script>' not in page


def test_unexpected_error_is_redacted_with_cases_recovery(client,app,monkeypatch):
    app.config["PROPAGATE_EXCEPTIONS"]=False
    def fail(*args):raise RuntimeError("Synthetic internal diagnostic marker")
    monkeypatch.setattr(s,"case",fail)
    response=client.get("/cases/synthetic")
    assert response.status_code==500
    assert b"Synthetic internal diagnostic marker" not in response.data
    assert b"unexpected error" in response.data and b'Return to cases' in response.data
