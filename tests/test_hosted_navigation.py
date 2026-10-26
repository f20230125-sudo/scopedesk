"""Deployment navigation must use a configured origin, never a visitor's localhost."""
import secrets
import pytest
from scopedesk import create_app


@pytest.mark.parametrize("origin",["http://evil.example","https://crm.example/path","https://user:password@crm.example","https://crm.example?x=1","javascript:alert(1)","https://crm.example:70000"])
def test_reject_unsafe_crm_origin(origin,tmp_path):
    with pytest.raises(RuntimeError,match="LoopDesk origin"):
        create_app(dict(TESTING=True,PRODUCTION=False,SECRET_KEY="test",DATABASE_URL="sqlite:///"+str(tmp_path/"unused.sqlite3"),LOOPDESK_URL=origin))


def test_production_navigation_has_no_loopback_default(monkeypatch):
    monkeypatch.delenv("SCOPEDESK_LOOPDESK_URL",raising=False)
    app=create_app(dict(TESTING=True,PRODUCTION=True,DATABASE_URL="postgresql://unused.invalid/not_connected",SECRET_KEY=secrets.token_hex(32),TRUSTED_HOSTS=["scope.example"]))
    page=app.test_client().get("/",base_url="https://scope.example")
    assert page.status_code==200
    assert b"127.0.0.1" not in page.data and b"localhost" not in page.data


def test_explicit_crm_origin_is_rendered(app,monkeypatch):
    monkeypatch.setitem(app.config,"LOOPDESK_URL","https://crm.example")
    page=app.test_client().get("/")
    assert b'href="https://crm.example/scope-import"' in page.data
    assert b"127.0.0.1" not in page.data
