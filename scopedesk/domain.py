"""Pure scope reconciliation. No inference of drive counts from equipment counts."""
import csv
import io
import json
import re
from collections import Counter, defaultdict


class ValidationError(ValueError):
    pass


class Conflict(ValidationError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def quantity(value):
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    return int(text) if re.fullmatch(r"[0-9]{1,7}", text) else None


def parse_csv(raw, delimiter):
    if len(raw) > 256 * 1024:
        raise ValidationError("CSV exceeds 256 KiB.")
    if delimiter not in {",", ";", "\t"}:
        raise ValidationError("Select comma, semicolon or tab explicitly.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("CSV must use UTF-8 encoding.") from None
    if "\x00" in text:
        raise ValidationError("CSV contains a null character.")
    try:
        reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""), delimiter=delimiter, strict=True)
        headers = next(reader, [])
        if not 1 <= len(headers) <= 20 or any(not h.strip() for h in headers):
            raise ValidationError("Use 1–20 nonempty column headers.")
        if len(set(h.strip().casefold() for h in headers)) != len(headers):
            raise ValidationError("Duplicate column headers are not supported.")
        rows = []
        for row in reader:
            # Even blank records are retained. Physical line and logical record numbers differ for quoted newlines.
            if len(row) > len(headers):
                raise ValidationError(f"Record {len(rows)+1} has more cells than headers.")
            rows.append(row + [""] * (len(headers) - len(row)))
            if len(rows) > 1000:
                raise ValidationError("CSV exceeds 1,000 records.")
            if any(len(c.encode("utf-8")) > 4096 for c in row):
                raise ValidationError(f"Record {len(rows)} has a field larger than 4 KiB.")
        if any(len(h.encode("utf-8")) > 160 for h in headers):
            raise ValidationError("Column headers must be at most 160 bytes.")
        if not rows:
            raise ValidationError("CSV has no records.")
        return text, {"headers": headers, "rows": rows, "delimiter": delimiter}
    except csv.Error as exc:
        raise ValidationError(f"Invalid CSV: {exc}") from None


def interpret(parsed, mapping, mode, sid):
    if mode not in {"register", "quantity"}:
        raise ValidationError("Choose asset register or quantity list.")
    headers = parsed["headers"]
    if mapping.get("item") not in headers:
        raise ValidationError("Map an item column.")
    if mode == "quantity" and mapping.get("quantity") not in headers:
        raise ValidationError("Quantity lists require a quantity column mapping.")
    for field in ("item", "quantity", "identifier", "site", "category", "unit"):
        if mapping.get(field) and mapping[field] not in headers:
            raise ValidationError(f"Unknown mapped column for {field}.")
    result = []
    for pos, values in enumerate(parsed["rows"], 1):
        cells = dict(zip(headers, values))
        def cell(key, default=""):
            return cells.get(mapping.get(key), default)
        rawq = "1" if mode == "register" else cell("quantity")
        category = cell("category", mapping.get("default_category", "unknown")).strip().lower()
        category = category if category in {"equipment", "media"} else "unknown"
        result.append(dict(id=f"{sid}-{pos}", source_id=sid, position=pos, cells=cells,
                           item=cell("item").strip(), identifier=cell("identifier"),
                           quantity=quantity(rawq), raw_quantity=rawq, site=cell("site").strip(),
                           category=category, unit=cell("unit", "items").strip().lower(),
                           refs=[f"{sid}:R{pos}:{h}" for h in dict.fromkeys(mapping.get(k) for k in ("item","quantity","site","identifier","category","unit")) if h in headers], mode=mode))
    return result


def empty_state():
    return dict(overrides={}, allocations=[], requirements=[], media_actions=[], duplicate_decisions={}, assumptions=[], followups=[])


def effective_rows(rows, state):
    return [dict(r, **state.get("overrides", {}).get(r["id"], {})) for r in rows]


def ref_index(sources):
    result = {}
    for source in sources:
        sid = source["id"]
        if source["kind"] == "csv":
            meta = source["metadata"]
            for i, values in enumerate(meta["rows"], 1):
                for h, value in zip(meta["headers"], values):
                    result[f"{sid}:R{i}:{h}"] = value
        else:
            for i, line in enumerate(source["raw_text"].splitlines() or [""], 1):
                result[f"{sid}:L{i}"] = line
    return result


def validate_shape(state, rows, refs):
    """Reject malformed edits, while retaining logical conflicts for review."""
    if not isinstance(state, dict) or set(state) != set(empty_state()):
        raise ValidationError("Scope state has missing or unsupported fields.")
    try:
        size = len(canonical(state).encode("utf-8"))
    except (UnicodeError,ValueError,RecursionError):
        raise ValidationError("Scope state contains invalid Unicode, numbers or excessive nesting.") from None
    if size > 240 * 1024:
        raise ValidationError("Scope edits exceed 240 KiB.")
    rowids = {r["id"] for r in rows}
    if not isinstance(state["overrides"], dict) or not isinstance(state["duplicate_decisions"], dict):
        raise ValidationError("Corrections and duplicate decisions must be objects.")
    def check_refs(obj):
        locs = obj.get("refs")
        if not isinstance(locs, list) or not 1 <= len(locs) <= 32 or any(not isinstance(r, str) or r not in refs for r in locs):
            raise ValidationError("Every confirmed detail needs resolvable source references.")
        if len(set(locs)) != len(locs):
            raise ValidationError("Source references must be distinct (maximum 32 per detail).")
    def string(obj, key, optional=False, limit=500):
        if not isinstance(obj.get(key), str) or len(obj[key]) > limit or (not optional and not obj[key].strip()):
            raise ValidationError(f"{key.replace('_',' ')} requires text (maximum {limit} characters).")
    for rid, override in state["overrides"].items():
        if rid not in rowids or not isinstance(override, dict) or set(override) - {"quantity", "category", "site", "item", "unit", "excluded", "reason", "refs"}:
            raise ValidationError("Invalid source-row correction.")
        check_refs(override)
        string(override, "reason")
        if "quantity" in override and override["quantity"] is not None and (type(override["quantity"]) is not int or not 0 <= override["quantity"] <= 9999999):
            raise ValidationError("Corrected quantities must be non-negative integers or unknown.")
        if "category" in override and override["category"] not in ("equipment", "media", "unknown"):
            raise ValidationError("Invalid category correction.")
        if "excluded" in override and type(override["excluded"]) is not bool:
            raise ValidationError("Exclusion must be true or false.")
        for key in ("site", "item", "unit"):
            if key in override:
                string(override, key, optional=True, limit=160)
    layouts = {
        "allocations": ({"row_id", "quantity", "site", "outcome", "refs"}, {"row_id", "quantity", "site", "outcome", "refs"}),
        "requirements": ({"kind", "item", "quantity", "site", "precision", "refs", "acknowledged", "basis"}, {"kind", "item", "quantity", "site", "precision", "refs", "acknowledged", "basis"}),
        "media_actions": ({"row_id", "quantity", "site", "action", "location", "collection", "refs"}, {"row_id", "quantity", "site", "action", "location", "collection", "refs"}),
        "assumptions": ({"text", "refs"}, {"text", "refs"}),
        "followups": ({"text", "refs"}, {"text", "refs"}),
    }
    for key, (allowed, required) in layouts.items():
        if not isinstance(state[key], list) or len(state[key]) > 2000:
            raise ValidationError(f"Invalid {key} list.")
        for obj in state[key]:
            if not isinstance(obj, dict) or set(obj) - allowed or required - set(obj):
                raise ValidationError(f"Invalid fields in {key}.")
            check_refs(obj)
            if "row_id" in obj and (not isinstance(obj["row_id"],str) or obj["row_id"] not in rowids):
                raise ValidationError("Allocation references an unknown row.")
            if "quantity" in obj and obj["quantity"] is not None and (type(obj["quantity"]) is not int or not 0 <= obj["quantity"] <= 9999999):
                raise ValidationError("Quantities must be non-negative integers or unknown.")
            for field in ("site", "item", "basis"):
                if field in obj:
                    string(obj, field, optional=True, limit=160)
            if key in {"assumptions", "followups"}:
                string(obj, "text")
            if key == "allocations" and obj["outcome"] not in ("reuse", "recycle", "destroy", "undecided"):
                raise ValidationError("Select an equipment outcome.")
            if key == "requirements" and (obj["kind"] not in ("equipment", "media", "embedded", "onsite") or obj["precision"] not in ("exact", "approximate") or type(obj["acknowledged"]) is not bool):
                raise ValidationError("Select a requirement kind and count precision.")
            if key == "media_actions" and (obj["action"] not in ("wipe", "destroy", "retain", "undecided") or obj["location"] not in ("onsite", "offsite", "unknown") or obj["collection"] not in ("after", "before", "none")):
                raise ValidationError("Select media action, location and collection sequence.")
    for identifier, decision in state["duplicate_decisions"].items():
        if not isinstance(identifier, str) or not isinstance(decision, dict) or set(decision) != {"text", "refs"}:
            raise ValidationError("Duplicate review requires a reason and references.")
        string(decision, "text")
        check_refs(decision)


def findings(rows, state):
    rows = effective_rows(rows, state)
    output = []
    def add(code, message, refs, blocking=True):
        unique = list(dict.fromkeys(refs))
        finding = dict(code=code, message=message, refs=unique[:32], blocking=blocking)
        if len(unique)>32:
            finding["additional_reference_count"] = len(unique)-32
        output.append(finding)
    active = [r for r in rows if not r.get("excluded")]
    ids = Counter(r["identifier"].strip().casefold() for r in active if r["identifier"].strip())
    for r in active:
        refs = r["refs"]
        if r["quantity"] is None:
            add("unknown_quantity", f"{r['item'] or r['id']}: quantity is unknown ({r['raw_quantity']!r}).", refs)
        if r["category"] == "unknown" or not r["item"]:
            add("unclear_category", f"Clarify the item category for {r['id']}.", refs)
        if r["unit"] not in {"item", "items", "unit", "units", "each", "pcs"}:
            add("unsupported_unit", f"{r['id']}: unit {r['unit']!r} needs an item-count correction.", refs)
        identifier = r["identifier"].strip().casefold()
        if ids[identifier] > 1 and identifier not in state["duplicate_decisions"]:
            add("duplicate_identifier", f"Identifier {r['identifier']!r} occurs more than once. Review; do not auto-merge.", refs)
        allocations = [a for a in state["allocations"] if a["row_id"] == r["id"]]
        actions = [a for a in state["media_actions"] if a["row_id"] == r["id"]]
        if r["category"] == "equipment":
            if any(a["quantity"] is None for a in allocations):
                add("unknown_allocation", f"{r['id']}: an equipment allocation has no count.", refs)
            total = sum(a["quantity"] or 0 for a in allocations)
            if r["quantity"] is not None and total != r["quantity"]:
                add("equipment_overlap" if total > r["quantity"] else "allocation_conservation", f"{r['id']}: equipment allocations total {total}; included quantity is {r['quantity']}. Reuse and destruction cannot claim the same whole item.", refs + [ref for a in allocations for ref in a["refs"]])
            if any(not a["site"] or a["outcome"] == "undecided" for a in allocations) or not allocations:
                add("equipment_scope", f"{r['id']}: confirm site and equipment outcome.", refs)
        elif allocations:
            add("equipment_media_mix", f"{r['id']}: equipment outcomes are only for equipment rows.", refs)
        if r["category"] == "media":
            total = sum(a["quantity"] or 0 for a in actions)
            if r["quantity"] is not None and total != r["quantity"]:
                add("media_conservation", f"{r['id']}: loose-media actions total {total}; included count is {r['quantity']}.", refs)
        for a in actions:
            if a["quantity"] is None or not a["site"] or a["action"] == "undecided" or a["location"] == "unknown":
                add("media_scope", f"{r['id']}: confirm media count, site, action and location.", a["refs"])
    active_ids = {r["id"] for r in active}
    for a in state["allocations"] + state["media_actions"]:
        if a["row_id"] not in active_ids:
            add("excluded_allocation", "An excluded row still has an allocation. Remove its allocation explicitly.", a["refs"])
    # Compare per-site and overall counts independently. Equipment totals never include media.
    byid = {r["id"]: r for r in active}
    for req in state["requirements"]:
        if req["kind"] == "onsite":
            for a in state["media_actions"]:
                if a["row_id"] not in byid:
                    continue
                if (not req["site"] or req["site"] == a["site"]) and (not req["item"] or req["item"] == byid[a["row_id"]]["item"]):
                    if a["location"] == "offsite" and a["action"] in {"wipe", "destroy"}:
                        add("onsite_conflict", f"{a['site']}: off-site {a['action']} conflicts with the recorded on-site restriction.", req["refs"] + a["refs"])
                    if a["collection"] == "before" and a["action"] in {"wipe", "destroy"}:
                        add("collection_sequence", f"{a['site']}: collection must follow the required on-site media work.", req["refs"] + a["refs"])
            continue
        selected = [r for r in active if (req["kind"] == "embedded" and r["category"] == "equipment" or r["category"] == req["kind"]) and (not req["item"] or r["item"] == req["item"])]
        selected_ids = {r["id"] for r in selected}
        entries = state["allocations"] if req["kind"] == "equipment" else state["media_actions"]
        entries = [a for a in entries if a["row_id"] in selected_ids and (not req["site"] or a["site"] == req["site"])]
        actual = sum(a["quantity"] or 0 for a in entries)
        if req["quantity"] is None:
            add("unknown_requirement", f"Confirm the required {req['kind']} count for {req['site'] or 'all sites'}.", req["refs"])
        elif actual != req["quantity"]:
            approx = req["precision"] == "approximate"
            add("approximate_difference" if approx else "count_mismatch", f"{req['item'] or req['kind']} at {req['site'] or 'all sites'}: requested {req['quantity']}, allocated {actual}." + (" Record acknowledgement and a count basis." if approx else " Exact counts must agree."), req["refs"] + [ref for a in entries for ref in a["refs"]], not (approx and req["acknowledged"] and bool(req["basis"].strip())))
    if not state["requirements"]:
        add("no_requirements", "Confirm the customer's counts and restrictions from the enquiry before review.", [])
    if not rows:
        add("no_inventory", "Import an inventory before review.", [])
    return output


def status(rows, state):
    return "Needs clarification" if any(f["blocking"] for f in findings(rows, state)) else "Ready for review"


def grouped_scope(rows, state):
    byid = {r["id"]: r for r in effective_rows(rows, state) if not r.get("excluded")}
    groups = defaultdict(lambda: {"quantity": 0, "source_refs": set()})
    for key in ("allocations", "media_actions"):
        for a in state[key]:
            r = byid.get(a["row_id"])
            if not r:
                continue
            kind = "equipment" if key == "allocations" else "loose_media" if r["category"] == "media" else "embedded_media"
            group = (kind, r["item"], a["site"], a.get("outcome", a.get("action")), a.get("location", ""), a.get("collection", ""))
            if a["quantity"] is None or groups[group]["quantity"] is None:
                groups[group]["quantity"] = None
            else:
                groups[group]["quantity"] += a["quantity"]
            groups[group]["source_refs"].update(a["refs"] + r["refs"])
    return [dict(kind=k[0], item=k[1], site=k[2], outcome=k[3], location=k[4], collection=k[5], quantity=v["quantity"], source_refs=sorted(v["source_refs"])) for k,v in sorted(groups.items())]


def clarification_draft(items):
    return "Please confirm the following scope details:\n\n" + "\n\n".join(f"{i}. {f['message']}\nSource: {', '.join(dict.fromkeys(f['refs'])) or 'Reviewer: inventory/intake required'}" + (f"\n{f['additional_reference_count']} additional references are retained in the case allocations." if f.get("additional_reference_count") else "") for i,f in enumerate(items,1)) + "\n\nWe will update the reviewed scope after your clarification."


def allocation_csv(rows, state):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["kind", "item", "site", "outcome", "quantity", "location", "collection", "source_refs"])
    for row in grouped_scope(rows, state):
        values = [("Unknown" if row[k] is None else row[k]) if k != "source_refs" else "; ".join(row[k]) for k in ("kind", "item", "site", "outcome", "quantity", "location", "collection", "source_refs")]
        writer.writerow(["'"+v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else v for v in values])
    return "\ufeff" + out.getvalue()
