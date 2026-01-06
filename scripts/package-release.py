"""Allowlisted public source and a verified offline two-application Windows package."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from email.parser import Parser
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from manage import environment

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parent


def source_files(project):
    singles={"app.py","requirements.txt","requirements-dev.txt","pyproject.toml","README.md","LICENSE","package.json","vercel.json",".gitignore",".vercelignore",".env.example","Start-ScopeDesk.cmd","Start-LoopDesk.cmd"}
    folders={project.name,"public","migrations","tests","scripts","docs","examples",".github"}
    for path in sorted(project.rglob("*")):
        rel=path.relative_to(project)
        if not path.is_file() or any(p in {"__pycache__",".venv",".local",".git","private","instance","node_modules","recording-raw"} for p in rel.parts):continue
        if rel.parts[0] in folders and path.suffix in {".py",".html",".css",".js",".mjs",".sql",".json",".md",".txt",".csv",".svg",".yml",".ps1"}:
            yield path
        elif len(rel.parts)==1 and rel.name in singles:yield path
        elif rel.parts[0]=="artifacts" and len(rel.parts)==2 and path.suffix in {".json",".xml",".png",".webm",".html",".csv",".txt"} and not path.name.startswith("initial-") and path.name not in {"offline-verification.json","source-manifest.json"}:
            yield path


def wheels():
    expected={}
    for name in ("requirements.txt","requirements-dev.txt"):
        for line in (ROOT/name).read_text().splitlines():
            if "==" in line and not line.startswith("#"):
                package,version=line.split(";",1)[0].strip().split("==")
                expected[package.lower().replace("-","_")]=version
    result={}
    for path in (WORK/"loopdesk/.local/wheels").glob("*.whl"):
        with ZipFile(path) as z:
            meta=Parser().parsestr(z.read(next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))).decode())
            name=meta["Name"].lower().replace("-","_")
            if expected.get(name)==meta["Version"]:result[name]=path
    assert not set(expected)-set(result),"Missing pinned wheels"
    return sorted(result.values())


def build():
    projects=[ROOT,WORK/"loopdesk"]
    source=WORK/"ScopeDesk-Source.zip"
    manifest=[]
    with ZipFile(source,"w",ZIP_DEFLATED) as z:
        for project in projects:
            for path in source_files(project):
                name=str(Path(project.name)/path.relative_to(project)).replace("\\","/")
                z.write(path,name)
                manifest.append(dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
        security_review=WORK/"security-review"
        for filename in ("README.md","probe.py","fuzz.py","serve.py","browser-security.mjs","baseline.json","replay-baseline.json","retest.json","fuzz-results.json","browser-security.json","scopedesk-hostile-brief.png","loopdesk-hostile-history.png"):
            path=security_review/filename
            if path.is_file():
                name="security-review/"+filename
                z.write(path,name)
                manifest.append(dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
        z.writestr("SOURCE-MANIFEST.json",json.dumps(manifest,indent=2))
    offline=WORK/"ScopeDesk-Windows-Offline.zip"
    wheel_files=wheels()
    with ZipFile(source) as src,ZipFile(offline,"w",ZIP_DEFLATED) as dest:
        for name in src.namelist():dest.writestr(name,src.read(name))
        for project in projects:
            for wheel in wheel_files:dest.write(wheel,f"{project.name}/.local/wheels/{wheel.name}")
        dest.writestr("START-HERE.txt","ScopeDesk + LoopDesk offline Windows demonstration\n\nRequires existing Windows x64 Python 3.14. Extract both folders to D:.\nOpen scopedesk/Start-ScopeDesk.cmd (5058) and loopdesk/Start-LoopDesk.cmd (5055).\nStart each demo, review the two-site scope and import its reviewed JSON into LoopDesk.\nAll data is fictional. No hosting or application submission is performed.\nSource, pinned runtime/test wheels, tests, screenshots and the ScopeDesk recording are included.\n")
    assert ZipFile(offline).testzip() is None
    return source,offline,len(wheel_files)


def token(html):return re.search(r'name="csrf_token" value="([^"]+)"',html)[1]


def post(opener,url,fields):
    return opener.open(urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode()),timeout=15)


def verify(archive):
    folder=ROOT/".local"/("offline-review-"+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    with ZipFile(archive) as z:
        for name in z.namelist():assert (folder/name).resolve().is_relative_to(folder.resolve())
        z.extractall(folder)
    logs=[]
    for name in ("scopedesk","loopdesk"):
        project=folder/name
        env=environment(project)
        for key in ("SCOPEDESK_DATABASE_URL","SCOPEDESK_SECRET_KEY","DATABASE_URL","SECRET_KEY","APP_ENV","VERCEL","SCOPEDESK_TRUSTED_HOSTS","LOOPDESK_TRUSTED_HOSTS"):env.pop(key,None)
        python=project/".venv/Scripts/python.exe"
        commands=[[sys.executable,"-m","venv",str(project/".venv")],[str(python),"-m","pip","install","--no-index","--find-links",str(project/".local/wheels"),"-r","requirements.txt"],[str(python),"-m","flask","--app","app","migrate"]]
        for command in commands:
            result=subprocess.run(command,cwd=project,env=env,capture_output=True,text=True)
            logs.append(result.stdout+result.stderr)
            assert result.returncode==0,logs[-1][-1500:]
    running=[]
    try:
        ports={}
        for name in ("scopedesk","loopdesk"):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1",0))
                port=listener.getsockname()[1]
            ports[name]=port
            project=folder/name
            env=environment(project)
            for key in ("SCOPEDESK_DATABASE_URL","SCOPEDESK_SECRET_KEY","DATABASE_URL","SECRET_KEY","APP_ENV","VERCEL","SCOPEDESK_TRUSTED_HOSTS","LOOPDESK_TRUSTED_HOSTS"):env.pop(key,None)
            logfile=(project/".local/server.log").open("w",encoding="utf-8")
            nonce=uuid.uuid4().hex
            # Tag only the health response of this child. Business routes run unchanged.
            bootstrap="from app import app\noriginal_health=app.view_functions['health']\ndef offline_health():\n response=app.make_response(original_health())\n response.headers['X-Offline-Probe']="+repr(nonce)+"\n return response\napp.view_functions['health']=offline_health\napp.run(host='127.0.0.1',port="+str(port)+",debug=False)\n"
            process=subprocess.Popen([str(project/".venv/Scripts/python.exe"),"-c",bootstrap],cwd=project,env=env,stdout=logfile,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            running.append((process,logfile))
            for attempt in range(60):
                if process.poll() is not None:
                    raise AssertionError("Extracted application exited before readiness")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=1) as response:
                        assert response.status==200 and response.headers.get("X-Offline-Probe")==nonce,"Health response did not come from the extracted application"
                    break
                except OSError:time.sleep(.1)
            else:raise AssertionError("Extracted app did not become healthy")
        jar=http.cookiejar.CookieJar()
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        scope,loop=f"http://127.0.0.1:{ports['scopedesk']}",f"http://127.0.0.1:{ports['loopdesk']}"
        landing=opener.open(scope).read().decode()
        cases=post(opener,scope+"/demo",dict(csrf_token=token(landing))).read().decode()
        cards=re.findall(r'<a class="case-card" href="([^"]+)"',cases)
        assert len(cards)==2
        valid=next(url for url in cards if "Reuse equipment, destroy embedded media" in opener.open(scope+url).read().decode())
        case_html=opener.open(scope+valid).read().decode()
        reviewed=post(opener,scope+valid+"/review",dict(csrf_token=token(case_html),version=re.search(r'name="version" value="(\d+)"',case_html)[1])).read().decode()
        assert "Reviewed · Revision 1" in reviewed
        raw=opener.open(scope+valid+"/handoff/1.json").read()
        assert json.loads(raw)["source_system"]=="ScopeDesk"
        landing=opener.open(loop).read().decode()
        post(opener,loop+"/demo",dict(csrf_token=token(landing))).read()
        upload=opener.open(loop+"/scope-import").read().decode()
        boundary="ScopeDeskOfflineBoundary"+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="csrf_token"\r\n\r\n{token(upload)}\r\n--{boundary}\r\nContent-Disposition: form-data; name="handoff"; filename="scope.json"\r\nContent-Type: application/json\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
        response=opener.open(urllib.request.Request(loop+"/scope-import",data=body,headers={"Content-Type":"multipart/form-data; boundary="+boundary}))
        preview_url=response.url
        preview=response.read().decode()
        org=re.search(r'<option value="([^"]+)">Cedar Circuit</option>',preview)[1]
        contact=re.search(r'<option value="([^"]+)" data-organisation="'+org+r'">',preview)[1]
        fields=dict(csrf_token=token(preview),organisation_id=org,contact_id=contact,owner="Maya (demo)")
        response=post(opener,preview_url,fields)
        opportunity=response.url
        detail=response.read().decode()
        assert "Not estimated" in detail and "ScopeDesk revision 1 received" in detail
        assert post(opener,preview_url,fields).url==opportunity
        assert {c.name for c in jar}=={"session","scopedesk_session"}
        return dict(verified=True,python=sys.version.split()[0],platform=sys.platform,twoCleanVirtualEnvironments=True,installedWithoutNetwork=True,healthEndpoints=2,childInstanceIdentityVerified=True,reviewedJsonExport=True,realHttpLoopDeskImport=True,repeatedImportSameOpportunity=True,separateCookies=True,allGeneratedFilesUnder=str(folder))
    finally:
        for process,logfile in running:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            logfile.close()
        (ROOT/".local/offline-install.log").write_text("\n".join(logs),encoding="utf-8")


if __name__=="__main__":
    source,offline,count=build()
    result=verify(offline)
    result["wheelCountPerApp"]=count
    for archive in (source,offline):
        with ZipFile(archive,"a",ZIP_DEFLATED) as z:z.writestr("OFFLINE-VERIFICATION.json",json.dumps(result,indent=2))
        assert ZipFile(archive).testzip() is None
    result.update(archive=str(offline),bytes=offline.stat().st_size,sha256=hashlib.sha256(offline.read_bytes()).hexdigest())
    (ROOT/"artifacts/offline-verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (WORK/"ScopeDesk-Release.json").write_text(json.dumps(dict(source=str(source),offline=result),indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
