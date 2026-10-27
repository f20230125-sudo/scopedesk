"""Display labels only; finding codes and evidence remain unchanged."""

FINDING_TITLES = {
    "unknown_quantity":"Item count is unknown",
    "unclear_category":"Item category needs confirmation",
    "unsupported_unit":"Unit needs an item-count correction",
    "duplicate_identifier":"Identifiers occur more than once",
    "unknown_allocation":"Allocation count is unknown",
    "equipment_overlap":"Reuse and destruction overlap",
    "allocation_conservation":"Allocations do not match the item count",
    "equipment_scope":"Equipment site or outcome needs confirmation",
    "equipment_media_mix":"Equipment and media allocations are mixed",
    "media_conservation":"Media actions do not match the item count",
    "media_scope":"Media action details need confirmation",
    "excluded_allocation":"Excluded rows still have allocations",
    "onsite_conflict":"On-site restriction conflict",
    "collection_sequence":"Collection must follow on-site work",
    "unknown_requirement":"Required count needs confirmation",
    "approximate_difference":"Approximate counts differ",
    "count_mismatch":"Counts do not agree",
    "no_requirements":"Customer requirements need confirmation",
    "no_inventory":"Inventory is missing",
}


def finding_groups(findings):
    groups = {}
    for finding in findings:
        code = finding["code"]
        if code not in groups:
            groups[code] = dict(code=code,title=FINDING_TITLES.get(code,code.replace("_"," ").capitalize()),items=[])
        groups[code]["items"].append(finding)
    return list(groups.values())


def reference_summary(refs):
    groups = {}
    for ref in refs:
        source,position,*cell = ref.split(":",2)
        key = (source,position)
        if key not in groups:
            groups[key] = dict(ref=ref,label=f"{source} {'row' if cell else 'line'} {position[1:]}")
    return list(groups.values())
