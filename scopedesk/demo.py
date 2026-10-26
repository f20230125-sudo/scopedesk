"""Fictional worked enquiry; corrections are deliberately left for the reviewer."""
import copy
from . import services as s

ENQUIRY = """Please scope 120 laptops: 80 at Dubai and 40 at Sharjah.
There are also 20 loose drives at Dubai; destroy these on-site before collection.
Reuse the laptops. Destroy their embedded drives on-site: 80 Dubai and 40 Sharjah.
All data work must remain on-site at each location. Equipment collection follows data work.
Please confirm the access windows before arranging the service."""
CSV = b"item,quantity,site,category,identifier,unit\nLaptop,70,Dubai,equipment,0001,items\nLaptop,50,Sharjah,equipment,0002,items\nLoose drive,20,Dubai,media,0003,items\n"


def requirement(kind,item,quantity,site,ref):
    return dict(kind=kind,item=item,quantity=quantity,site=site,precision="exact",refs=[ref],acknowledged=False,basis="")


def create_demo(db,wid,valid=False):
    cid = s.create_case(db,wid,"Acacia Demo Systems","Two-site laptop refresh" if not valid else "Reuse equipment, destroy embedded media",ENQUIRY)
    pid = s.preview(db,wid,cid,CSV,",","quantity","acacia-inventory.csv")
    mapping = {k:k for k in ("item","quantity","site","category","identifier","unit")}
    s.map_preview(db,wid,cid,pid,mapping,1)
    s.commit_import(db,wid,cid,pid,mapping,1)
    c = s.case(db,wid,cid)
    state = c["state"]
    for a in state["allocations"]:
        a["outcome"] = "reuse"
    # These three classes of conflict are deliberately planted and have actual source locations.
    state["allocations"].append(dict(row_id="S2-1",quantity=20,site="Dubai",outcome="destroy",refs=["S1:L3"]))
    state["media_actions"][0].update(action="destroy",location="offsite",collection="after")
    for rid,site,q in [("S2-1","Dubai",80),("S2-2","Sharjah",40)]:
        state["media_actions"].append(dict(row_id=rid,quantity=q,site=site,action="destroy",location="onsite",collection="after",refs=["S1:L3"]))
    state["requirements"] = [requirement("equipment","Laptop",120,"","S1:L1"),requirement("equipment","Laptop",80,"Dubai","S1:L1"),requirement("equipment","Laptop",40,"Sharjah","S1:L1"),requirement("media","Loose drive",20,"Dubai","S1:L2"),requirement("embedded","Laptop",80,"Dubai","S1:L3"),requirement("embedded","Laptop",40,"Sharjah","S1:L3"),requirement("onsite","",None,"","S1:L4")]
    state["followups"] = [dict(text="Confirm access windows at Dubai and Sharjah before scheduling.",refs=["S1:L5"])]
    s.save_state(db,wid,cid,c["version"],state,"Seeded fictional scope with deliberate allocation and location conflicts.")
    if valid:
        resolve_demo(db,wid,cid)
    return cid


def corrected_state(state,sid):
    state = copy.deepcopy(state)
    state["allocations"] = [dict(row_id="S2-1",quantity=80,site="Dubai",outcome="reuse",refs=[f"{sid}:L1"]),dict(row_id="S2-2",quantity=40,site="Sharjah",outcome="reuse",refs=[f"{sid}:L1"])]
    for rid,q in [("S2-1",80),("S2-2",40)]:
        state["overrides"][rid] = dict(quantity=q,reason="Customer corrected the site quantities; the overall laptop count stays 120.",refs=[f"{sid}:L1"])
    state["media_actions"][0].update(location="onsite",refs=[f"{sid}:L3"])
    return state


CORRECTION = """Confirmed inventory correction: 80 laptops at Dubai and 40 at Sharjah.
Reuse all laptops. Whole-equipment destruction was entered in error; destroy embedded drives only.
Destroy all 20 loose drives on-site at Dubai. Collect equipment only after on-site media work."""


def resolve_demo(db,wid,cid):
    c = s.case(db,wid,cid)
    sid = s.add_statement(db,wid,cid,c["version"],"customer clarification",CORRECTION)
    c = s.case(db,wid,cid)
    s.save_state(db,wid,cid,c["version"],corrected_state(c["state"],sid),"Applied customer clarification: site counts corrected, equipment overlap removed, loose-drive work on-site.")
