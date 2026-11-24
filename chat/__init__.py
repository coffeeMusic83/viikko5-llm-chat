"""Week 5: a web chat that talks to a language model running locally with Ollama.

The application factory takes the storage and the model client as arguments so that
the automated tests can replace them with fakes (no real database or model needed).
"""

import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .llm import LLMError, OllamaClient
from .store import MariaDBStore, StoreError

COOKIE_NAME = "viikko5_session"
MAX_MESSAGE_CHARS = 2000
HISTORY_FOR_MODEL = 20

APP_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_URL = "http://195.148.21.16/viikko5/"
REPO_URL = "https://github.com/coffeeMusic83/viikko5-llm-chat"

EVIDENCE_FILES = [
    ("systemctl-status.txt", "systemctl status viikko5 / systemctl show viikko5 -p User -p Group"),
    ("ls-l.txt", "ls -l of the application directory and the environment file"),
    ("grants.txt", "SHOW GRANTS FOR 'viikko5app'@'localhost';"),
    ("ollama-free.txt", "ollama list and free -h with the model loaded"),
    ("ss-ltnp.txt", "sudo ss -ltnp (model server and app server on 127.0.0.1 only)"),
]


def read_revision(app_root=APP_ROOT):
    """The deployment script writes the Git commit SHA (github.sha) to REVISION."""
    try:
        return (Path(app_root) / "REVISION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def read_evidence(app_root=APP_ROOT):
    folder = Path(app_root) / "docs" / "evidence"
    items = []
    for name, title in EVIDENCE_FILES:
        try:
            text = (folder / name).read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        items.append({"name": name, "title": title, "text": text})
    return items


def valid_session_id(value):
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError):
        return None


def create_app(store=None, llm=None, revision=None, app_root=APP_ROOT):
    app = Flask(__name__)
    # Nginx serves the app under /viikko5/ and sends X-Forwarded-Prefix,
    # so url_for() builds links like /viikko5/static/style.css.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    store = store or MariaDBStore.from_env()
    llm = llm or OllamaClient.from_env()
    app.config["REVISION"] = revision or read_revision(app_root)
    app.config["MODEL_NAME"] = getattr(llm, "model", "unknown")

    def set_session_cookie(response, session_id):
        # No max_age: a browser-session cookie. A new browser session (or a private
        # window) has no cookie and therefore starts with an empty conversation.
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="Lax",
            path=(request.script_root or "") + "/",
        )
        return response

    @app.context_processor
    def common():
        rev = app.config["REVISION"]
        return {
            "revision": rev,
            "short_revision": rev[:7],
            "model": app.config["MODEL_NAME"],
            "repo_url": REPO_URL,
            "public_url": PUBLIC_URL,
        }

    @app.get("/")
    def index():
        session_id = valid_session_id(request.cookies.get(COOKIE_NAME))
        is_new = session_id is None
        messages, error = [], None
        if is_new:
            session_id = str(uuid.uuid4())
        else:
            try:
                messages = store.get_messages(session_id)
            except StoreError:
                error = "The conversation history could not be loaded."
        response = app.make_response(render_template("index.html", messages=messages, error=error))
        if is_new:
            set_session_cookie(response, session_id)
        return response

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        text = str(data.get("message", "")).strip()
        if not text:
            return jsonify(error="Message is empty."), 400
        if len(text) > MAX_MESSAGE_CHARS:
            return jsonify(error=f"Message is longer than {MAX_MESSAGE_CHARS} characters."), 400

        session_id = valid_session_id(request.cookies.get(COOKIE_NAME))
        is_new = session_id is None
        if is_new:
            session_id = str(uuid.uuid4())

        try:
            history = [] if is_new else store.get_messages(session_id, limit=HISTORY_FOR_MODEL)
        except StoreError:
            return jsonify(error="Database error."), 500

        try:
            reply = llm.chat(history + [{"role": "user", "content": text}])
        except LLMError:
            return jsonify(error="The language model did not answer. Try again."), 502

        try:
            store.add_messages(
                session_id,
                [{"role": "user", "content": text}, {"role": "assistant", "content": reply}],
            )
        except StoreError:
            return jsonify(error="Database error."), 500

        response = jsonify(reply=reply)
        if is_new:
            set_session_cookie(response, session_id)
        return response

    @app.post("/new")
    def new_conversation():
        response = redirect(url_for("index"))
        return set_session_cookie(response, str(uuid.uuid4()))

    @app.get("/health")
    def health():
        return jsonify(status="ok", commit=app.config["REVISION"], model=app.config["MODEL_NAME"])

    @app.get("/docs")
    def docs():
        return render_template("docs.html", evidence=read_evidence(app_root))

    return app

