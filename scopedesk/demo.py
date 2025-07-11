"""Fictional worked enquiry; corrections are deliberately left for the reviewer."""
import copy
from . import services as s
from . import domain as d

EXAMPLES = {
    "approximate-monitors": dict(title="Approximate monitor count",client="Juniper Example Offices",mode="quantity",
        shows="Approximate enquiry counts need acknowledgement and an explicit inventory count basis.",
        enquiry="Please scope about 200 monitors at Dubai for reuse.\nOur attached store count lists 192; the final count is still to be confirmed.",
        csv=b"item,quantity,site,category,identifier,unit\nMonitor,192,Dubai,equipment,MON-0001,items\n"),
    "duplicate-register": dict(title="Repeated identifiers in a laptop register",client="Willow Example Studio",mode="register",
        shows="Repeated identifiers need a recorded decision; leading zeros remain unchanged.",
        enquiry="Please scope these three laptops at Sharjah for reuse.\nTwo register entries share serial 000042; please keep both entries pending our check.",
        csv=b"item,site,category,identifier,unit\nLaptop,Sharjah,equipment,000042,items\nLaptop,Sharjah,equipment,000042,items\nLaptop,Sharjah,equipment,000007,items\n"),
    "unsupported-unit": dict(title="Monitor list supplied in boxes",client="Elm Example Design",mode="quantity",
        shows="A box count stays blocked until an item count and unit correction are recorded.",
        enquiry="Please scope monitors at Dubai for reuse.\nThe list records four boxes; we have not confirmed the number of monitors inside.",
        csv=b"item,quantity,site,category,identifier,unit\nMonitor,4,Dubai,equipment,BOX-0001,boxes\n"),
}


def create_example(db,wid,key):
    if key not in EXAMPLES:
        raise d.ValidationError("Choose one of the three available fictional examples.")
    example = EXAMPLES[key]
    cid = s.create_case(db,wid,example["client"],example["title"],example["enquiry"])
    pid = s.preview(db,wid,cid,example["csv"],",",example["mode"],key+".csv")
    mapping = {k:k for k in ("item","site","category","identifier","unit")}
    if example["mode"] == "quantity":
        mapping["quantity"] = "quantity"
    s.map_preview(db,wid,cid,pid,mapping,1)
    s.commit_import(db,wid,cid,pid,mapping,1)
    c = s.case(db,wid,cid)
    state = c["state"]
    for allocation in state["allocations"]:
        allocation.update(outcome="reuse",refs=allocation["refs"]+["S1:L1"])
    item,quantity,site = ("Laptop",3,"Sharjah") if key == "duplicate-register" else ("Monitor",200 if key == "approximate-monitors" else 4,"Dubai")
    state["requirements"] = [requirement("equipment",item,quantity,site,"S1:L1")]
    if key == "approximate-monitors":
        state["requirements"][0]["precision"] = "approximate"
    elif key == "unsupported-unit":
        # No item count is asserted by the enquiry; this is the unresolved box count from the CSV.
        state["requirements"][0]["refs"] = ["S2:R1:quantity","S2:R1:unit"]
        state["followups"] = [dict(text="Confirm the monitor item count before correcting the box quantity and unit.",refs=["S1:L2"])]
    s.save_state(db,wid,cid,c["version"],state,"Loaded fictional example; unresolved count or identifier evidence remains visible.")
    return cid

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
