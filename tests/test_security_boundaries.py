import copy
import io
import json
import pytest
from werkzeug.exceptions import TooManyRequests
from scopedesk import services as s,domain as d
from scopedesk.demo import create_demo


@pytest.mark.parametrize("revision",["9"*100,"0","-1","nan","1.0"])
def test_bad_revision_queries_fail_closed(client,db,wid,revision):
    cid=create_demo(db,wid,True)
    assert client.get(f"/cases/{cid}/brief?revision={revision}").status_code==422
    assert client.get(f"/cases/{cid}/allocations.csv?revision={revision}").status_code==422
    if revision.isascii() and revision.isdigit() and revision!="0":
        assert client.get(f"/cases/{cid}/handoff/{revision}.json").status_code==422


def test_reference_arrays_cannot_amplify_findings(db,wid):
    cid=create_demo(db,wid,True)
    c=s.case(db,wid,cid)
    c["state"]["allocations"][0]["refs"]=["S1:L1"]*1500
    with pytest.raises(d.ValidationError):s.save_state(db,wid,cid,c["version"],c["state"],"Malicious reference amplification.")
    assert s.case(db,wid,cid)["version"]==c["version"]
    c["state"]["allocations"][0]["refs"]=["S1:L1"]*2
    with pytest.raises(d.ValidationError):s.save_state(db,wid,cid,c["version"],c["state"],"Repeated references.")


def test_preview_quota_preserves_case_and_existing_data(client,db,wid):
    cid=s.create_case(db,wid,"Client","Upload preview budget","Two laptops.")
    for i in range(11):
        response=client.post(f"/cases/{cid}/preview",data=dict(csrf_token="fixture",inventory=(io.BytesIO(b"item,qty\nLaptop,2"),"input.csv"),delimiter=",",mode="quantity"))
        assert response.status_code==(303 if i<10 else 429)
    assert int(response.headers["Retry-After"])>0
    assert db.one("SELECT count(*) AS n FROM import_previews WHERE workspace_id=?",(wid,))["n"]==10
    assert s.case(db,wid,cid)["version"]==1
    assert len(s.sources(db,wid,cid))==1


def test_source_quota_rollback_keeps_version_consistent(db,wid):
    cid=s.create_case(db,wid,"Client","Source budget","Two laptops.")
    for i in range(39):s.add_statement(db,wid,cid,i+1,"reviewer statement",f"Synthetic statement {i}")
    before=s.case(db,wid,cid)
    with pytest.raises(TooManyRequests):s.add_statement(db,wid,cid,before["version"],"reviewer statement","Over budget")
    assert s.case(db,wid,cid)==before
    assert len(s.sources(db,wid,cid))==40


def test_case_quota_rejects_excess_cases(db,wid):
    for i in range(20):s.create_case(db,wid,"Client",f"Case {i}","Synthetic enquiry")
    with pytest.raises(TooManyRequests):s.create_case(db,wid,"Client","Over budget","Synthetic enquiry")
    assert db.one("SELECT count(*) AS n FROM cases WHERE workspace_id=?",(wid,))["n"]==20


def test_unicode_source_storage_budget_counts_bytes_and_rolls_back(db,wid):
    cid=s.create_case(db,wid,"Client","Byte budget","Synthetic enquiry")
    rejected=False
    for i in range(39):
        before=s.case(db,wid,cid)
        try:s.add_statement(db,wid,cid,before["version"],"reviewer statement","é"*16000)
        except TooManyRequests as exc:
            assert "storage limit" in str(exc)
            assert s.case(db,wid,cid)==before
            assert len(s.sources(db,wid,cid))<40
            rejected=True
            break
    assert rejected


def test_multiple_csvs_cannot_bypass_case_inventory_limit(db,wid):
    cid=s.create_case(db,wid,"Client","Aggregate CSV budget","Synthetic enquiry")
    mapping=dict(item="item",quantity="qty",default_category="equipment")
    first=s.preview(db,wid,cid,b"item,qty\n"+b"Laptop,1\n"*600,",","quantity","first.csv")
    s.map_preview(db,wid,cid,first,mapping,1)
    s.commit_import(db,wid,cid,first,mapping,1)
    before=s.case(db,wid,cid)
    second=s.preview(db,wid,cid,b"item,qty\n"+b"Laptop,1\n"*401,",","quantity","second.csv")
    s.map_preview(db,wid,cid,second,mapping,before["version"])
    with pytest.raises(d.ValidationError,match="across all imports"):
        s.commit_import(db,wid,cid,second,mapping,before["version"])
    assert s.case(db,wid,cid)==before and len(s.rows(db,wid,cid))==600
    assert s.get_preview(db,wid,cid,second)


def test_findings_cannot_expand_into_a_reference_cartesian_product(db,wid):
    cid=create_demo(db,wid,True)
    c=s.case(db,wid,cid)
    s.add_statement(db,wid,cid,c["version"],"reviewer statement","\n".join(f"Synthetic source line {i}" for i in range(20)))
    c=s.case(db,wid,cid)
    refs=list(d.ref_index(s.sources(db,wid,cid)))
    state=c["state"]
    state["allocations"][0]["quantity"]=0
    for i in range(20):
        state["allocations"].append(dict(row_id="S2-1",quantity=0,site="Dubai",outcome="reuse",refs=refs[i:i+32]))
    original=copy.deepcopy(state)
    d.validate_shape(state,s.rows(db,wid,cid),d.ref_index(s.sources(db,wid,cid)))
    found=d.findings(s.rows(db,wid,cid),state)
    assert max(len(f["refs"]) for f in found)<=32
    assert any(f.get("additional_reference_count",0)>0 for f in found)
    assert "additional references" in d.clarification_draft(found)
    assert state==original  # Bound output; retain all original allocation evidence.
