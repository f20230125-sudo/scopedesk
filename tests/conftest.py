import os
import uuid
import pytest
from scopedesk import create_app
from scopedesk.db import Database,get_db,migrate
from scopedesk import services as s

@pytest.fixture
def app(tmp_path):
    url=os.environ.get("SCOPEDESK_TEST_DATABASE_URL")
    admin=None
    schema=None
    if url:
        from psycopg import sql
        schema="scopedesk_test_"+uuid.uuid4().hex
        admin=Database(url)
        with admin.transaction():admin.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    app=create_app(dict(TESTING=True,PRODUCTION=False,SECRET_KEY="fixture-session-secret",DATABASE_URL=url or "sqlite:///"+str(tmp_path/"scope.sqlite"),DATABASE_SCHEMA=schema))
    with app.app_context():migrate(get_db())
    try:yield app
    finally:
        if admin:
            from psycopg import sql
            with admin.transaction():admin.conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            admin.close()

@pytest.fixture
def db(app):
    with app.app_context():yield get_db()

@pytest.fixture
def wid(db):return s.workspace(db)

@pytest.fixture
def client(app,wid):
    client=app.test_client()
    with client.session_transaction() as sess:sess.update(workspace_id=wid,csrf="fixture")
    return client
