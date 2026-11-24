"""Automated tests. The language model and the database are replaced with fakes,
so the tests run on GitHub's runner without Ollama or MariaDB."""

import pymysql
import pytest
import requests

from chat import COOKIE_NAME, MAX_MESSAGE_CHARS, create_app
from chat.llm import LLMError, OllamaClient
from chat.store import MariaDBStore, StoreError

SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeStore:
    def __init__(self):
        self.data = {}
        self.fail = False

    def get_messages(self, session_id, limit=200):
        if self.fail:
            raise StoreError("db down")
        return list(self.data.get(session_id, []))[-limit:]

    def add_messages(self, session_id, messages):
        if self.fail:
            raise StoreError("db down")
        self.data.setdefault(session_id, []).extend(messages)


class FakeLLM:
    model = "fake-model:1b"

    def __init__(self):
        self.calls = []
        self.fail = False

    def chat(self, messages):
        if self.fail:
            raise LLMError("model down")
        self.calls.append(messages)
        return f"echo: {messages[-1]['content']}"


@pytest.fixture
def parts(tmp_path):
    store, llm = FakeStore(), FakeLLM()
    app = create_app(store=store, llm=llm, revision=SHA, app_root=tmp_path)
    app.config["TESTING"] = True
    return app, store, llm


@pytest.fixture
def client(parts):
    return parts[0].test_client()


def session_cookie(client):
    cookie = client.get_cookie(COOKIE_NAME, path="/")
    return cookie.value if cookie else None


def test_health_returns_commit_sha(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "commit": SHA, "model": "fake-model:1b"}


def test_revision_is_read_from_file(tmp_path):
    (tmp_path / "REVISION").write_text(SHA + "\n", encoding="utf-8")
    app = create_app(store=FakeStore(), llm=FakeLLM(), app_root=tmp_path)
    assert app.test_client().get("/health").get_json()["commit"] == SHA


def test_new_visitor_gets_empty_conversation_and_cookie(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"New conversation" in response.data
    assert session_cookie(client) is not None


def test_chat_reply_is_returned_and_saved(parts):
    app, store, llm = parts
    client = app.test_client()
    client.get("/")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.get_json() == {"reply": "echo: hello"}
    saved = store.data[session_cookie(client)]
    assert saved == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "echo: hello"}]


def test_conversation_is_visible_after_reload(client):
    client.get("/")
    client.post("/api/chat", json={"message": "remember me"})
    page = client.get("/").data
    assert b"remember me" in page
    assert b"echo: remember me" in page


def test_history_is_sent_to_the_model(parts):
    app, _, llm = parts
    client = app.test_client()
    client.get("/")
    client.post("/api/chat", json={"message": "first"})
    client.post("/api/chat", json={"message": "second"})
    assert [m["content"] for m in llm.calls[-1]] == ["first", "echo: first", "second"]


def test_separate_browser_sessions_have_separate_conversations(parts):
    app = parts[0]
    alice, bob = app.test_client(), app.test_client()
    alice.get("/")
    alice.post("/api/chat", json={"message": "secret of alice"})
    page = bob.get("/").data
    assert b"secret of alice" not in page
    assert b"New conversation" in page


def test_new_chat_button_starts_empty_conversation(client):
    client.get("/")
    client.post("/api/chat", json={"message": "old message"})
    old = session_cookie(client)
    response = client.post("/new")
    assert response.status_code == 302
    assert session_cookie(client) != old
    assert b"old message" not in client.get("/").data


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}])
def test_empty_message_is_rejected(client, payload):
    assert client.post("/api/chat", json=payload).status_code == 400


def test_too_long_message_is_rejected(client):
    response = client.post("/api/chat", json={"message": "x" * (MAX_MESSAGE_CHARS + 1)})
    assert response.status_code == 400


def test_model_error_returns_502_and_saves_nothing(parts):
    app, store, llm = parts
    llm.fail = True
    client = app.test_client()
    client.get("/")
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 502
    assert store.data == {}


def test_database_error_returns_500(parts):
    app, store, _ = parts
    client = app.test_client()
    client.get("/")
    store.fail = True
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 500


def test_links_work_under_the_viikko5_sub_path(client):
    headers = {"X-Forwarded-Prefix": "/viikko5"}
    page = client.get("/", headers=headers).data
    assert b'href="/viikko5/static/style.css"' in page
    assert b'src="/viikko5/static/app.js"' in page
    assert b'data-api="/viikko5/api/chat"' in page
    assert client.get("/static/style.css").status_code == 200


def test_cookie_path_is_the_sub_path(client):
    response = client.get("/", headers={"X-Forwarded-Prefix": "/viikko5"})
    assert "Path=/viikko5/" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]


def test_docs_page_renders(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert b"Request path" in response.data


# --- Ollama client (requests.post is mocked) ---------------------------------

class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"HTTP {self.status}")

    def json(self):
        return self.data


def test_ollama_client_sends_model_and_history(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent.update(url=url, json=json)
        return FakeResponse({"message": {"role": "assistant", "content": " Hi! "}})

    monkeypatch.setattr(requests, "post", fake_post)
    client = OllamaClient("http://127.0.0.1:11434/", "gemma3:1b")
    assert client.chat([{"role": "user", "content": "hello"}]) == "Hi!"
    assert sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert sent["json"]["model"] == "gemma3:1b"
    assert sent["json"]["stream"] is False
    assert sent["json"]["messages"][0]["role"] == "system"
    assert sent["json"]["messages"][-1] == {"role": "user", "content": "hello"}


@pytest.mark.parametrize(
    "behaviour",
    [requests.ConnectionError("refused"), FakeResponse({}, 500), FakeResponse({"oops": 1})],
)
def test_ollama_client_errors_become_llm_error(monkeypatch, behaviour):
    def fake_post(url, json, timeout):
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(LLMError):
        OllamaClient("http://127.0.0.1:11434", "m").chat([{"role": "user", "content": "x"}])


# --- MariaDB store (pymysql.connect is mocked) -------------------------------

def test_store_wraps_database_errors(monkeypatch):
    def fail(**kwargs):
        raise pymysql.err.OperationalError(2003, "Can't connect")

    monkeypatch.setattr(pymysql, "connect", fail)
    store = MariaDBStore("localhost", "u", "p", "viikko5chat")
    with pytest.raises(StoreError):
        store.get_messages("abc")
    with pytest.raises(StoreError):
        store.add_messages("abc", [{"role": "user", "content": "x"}])


def test_store_uses_parameterised_queries(monkeypatch):
    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            executed.append((sql, params))

        def executemany(self, sql, rows):
            executed.append((sql, rows))

        def fetchall(self):
            return [{"role": "user", "content": "hi"}]

    class Conn:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(pymysql, "connect", lambda **kwargs: Conn())
    store = MariaDBStore("localhost", "u", "p", "viikko5chat")
    assert store.get_messages("sid'; DROP TABLE messages;--") == [{"role": "user", "content": "hi"}]
    store.add_messages("sid", [{"role": "user", "content": "x"}])
    assert executed[0][1] == ("sid'; DROP TABLE messages;--", 200)
    assert "%s" in executed[1][0] and executed[1][1] == [("sid", "user", "x")]
