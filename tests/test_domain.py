import copy
import json
from pathlib import Path
import pytest
from scopedesk import domain as d
from scopedesk.demo import requirement

FIXTURES = json.loads(Path(__file__).with_name("fixtures.json").read_text())


def authored_input(changes):
    rows = [dict(id="r1",item="Laptop",identifier="0001",quantity=2,raw_quantity="2",site="Dubai",category="equipment",unit="items",refs=["S2:R1:item"]),dict(id="r2",item="Drive",identifier="0002",quantity=1,raw_quantity="1",site="Dubai",category="media",unit="items",refs=["S2:R2:item"])]
    state = d.empty_state()
    state["allocations"] = [dict(row_id="r1",quantity=2,site="Dubai",outcome="reuse",refs=["S2:R1:item"])]
    state["media_actions"] = [dict(row_id="r2",quantity=1,site="Dubai",action="destroy",location="onsite",collection="after",refs=["S2:R2:item"])]
    state["requirements"] = [requirement("equipment","Laptop",2,"","S1:L1"),requirement("media","Drive",1,"Dubai","S1:L2")]
    for key,value in changes:
        if key == "embedded":
            state["media_actions"].append(dict(row_id="r1",quantity=value,site="Dubai",action="destroy",location="onsite",collection="after",refs=["S1:L3"]))
        elif key == "split":
            state["allocations"][0]["quantity"]=1
            state["allocations"].append(dict(row_id="r1",quantity=1,site="Sharjah",outcome="recycle",refs=["S1:L1"]))
        elif key == "equipment_quantity":
            rows[0]["quantity"]=state["allocations"][0]["quantity"]=state["requirements"][0]["quantity"]=value
        elif key == "precision":state["requirements"][0]["precision"]=value
        elif key == "approximate_accepted":state["requirements"][0].update(precision="approximate",quantity=value,acknowledged=True,basis="Counted two items during customer inventory check.")
        elif key == "onsite":state["requirements"].append(requirement("onsite","",None,"","S1:L3"))
        elif key == "duplicate":rows[1]["identifier"]=rows[0]["identifier"]
        elif key == "duplicate_reviewed":state["duplicate_decisions"]["0001"]={"text":"Separate asset and media identifiers confirmed by customer.","refs":["S1:L3"]}
        elif key == "overlap":state["allocations"].append(dict(row_id="r1",quantity=1,site="Dubai",outcome="destroy",refs=["S1:L1"]))
        elif key == "allocation_quantity":state["allocations"][0]["quantity"]=value
        elif key == "site_requirements":state["requirements"] += [requirement("equipment","Laptop",1,"Dubai","S1:L1"),requirement("equipment","Laptop",1,"Sharjah","S1:L1")]
        elif key == "location":state["media_actions"][0]["location"]=value
        elif key == "collection":state["media_actions"][0]["collection"]=value
        elif key == "source_unknown":rows[0].update(quantity=None,raw_quantity=value)
        elif key == "unit":rows[0]["unit"]=value
        elif key == "embedded_requirement":state["requirements"].append(requirement("embedded","Laptop",value,"Dubai","S1:L3"))
        elif key == "identifier":rows[0]["identifier"]=value
        elif key == "category":rows[0]["category"]=value
        elif key == "required_quantity":state["requirements"][0]["quantity"]=value
        elif key == "loose_required":state["requirements"][1]["quantity"]=value
        elif key == "exclude":state["overrides"]["r1"]={"excluded":True,"reason":"Customer duplicate","refs":["S1:L3"]}
        elif key == "no_requirements":state["requirements"]=[]
        else:raise AssertionError(key)
    return rows,state


@pytest.mark.parametrize("fixture",FIXTURES,ids=lambda f:f["id"])
def test_authored_domain_fixture(fixture):
    rows,state=authored_input(fixture["changes"])
    actual=[[f["code"],f["blocking"],sorted(set(f["refs"]))] for f in d.findings(rows,state)]
    assert actual == fixture["expected"]
    if fixture["group"] == "valid":
        assert not any(f[1] for f in actual)


def test_fixture_groups_are_eight_each():
    assert {group:sum(f["group"]==group for f in FIXTURES) for group in ("valid","conflicting","boundary")} == dict(valid=8,conflicting=8,boundary=8)


@pytest.mark.parametrize("raw,delimiter,error",[(b"a,a\n1,2",",","Duplicate"),(b"a,A \n1,2",",","Duplicate"),(b"a\n\xff",",","UTF-8"),(b"a,b\n1,2,3",",","more cells"),(b"a\n"+b"x"*4097,",","4 KiB"),(b"a\n"+b"1\n"*1001,",","1,000"),(b",".join([b"a"]*21)+b"\n1",",","1–20"),(b"a\n1","|","explicitly"),(b"a\n"+b"x"*(256*1024),",","256 KiB")],ids=["duplicate","casefold-duplicate","encoding","extra-cells","large-field","many-rows","many-columns","delimiter","file-size"])
def test_csv_rejections(raw,delimiter,error):
    with pytest.raises(d.ValidationError,match=error):d.parse_csv(raw,delimiter)


@pytest.mark.parametrize("delimiter",[",",";","\t"])
def test_csv_originals_and_unknowns(delimiter):
    raw=f'item{delimiter}qty{delimiter}serial\r\nLaptop{delimiter}bad{delimiter}00001\r\nLaptop{delimiter}0{delimiter}00002\r\n\r\n'.encode()
    text,parsed=d.parse_csv(raw,delimiter)
    result=d.interpret(parsed,{"item":"item","quantity":"qty","identifier":"serial","default_category":"equipment"},"quantity","S2")
    assert text==raw.decode() and len(result)==3
    assert result[0]["identifier"]=="00001" and result[0]["quantity"] is None
    assert result[1]["quantity"]==0 and result[2]["quantity"] is None
    assert "S2:R1:qty" in result[0]["refs"]
    register=d.interpret(parsed,{"item":"item"},"register","S2")
    assert all(r["quantity"]==1 for r in register)


def test_quantity_and_formula_boundaries():
    assert [d.quantity(v) for v in ["",None,"1.0","-1","1e3",True,0,"0001"]]==[None,None,None,None,None,None,0,1]
    rows,state=authored_input([])
    rows[0]["item"]="=HYPERLINK(\"x\")"
    assert "'=HYPERLINK" in d.allocation_csv(rows,state)
    assert "S1:L1" in d.clarification_draft([dict(message="Clarify count",refs=["S1:L1"])])


def test_invalid_refs_and_exclusion_reason_rejected():
    rows,state=authored_input([])
    refs={"S1:L1":"","S1:L2":"","S1:L3":"","S2:R1:item":"","S2:R2:item":""}
    d.validate_shape(state,rows,refs)
    state["requirements"][0]["refs"]=["S9:L9"]
    with pytest.raises(d.ValidationError):d.validate_shape(state,rows,refs)
    state["assumptions"]=[dict(text="\ud800",refs=["S1:L3"])]
    with pytest.raises(d.ValidationError,match="Unicode"):d.validate_shape(state,rows,refs)
    state["assumptions"]=[]
    state["requirements"][0]["refs"]=["S1:L1"]
    state["overrides"]["r1"]={"excluded":True,"reason":"","refs":["S1:L3"]}
    with pytest.raises(d.ValidationError):d.validate_shape(state,rows,refs)
