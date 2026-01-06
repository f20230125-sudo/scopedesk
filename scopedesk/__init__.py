import hmac
import json
import os
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
import click
import psycopg
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException, SecurityError
from . import domain as d, services as s
from .db import get_db, migrate
from . import security
from .presentation import finding_groups, reference_summary


def create_app(config=None):
    root = Path(__file__).resolve().parents[1]
    production = os.environ.get("APP_ENV") == "production" or bool(os.environ.get("VERCEL"))
    app = Flask(__name__,static_folder=str(root/"public/assets"),static_url_path="/assets")
    app.config.update(DATABASE_URL=os.environ.get("SCOPEDESK_DATABASE_URL",f"sqlite:///{root/'instance/scope.sqlite3'}"),SECRET_KEY=os.environ.get("SCOPEDESK_SECRET_KEY"),PRODUCTION=production,SESSION_COOKIE_NAME="scopedesk_session",SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",SESSION_COOKIE_SECURE=production,PERMANENT_SESSION_LIFETIME=timedelta(hours=24),MAX_CONTENT_LENGTH=600*1024,MAX_FORM_MEMORY_SIZE=500*1024)
    if config:
        app.config.update(config)
    app.config["LOOPDESK_URL"]=os.environ.get("SCOPEDESK_LOOPDESK_URL","" if app.config["PRODUCTION"] else "http://127.0.0.1:5055") if not (config and "LOOPDESK_URL" in config) else config["LOOPDESK_URL"]
    if app.config["LOOPDESK_URL"]:
        try:
            linked=urlsplit(app.config["LOOPDESK_URL"])
            local=linked.hostname in {"127.0.0.1","localhost","::1"}
            if not linked.hostname or linked.port==0 or any(ord(c)<=32 for c in app.config["LOOPDESK_URL"]) or linked.username or linked.password or linked.path or linked.query or linked.fragment or linked.scheme not in {"http","https"} or (linked.scheme=="http" and (app.config["PRODUCTION"] or not local)):
                raise ValueError()
        except (TypeError,ValueError):
            raise RuntimeError("Configure an HTTPS LoopDesk origin, or loopback HTTP for local use.") from None
    app.config["TEMPLATES_AUTO_RELOAD"] = not app.config["PRODUCTION"]
    if app.config["PRODUCTION"]:
        if not app.config["DATABASE_URL"].startswith(("postgres://","postgresql://")) or len(app.config["SECRET_KEY"] or "") < 32:
            raise RuntimeError("Production requires PostgreSQL and a random session secret of at least 32 characters.")
    elif not app.config["SECRET_KEY"]:
        (root/"instance").mkdir(exist_ok=True)
        secret = root/"instance/session-secret"
        try:
            with secret.open("x",encoding="utf-8") as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret.read_text()
    security.configure(app,"SCOPEDESK")

    @app.teardown_appcontext
    def close_db(error):
        if "db" in g:
            g.pop("db").close()

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    @app.context_processor
    def context():
        return dict(csrf_token=csrf_token,workspace=getattr(g,"wid",None),loopdesk_url=app.config["LOOPDESK_URL"],reference_summary=reference_summary)

    @app.before_request
    def protect():
        g.wid = None
        if isinstance(request.routing_exception,SecurityError):
            return Response("Untrusted request host.\n",status=400,content_type="text/plain")
        if request.method == "POST":
            security.check_origin()
            if not session.get("csrf") or not hmac.compare_digest(request.form.get("csrf_token","").encode(),session["csrf"].encode()):
                abort(400,"Invalid security token. Reload the form.")
        if request.endpoint is None and session.get("workspace_id") and security.active_workspace(get_db(),session["workspace_id"],s.stamp()):
            g.wid = session["workspace_id"]
        if request.endpoint is not None and request.endpoint not in {"landing","demo","static","health"}:
            wid = session.get("workspace_id")
            if not security.active_workspace(get_db(),wid,s.stamp()):
                session.pop("workspace_id",None)
                flash("Start a fresh demo. Workspaces expire after 24 hours.")
                return redirect(url_for("landing"),303)
            g.wid = wid
        if request.method == "POST" or getattr(g,"wid",None):
            security.enforce_rate_limits(get_db(),getattr(g,"wid",None),demo=request.endpoint=="demo")

    @app.after_request
    def headers(response):
        response.headers.update({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"same-origin","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        if app.config["PRODUCTION"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.cli.command("migrate")
    def migrate_command():
        if app.config["DATABASE_URL"].startswith("sqlite:///"):
            Path(app.config["DATABASE_URL"].removeprefix("sqlite:///")).parent.mkdir(parents=True,exist_ok=True)
        migrate(get_db())
        click.echo("ScopeDesk migrations applied.")

    @app.get("/health")
    def health():
        row = get_db().one("SELECT version FROM schema_migrations WHERE version='003_session_revocation'")
        return {"status":"ok" if row else "migration_required"},200 if row else 503

    @app.get("/")
    def landing():
        return render_template("landing.html")

    @app.post("/demo")
    def demo():
        wid = session.get("workspace_id")
        existing = security.active_workspace(get_db(),wid,s.stamp())
        if not existing or request.form.get("reset") == "1":
            previous = wid if existing else None
            wid = s.workspace(get_db())
            from .demo import create_demo
            create_demo(get_db(),wid)
            create_demo(get_db(),wid,valid=True)
            if previous:
                security.revoke_workspace(get_db(),previous,s.stamp())
            session.clear()
            session["workspace_id"] = wid
            session.permanent = True
        return redirect(url_for("cases"),303)

    @app.get("/cases")
    def cases():
        from .demo import EXAMPLES
        items = get_db().all("SELECT * FROM cases WHERE workspace_id=? ORDER BY created_at,id",(g.wid,))
        for c in items:
            c["state"] = json.loads(c["state"])
            revs = s.revision_list(get_db(),g.wid,c["id"])
            c["status"] = revs[0]["status"] if revs and not revs[0]["superseded"] else d.status(s.rows(get_db(),g.wid,c["id"]),c["state"])
            c["blockers"] = sum(f["blocking"] for f in d.findings(s.rows(get_db(),g.wid,c["id"]),c["state"]))
        examples = [dict(value,key=key,loaded=next((c for c in items if c["client"] == value["client"] and c["title"] == value["title"]),None)) for key,value in EXAMPLES.items()]
        return render_template("cases.html",cases=items,examples=examples,case_limit=20)

    @app.post("/cases/examples")
    def load_example():
        from .demo import EXAMPLES,create_example
        key = request.form.get("example","")
        if key not in EXAMPLES:
            raise d.ValidationError("Choose one of the three available fictional examples.")
        example = EXAMPLES[key]
        existing = get_db().one("SELECT id FROM cases WHERE workspace_id=? AND client=? AND title=? ORDER BY created_at,id",(g.wid,example["client"],example["title"]))
        if existing:
            return redirect(url_for("case_detail",cid=existing["id"]),303)
        cid = create_example(get_db(),g.wid,key)
        return redirect(url_for("case_detail",cid=cid),303)

    @app.route("/cases/new",methods=["GET","POST"])
    def new_case():
        if request.method == "POST":
            cid = s.create_case(get_db(),g.wid,request.form.get("client",""),request.form.get("title",""),request.form.get("enquiry",""))
            return redirect(url_for("case_detail",cid=cid),303)
        return render_template("new.html")

    @app.get("/cases/<cid>")
    def case_detail(cid):
        c = s.case(get_db(),g.wid,cid)
        inventory = s.rows(get_db(),g.wid,cid)
        origin = s.sources(get_db(),g.wid,cid)
        found = d.findings(inventory,c["state"])
        revs = s.revision_list(get_db(),g.wid,cid)
        current_status = revs[0]["status"] if revs and not revs[0]["superseded"] else d.status(inventory,c["state"])
        assumptions,_ = s.review_assumptions(c["state"],origin)
        return render_template("case.html",case=c,rows=d.effective_rows(inventory,c["state"]),proposed=d.grouped_scope(inventory,c["state"]),sources=origin,references=d.ref_index(origin),findings=found,finding_groups=finding_groups(found),assumption_count=len(assumptions),status=current_status,blockers=sum(f["blocking"] for f in found),revisions=revs,draft=d.clarification_draft(found),state_json=json.dumps(c["state"],indent=2,ensure_ascii=False),audit=get_db().all("SELECT * FROM audit_events WHERE workspace_id=? AND case_id=? ORDER BY created_at DESC,id DESC",(g.wid,cid)))

    @app.post("/cases/<cid>/preview")
    def import_preview(cid):
        file = request.files.get("inventory")
        if not file:
            raise d.ValidationError("Choose a UTF-8 CSV inventory.")
        pid = s.preview(get_db(),g.wid,cid,file.read(256*1024+1),request.form.get("delimiter"),request.form.get("mode"),file.filename or "inventory.csv")
        return redirect(url_for("mapping",cid=cid,pid=pid),303)

    @app.route("/cases/<cid>/imports/<pid>",methods=["GET","POST"])
    def mapping(cid,pid):
        c = s.case(get_db(),g.wid,cid)
        p = s.get_preview(get_db(),g.wid,cid,pid)
        fields = ("item","quantity","identifier","site","category","unit")
        mapping = {f:request.form.get(f,"") for f in fields}
        mapping["default_category"] = request.form.get("default_category","unknown")
        interpreted = None
        if request.method == "POST":
            if request.form.get("action") == "commit":
                s.commit_import(get_db(),g.wid,cid,pid,mapping,request.form.get("version"))
                flash("Inventory imported. Original rows and identifiers are preserved.")
                return redirect(url_for("case_detail",cid=cid),303)
            interpreted = s.map_preview(get_db(),g.wid,cid,pid,mapping,request.form.get("version"))
        else:
            mapping = {f:next((h for h in p["parsed"]["headers"] if h.lower() == f),"") for f in fields}
            mapping["default_category"] = "unknown"
        return render_template("mapping.html",case=c,preview=p,mapping=mapping,fields=fields,interpreted=interpreted)

    @app.post("/cases/<cid>/statement")
    def statement(cid):
        sid = s.add_statement(get_db(),g.wid,cid,request.form.get("version"),request.form.get("kind"),request.form.get("text",""))
        flash(f"Recorded immutable source {sid}. Use its references in the structured correction.")
        return redirect(url_for("case_detail",cid=cid)+"#scope-editor",303)

    @app.post("/cases/<cid>/scope")
    def save_scope(cid):
        try:
            state = json.loads(request.form.get("state",""))
        except (json.JSONDecodeError,RecursionError,ValueError):
            raise d.ValidationError("Scope state is not valid JSON.") from None
        s.save_state(get_db(),g.wid,cid,request.form.get("version"),state,request.form.get("reason",""))
        flash("Scope saved. Findings recalculated; prior reviewed revisions are superseded.")
        return redirect(url_for("case_detail",cid=cid),303)

    @app.post("/cases/<cid>/review")
    def review(cid):
        revision = s.review(get_db(),g.wid,cid,request.form.get("version"))
        return redirect(url_for("brief",cid=cid,revision=revision),303)

    @app.get("/cases/<cid>/brief")
    def brief(cid):
        revision = security.positive_integer(request.args["revision"],1000000) if "revision" in request.args else None
        if "revision" in request.args and revision is None:
            raise d.ValidationError("Revision must be a positive integer of at most 1,000,000.")
        c = s.case(get_db(),g.wid,cid)
        if revision:
            r = s.get_revision(get_db(),g.wid,cid,revision)
            snapshot = r["snapshot"]
            label = ("Superseded · " if r["superseded"] else "") + f"{r['status']} · Revision {revision}"
        else:
            inventory = s.rows(get_db(),g.wid,cid)
            snapshot = dict(case=c,rows=inventory,sources=s.sources(get_db(),g.wid,cid),findings=d.findings(inventory,c["state"]),scope=d.grouped_scope(inventory,c["state"]),assumptions=c["state"]["assumptions"])
            label = "DRAFT — not reviewed"
        html = render_template("brief.html",snapshot=snapshot,label=label,revision=revision,references=d.ref_index(snapshot["sources"]),standalone=bool(request.args.get("download")),standalone_css=(root/"public/assets/app.css").read_text(encoding="utf-8"))
        return Response(html,content_type="text/html; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="scopedesk-brief-{revision or "draft"}.html"'} if request.args.get("download") else {})

    @app.get("/cases/<cid>/allocations.csv")
    def export_csv(cid):
        c = s.case(get_db(),g.wid,cid)
        revision = security.positive_integer(request.args["revision"],1000000) if "revision" in request.args else None
        if "revision" in request.args and revision is None:
            raise d.ValidationError("Revision must be a positive integer of at most 1,000,000.")
        inventory = s.rows(get_db(),g.wid,cid)
        label = "DRAFT"
        if revision:
            r = s.get_revision(get_db(),g.wid,cid,revision)
            inventory,c = r["snapshot"]["rows"],r["snapshot"]["case"]
            label = f"{'Superseded-' if r['superseded'] else 'Reviewed-'}r{revision}"
        return Response(d.allocation_csv(inventory,c["state"]),content_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="scopedesk-{label}-allocations.csv"'})

    @app.get("/cases/<cid>/handoff/<int:revision>.json")
    def handoff(cid,revision):
        return Response(s.export_handoff(get_db(),g.wid,cid,revision),content_type="application/json",headers={"Content-Disposition":f'attachment; filename="scopedesk-{cid}-r{revision}.json"'})

    @app.errorhandler(d.ValidationError)
    def invalid(error):
        code = 409 if isinstance(error,d.Conflict) else 422
        return render_template("error.html",message=str(error),code=code),code

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        message = "ScopeDesk encountered an unexpected error. Return to cases and try again." if error.code == 500 else error.description
        response.set_data(render_template("error.html",message=message,code=error.code))
        response.content_type = "text/html; charset=utf-8"
        return response

    def db_error(error):
        app.logger.warning("Scope database unavailable (%s)",type(error).__name__)
        return render_template("error.html",message="The demo database is temporarily unavailable.",code=503),503
    for error in (sqlite3.OperationalError,psycopg.OperationalError,psycopg.errors.UndefinedTable):
        app.register_error_handler(error,db_error)
    return app
