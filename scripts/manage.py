"""Project-local commands; all generated state stays on the project drive."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]


def environment(root=ROOT):
    env=os.environ.copy()
    for key,tail in {"TEMP":"temp","TMP":"temp","TMPDIR":"temp","PIP_CACHE_DIR":"pip-cache","npm_config_cache":"npm-cache","XDG_CACHE_HOME":"cache","PYTHONPYCACHEPREFIX":"pycache"}.items():
        folder=root/".local"/tail
        folder.mkdir(parents=True,exist_ok=True)
        env[key]=str(folder)
    env["PIP_DISABLE_PIP_VERSION_CHECK"]="1"
    return env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["run","migrate","test","test-postgres","browser","record","package"])
    args=parser.parse_args()
    env=environment()
    python=ROOT/".venv"/("Scripts/python.exe" if os.name=="nt" else "bin/python")
    if not python.is_file():parser.error("Create .venv and install requirements-dev.txt first.")
    def run(command):return subprocess.run(command,cwd=ROOT,env=env).returncode
    if args.command in {"run","migrate"}:
        result=run([str(python),"-m","flask","--app","app","migrate"])
        return result or (run([str(python),"app.py"]) if args.command=="run" else 0)
    if args.command in {"test","test-postgres"}:
        if args.command=="test-postgres" and not env.get("SCOPEDESK_TEST_DATABASE_URL"):
            parser.error("Set SCOPEDESK_TEST_DATABASE_URL to a dedicated PostgreSQL test database.")
        if args.command=="test":env.pop("SCOPEDESK_TEST_DATABASE_URL",None)
        backend="postgres" if args.command=="test-postgres" else "sqlite"
        return run([str(python),"-m","pytest","-q",f"--basetemp={ROOT/'.local'/('pytest-'+uuid.uuid4().hex)}",f"--junitxml=artifacts/pytest-{backend}.xml"])
    if args.command in {"browser","record"}:return run(["node","scripts/"+("browser-check.mjs" if args.command=="browser" else "record-demo.mjs")])
    return run([str(python),"scripts/package-release.py"])


if __name__=="__main__":raise SystemExit(main())
