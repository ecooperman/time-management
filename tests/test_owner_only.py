"""The whole app is private to its administrators. It has no accounts of its own, so this is the only thing between
the internet and the data once Cloudflare Access is no longer in front of it. The sweep calls EVERY route with no
sign-in and as someone who is not an administrator; a route added later cannot slip past (the gate is middleware
around the whole app) and this fails if one ever does."""
import re
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from shared_python import auth, settings

from app import config
from app.main import app

ISSUER = "https://login.example.com"
CLIENT = "client-123"
FRONT = "https://dashboard.example.org"
PAGES = ["/", "/jobs.html", "/admin.html"]


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def production(monkeypatch, key):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"owner@example.com"})
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", FRONT + "/auth/login")
    monkeypatch.setattr(auth, "_oidc_signing_key", lambda _t: key.public_key())
    return TestClient(app, base_url="https://time.example.org", follow_redirects=False)


def session(key, email):
    return jwt.encode(
        {"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": email, "email_verified": True}, key, algorithm="RS256"
    )


def every_route():
    for shown, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() not in ("HEAD", "OPTIONS"):
                yield method.upper(), shown, re.sub(r"\{[^}]+\}", "1", shown)


def call(client, method, path):
    body = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
    return client.request(method, path, **body)


def test_there_are_routes_to_sweep():
    assert len(list(every_route())) > 25  # guards against the sweep silently covering nothing


def test_nobody_signed_out_gets_anything_from_any_route(production):
    answered = []
    for method, shown, path in every_route():
        resp = call(production, method, path)
        if resp.status_code not in (401, 302):
            answered.append((method, shown, resp.status_code))
    for page in PAGES + ["/app.js", "/jobs.js", "/admin.js", "/style.css", "/nav.js", "/version.js", "/nope"]:
        if production.get(page).status_code != 302:
            answered.append(("GET", page))
    assert not answered, f"answered with no sign-in: {answered}"


def test_nobody_signed_in_as_a_stranger_gets_anything_either(production, key):
    production.cookies.set("oidc_session", session(key, "stranger@example.com"))
    answered = [
        (method, shown, status)
        for method, shown, path in every_route()
        if (status := call(production, method, path).status_code) != 403
    ]
    assert not answered, f"answered a signed-in stranger: {answered}"
    assert production.get("/").status_code == 403 and production.get("/app.js").status_code == 403


def test_the_administrator_gets_the_app(production, key):
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    for page in PAGES:
        assert production.get(page).status_code == 200
    assert production.get("/api/tasks").status_code == 200


def test_a_signed_out_visitor_to_a_page_is_sent_to_sign_in_and_back(production):
    resp = production.get("/jobs.html")
    assert resp.status_code == 302 and resp.headers["location"].startswith(FRONT + "/auth/login?next=")


def test_the_installable_app_files_and_the_push_service_worker_stay_public(production):
    assert production.get("/manifest.json").status_code == 200
    assert production.get("/icons/icon-192.png").status_code == 200
    assert production.get("/sw.js").status_code == 200
    assert production.get("/icons/../app.js").status_code in (302, 401, 404)


def test_the_service_worker_is_the_only_script_that_is_public(production):
    for path in ("/app.js", "/jobs.js", "/admin.js", "/nav.js"):
        assert production.get(path).status_code == 302


def test_nothing_private_is_in_the_public_files(production):
    for path in ("/manifest.json", "/sw.js"):
        body = production.get(path).text.lower()
        assert "api/tasks?" not in body and "token" not in body.replace("push", "")  # no data, no secrets


def test_without_an_administrator_configured_in_production_nobody_gets_in(production, key, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", set())
    production.cookies.set("oidc_session", session(key, "owner@example.com"))
    assert production.get("/api/tasks").status_code == 503


def test_locally_the_dev_user_is_the_administrator(client):
    assert client.get("/").status_code == 200 and client.get("/api/tasks").status_code == 200
