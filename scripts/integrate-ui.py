"""Apply small, explicit integrations to the existing LoopDesk layout."""
from pathlib import Path
root=Path(__file__).resolve().parents[2]/"loopdesk"
base=root/"loopdesk/templates/base.html"
text=base.read_text(encoding="utf-8")
if "('scope.upload','Scope import'" not in text:
    text=text.replace("('reports','Reports',", "('scope.upload','Scope import','↗'),('reports','Reports',")
base.write_text(text,encoding="utf-8")
page=root/"loopdesk/templates/scope_import.html"
text=page.read_text(encoding="utf-8")
text=text.replace('id="scope-organisation"','id="opportunity-organisation"').replace('select name="contact_id" required','select name="contact_id" id="opportunity-contact" required').replace('<option value="{{ c.id }}">','<option value="{{ c.id }}" data-organisation="{{ c.organisation_id }}">')
for key,label in (("organisation_id","Organisation"),("contact_id","Contact"),("owner","Owner")):
    if f'<select aria-label="{label}"' not in text:
        text=text.replace(f'<select name="{key}"',f'<select aria-label="{label}" name="{key}"')
page.write_text(text,encoding="utf-8")
for folder in (root/"loopdesk/templates",Path(__file__).resolve().parents[1]/"scopedesk/templates"):
    for template in folder.glob("*.html"):
        if folder == root/"loopdesk/templates" and not template.name.startswith("scope_"):
            continue
        text=template.read_text(encoding="utf-8").replace('<div class="table-wrap">','<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable scope table">')
        if template.name == 'case.html':
            text=text.replace('<select name="delimiter"','<select aria-label="Delimiter" name="delimiter"')
            text=text.replace('<textarea name="state"','<textarea aria-label="Scope state" name="state"')
        if template.name == 'brief.html':
            text=text.replace('{{ row.quantity }}',"{{ row.quantity if row.quantity is not none else 'Unknown' }}")
        template.write_text(text,encoding="utf-8")
