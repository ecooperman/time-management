"""Several people can use this app, and each person's tasks, jobs, categories and reminders are completely private.

The tests that matter most are the two-person ones: one person makes data, then ANOTHER person with a valid account
tries every route of the app against it (reading, listing, changing, deleting, pointing their own data at it) and must
get nothing and change nothing. Alongside: who can get in at all (default-deny), that no sign-in trick makes one person
another, who may invite, that reminders only ever go to their owner's own devices, and that what acts as the
administrator (resume generation) stays the administrator's."""
import re
import sqlite3
import time
from datetime import datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from shared_python import auth, owned, settings

from app import access, config, crud, models, notify, push, reminders
from app.database import SessionLocal
from app.main import app

ISSUER = "https://login.example.com"
CLIENT = "client-123"
FRONT = "https://dashboard.example.org"
ADMIN = "owner@example.com"
BOB_TASK = "SECRET-BOB-TASK-XYZ"
BOB_JOB = "SECRET-BOB-JOB-XYZ"
BOB_CATEGORY = "Secret-Bob-Category"
BOB_PERSON = "Secret-Bob-Person"
BOB_ENDPOINT = "https://push.example.com/bobs-secret-device"
OWNED_TABLES = (models.Category, models.Person, models.Job, models.Task, models.PushSubscription)
EVERYTHING = ("categories", "people", "jobs", "tasks")
def _range():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return {"start": (today - timedelta(days=7)).isoformat(), "end": (today + timedelta(days=14)).isoformat()}


WIDE = _range()


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def production(monkeypatch, key):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {ADMIN})
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", FRONT + "/auth/login")
    monkeypatch.setattr(auth, "_oidc_signing_key", lambda _t: key.public_key())
    sent = []
    monkeypatch.setattr(notify, "tell_let_in", lambda to, inviter: sent.append((to, inviter)))
    return sent


def session(key, email, **kw):
    claims = {"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": email, "email_verified": True}
    claims.update(kw)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture()
def person(key, production):
    def make(email, **kw):
        c = TestClient(app, base_url="https://time.example.org", follow_redirects=False)
        c.cookies.set("oidc_session", session(key, email, **kw))
        return c

    return make


@pytest.fixture()
def people(make_user):
    """Bob and Carol have accounts; Dana does not; Eve's access was removed."""
    return {"bob": make_user("bob@example.com"), "carol": make_user("carol@example.com"),
            "eve": make_user("eve@example.com", status=models.USER_REMOVED)}


def fill_bobs_data(bob):
    """Everything a person can own, with recognisable names."""
    cat = bob.post("/api/categories", json={"name": BOB_CATEGORY, "color": "#112233"})
    assert cat.status_code == 200, cat.text
    who = bob.post("/api/people", json={"name": BOB_PERSON, "color": "#445566"})
    assert who.status_code == 200, who.text
    job = bob.post("/api/jobs", json={"name": BOB_JOB, "url": "https://example.com/bobs-job", "person_id": who.json()["id"]})
    assert job.status_code == 200, job.text
    task = bob.post("/api/tasks", json={"title": BOB_TASK, "category_id": cat.json()["id"], "job_id": job.json()["id"]})
    assert task.status_code == 200, task.text
    today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    series = bob.post("/api/tasks", json={"title": "bob-daily", "category_id": cat.json()["id"]}).json()["id"]
    resp = bob.patch(f"/api/tasks/{series}", json={"scheduled_date": today, "repeat_daily": True, "remind_at": "2020-01-01T00:00:00"})
    assert resp.status_code == 200, resp.text
    assert bob.post("/api/push/subscribe", json={"endpoint": BOB_ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}}).status_code == 200
    snapshot(bob)  # looking at the calendar fills in the recurring task's days once; the reference is taken after that
    return snapshot(bob)


def snapshot(who):
    shot = {name: who.get(f"/api/{name}").json() for name in EVERYTHING}
    shot["backlog"] = who.get("/api/tasks/backlog").json()
    shot["calendar"] = who.get("/api/tasks", params=WIDE).json()
    return shot


def devices_of(user_id):
    with owned.scope(user_id), SessionLocal() as db:
        return sorted(row.endpoint for row in db.query(models.PushSubscription).all())


def every_route():
    for shown, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() not in ("HEAD", "OPTIONS"):
                yield method.upper(), shown


def fill(shown, ids):
    def sub(match):
        name = match.group(1)
        return str(ids.get(name, "x" if name == "batch_id" else 1))

    return re.sub(r"\{([^}]+)\}", sub, shown)


# --- who gets in (default-deny) ---------------------------------------------------------------------------------------


def test_a_person_with_an_account_gets_in(person, people):
    assert person("bob@example.com").get("/api/me").json()["id"] == people["bob"]


def test_signed_in_is_not_enough_a_person_nobody_let_in_gets_nothing_from_any_route(person, people):
    dana = person("dana@example.com")
    leaked = []
    for method, shown in every_route():
        resp = dana.request(method, fill(shown, {}), json={} if method in ("POST", "PATCH", "PUT") else None)
        if resp.status_code != 403:
            leaked.append((method, shown, resp.status_code))
    assert not leaked, leaked
    for path in ("/", "/jobs.html", "/admin.html", "/users.html", "/app.js"):
        assert dana.get(path).status_code == 403
    page = dana.get("/")
    assert "have access yet" in page.text and "dana@example.com" in page.text
    assert f'href="{FRONT}/auth/logout"' in page.text


def test_a_person_whose_access_was_removed_gets_nothing_and_is_told_so(person, people):
    eve = person("eve@example.com")
    assert eve.get("/api/tasks").status_code == 403 and eve.get("/api/me").status_code == 403
    assert "access was removed" in eve.get("/").text


def test_nobody_signed_out_gets_anything(person, people):
    signed_out = TestClient(app, base_url="https://time.example.org", follow_redirects=False)
    answered = []
    for method, shown in every_route():
        resp = signed_out.request(method, fill(shown, {}), json={} if method in ("POST", "PATCH", "PUT") else None)
        if resp.status_code not in (401, 302):
            answered.append((method, shown, resp.status_code))
    for path in ("/", "/jobs.html", "/admin.html", "/users.html", "/app.js", "/jobs.js", "/admin.js", "/users.js", "/nav.js", "/style.css", "/nope"):
        if signed_out.get(path).status_code != 302:
            answered.append(("GET", path))
    assert not answered, answered


def test_the_first_administrator_to_sign_in_gets_an_account_and_a_stranger_posing_as_one_does_not(person, people):
    assert person(ADMIN).get("/api/me").json()["is_admin"] is True
    assert person("owner+x@example.com").get("/api/me").status_code == 403  # a plus alias is a different person
    assert person("Owner@Example.com").get("/api/me").json()["email"] == ADMIN  # case does not matter


def test_a_new_account_starts_with_the_default_categories_and_nothing_else(person, people):
    for email in ("bob@example.com", ADMIN):
        who = person(email)
        assert sorted(c["name"] for c in who.get("/api/categories").json()) == ["Applying for Jobs", "Home", "Resume-Building"]
        assert who.get("/api/tasks/backlog").json() == [] and who.get("/api/jobs").json() == [] and who.get("/api/people").json() == []


# --- no sign-in trick makes one person another --------------------------------------------------------------------------------


def test_a_token_signed_by_anyone_else_is_refused(person, people, key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": "bob@example.com", "email_verified": True}, other, algorithm="RS256")
    c = TestClient(app, base_url="https://time.example.org", follow_redirects=False)
    c.cookies.set("oidc_session", forged)
    assert c.get("/api/tasks").status_code == 401


@pytest.mark.parametrize("kw", [{"aud": "another-app"}, {"email_verified": False}, {"exp": 1}, {"iss": "https://evil.example.com"}])
def test_a_token_for_the_wrong_app_issuer_unverified_or_expired_is_refused(person, people, kw):
    assert person("bob@example.com", **kw).get("/api/tasks").status_code == 401


def test_a_claim_of_identity_in_a_header_or_cookie_is_never_trusted(person, people):
    c = TestClient(app, base_url="https://time.example.org", follow_redirects=False)
    for headers in ({"Cf-Access-Authenticated-User-Email": "bob@example.com"}, {"X-Forwarded-User": "bob@example.com"}):
        assert c.get("/api/tasks", headers=headers).status_code == 401
    assert c.get("/api/tasks", cookies={"dev_user": "bob@example.com"}).status_code == 401


def test_a_body_or_query_naming_another_person_changes_nothing(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    fill_bobs_data(bob)
    before = snapshot(bob)
    cat = carol.get("/api/categories").json()[0]["id"]
    for extra in ({"owner_id": people["bob"]}, {"user_id": people["bob"]}, {"email": "bob@example.com"}):
        resp = carol.post("/api/tasks", json={"title": "carols", "category_id": cat, **extra})
        assert resp.status_code in (200, 422)  # the extra fields are simply ignored
    mine = carol.get("/api/tasks/backlog", params={"owner_id": people["bob"], "user_id": people["bob"]}).json()
    assert {t["title"] for t in mine} == {"carols"} and BOB_TASK not in str(mine)  # all hers, none Bob's
    assert snapshot(bob) == before  # and nothing was added to or taken from Bob


# --- whose data they see: the two-person tests ----------------------------------------------------------------------------------


def test_each_person_sees_only_their_own_data(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    fill_bobs_data(bob)
    carol.post("/api/tasks", json={"title": "carols-task", "category_id": carol.get("/api/categories").json()[0]["id"]})
    assert BOB_TASK in str(bob.get("/api/tasks/backlog").json()) and "carols-task" not in str(snapshot(bob))
    assert [t["title"] for t in carol.get("/api/tasks/backlog").json()] == ["carols-task"]
    assert carol.get("/api/jobs").json() == [] and carol.get("/api/people").json() == []
    assert BOB_CATEGORY not in str(carol.get("/api/categories").json())
    assert BOB_TASK not in str(snapshot(carol))


def test_another_person_can_neither_read_nor_change_nor_delete_anything_through_any_route(person, people):
    """Bob owns data; Carol, with a perfectly valid account, calls EVERY route of the app aimed at Bob's rows."""
    bob, carol = person("bob@example.com"), person("carol@example.com")
    before = fill_bobs_data(bob)
    ids = {
        "task_id": before["tasks"] and next(t["id"] for t in before["backlog"] if t["title"] == BOB_TASK),
        "job_id": before["jobs"][0]["id"], "person_id": before["people"][0]["id"], "user_id": people["bob"],
        "category_id": next(c["id"] for c in before["categories"] if c["name"] == BOB_CATEGORY),
    }
    tried, leaked = 0, []
    for method, shown in every_route():
        path = fill(shown, ids)
        kwargs = {}
        if method in ("POST", "PATCH", "PUT"):
            kwargs["json"] = {
                "title": "HIJACKED", "name": "HIJACKED", "color": "#000000", "description": "HIJACKED", "url": "https://example.com/h",
                "category_id": ids["category_id"], "job_id": ids["job_id"], "person_id": ids["person_id"],
                "job_ids": [ids["job_id"]], "updates": [{"id": ids["task_id"], "sort_order": 1, "scheduled_date": None}],
                "email": "hijack@example.com", "endpoint": BOB_ENDPOINT, "keys": {"p256dh": "x", "auth": "y"},
            }
        resp = carol.request(method, path, params={"person_id": ids["person_id"], "category_id": ids["category_id"], **WIDE}, **kwargs)
        tried += 1
        for mark in (BOB_TASK, BOB_JOB, BOB_CATEGORY, BOB_PERSON, "bob-daily"):
            if mark in resp.text:
                leaked.append((method, shown, f"{mark} in the response"))
        if method in ("PATCH", "PUT", "DELETE") and resp.status_code < 300:
            leaked.append((method, shown, resp.status_code))
        if method == "GET" and "{" in shown and resp.status_code == 200:
            leaked.append((method, shown, "an id route answered"))
    assert tried > 25 and not leaked, leaked
    assert snapshot(bob) == before  # not a name, a link, a date or a row changed
    assert devices_of(people["bob"]) == [BOB_ENDPOINT]
    assert "HIJACKED" not in str(snapshot(bob))
    assert BOB_TASK not in str(snapshot(carol)) and BOB_JOB not in str(snapshot(carol))


def test_pointing_ones_own_data_at_someone_elses_is_refused(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    before = fill_bobs_data(bob)
    bobs_cat = next(c["id"] for c in before["categories"] if c["name"] == BOB_CATEGORY)
    bobs_job, bobs_person = before["jobs"][0]["id"], before["people"][0]["id"]
    bobs_task = next(t["id"] for t in before["backlog"] if t["title"] == BOB_TASK)
    mine_cat = carol.get("/api/categories").json()[0]["id"]
    assert carol.post("/api/tasks", json={"title": "x", "category_id": bobs_cat}).status_code == 400
    assert carol.post("/api/tasks", json={"title": "x", "category_id": mine_cat, "job_id": bobs_job}).status_code == 400
    mine = carol.post("/api/tasks", json={"title": "mine", "category_id": mine_cat}).json()["id"]
    assert carol.patch(f"/api/tasks/{mine}", json={"category_id": bobs_cat}).status_code == 400
    assert carol.patch(f"/api/tasks/{mine}", json={"job_id": bobs_job}).status_code == 400
    assert carol.post("/api/jobs", json={"name": "j", "url": "https://example.com/j", "person_id": bobs_person}).status_code == 400
    myjob = carol.post("/api/jobs", json={"name": "j", "url": "https://example.com/j"}).json()["id"]
    assert carol.patch(f"/api/jobs/{myjob}", json={"person_id": bobs_person}).status_code == 400
    csv = b"url,title\nhttps://example.com/new,A job\n"
    assert carol.post("/api/jobs/import", files={"file": ("j.csv", csv)}, data={"person_id": str(bobs_person)}).status_code == 400
    # moving Bob's task by naming its id in a reorder does nothing to it
    carol.post("/api/tasks/reorder", json={"updates": [{"id": bobs_task, "sort_order": 999, "scheduled_date": "2031-01-01T00:00:00"}]})
    assert snapshot(bob) == before
    assert carol.get("/api/tasks/backlog").json()[0]["title"] == "mine"


def test_the_data_layer_alone_refuses_a_task_that_points_at_someone_elses_category(people, make_user, as_user):
    """Even if a route forgot its own check, the data layer will not save a link across two people."""
    with as_user(people["bob"]) as db:
        bobs_cat = db.query(models.Category).first().id
    with as_user(people["carol"]) as db:
        db.add(models.Task(title="sneaky", category_id=bobs_cat))
        with pytest.raises(owned.WrongOwner):
            db.flush()


def test_two_people_may_each_have_the_same_category_and_person_names(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    for who in (bob, carol):
        assert who.post("/api/people", json={"name": "Same Name", "color": "#111111"}).status_code == 200
        assert "Home" in [c["name"] for c in who.get("/api/categories").json()]  # everyone starts with the defaults
    assert bob.get("/api/people").json()[0]["id"] != carol.get("/api/people").json()[0]["id"]


def test_the_administrator_is_just_another_owner_and_cannot_read_a_persons_data_through_the_app(person, people):
    bob, admin = person("bob@example.com"), person(ADMIN)
    before = fill_bobs_data(bob)
    task_id = next(t["id"] for t in before["backlog"] if t["title"] == BOB_TASK)
    assert admin.get("/api/tasks/backlog").json() == [] and BOB_JOB not in admin.get("/api/jobs").text
    assert admin.get(f"/api/tasks/{task_id}").status_code == 404
    assert admin.delete(f"/api/tasks/{task_id}").status_code == 404
    assert snapshot(bob) == before


def test_one_persons_calendar_and_rollover_never_touch_anothers_tasks(person, people, as_user):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    cat = bob.get("/api/categories").json()[0]["id"]
    yesterday = (datetime.now() - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    task = bob.post("/api/tasks", json={"title": "overdue", "category_id": cat}).json()["id"]
    bob_sched = bob.patch(f"/api/tasks/{task}", json={"scheduled_date": yesterday}).json()
    series = bob.post("/api/tasks", json={"title": "daily", "category_id": cat}).json()["id"]
    bob.patch(f"/api/tasks/{series}", json={"scheduled_date": datetime.now().isoformat(), "repeat_daily": True})
    with as_user(people["bob"]) as db:
        occurrences = db.query(models.Task).filter(models.Task.series_id == series).count()
    # Carol opens her calendar over a long range: that runs rollover and recurring-task filling, for HER data only
    carol.get("/api/tasks", params=WIDE)
    carol.get("/api/tasks/backlog")
    with as_user(people["bob"]) as db:
        assert db.get(models.Task, task).scheduled_date.isoformat() == bob_sched["scheduled_date"]  # not rolled to today
        assert db.query(models.Task).filter(models.Task.series_id == series).count() == occurrences  # none materialized
    with as_user(people["carol"]) as db:
        assert db.query(models.Task).count() == 0


def test_removing_a_person_locks_them_out_at_once_and_keeps_their_data_private_until_deleted(person, people):
    bob, admin = person("bob@example.com"), person(ADMIN)
    before = fill_bobs_data(bob)
    assert admin.patch(f"/api/users/{people['bob']}", json={"status": "removed"}).status_code == 200
    assert bob.get("/api/tasks/backlog").status_code == 403
    assert admin.get("/api/tasks/backlog").json() == []  # still nobody else's
    admin.patch(f"/api/users/{people['bob']}", json={"status": "active"})
    assert snapshot(bob) == before  # restored: everything is still there


# --- reminders and devices: only ever the owner's ----------------------------------------------------------------------------------


@pytest.fixture()
def sent(monkeypatch):
    """Every push the reminder loop makes: (endpoint, title)."""
    out = []
    monkeypatch.setattr(push, "_vapid_private_key", lambda: "test-key")
    monkeypatch.setattr(push, "webpush", lambda subscription_info, data, **kw: out.append((subscription_info["endpoint"], __import__("json").loads(data)["title"])))
    return out


def due_task(who, title):
    cat = who.get("/api/categories").json()[0]["id"]
    task = who.post("/api/tasks", json={"title": title, "category_id": cat}).json()["id"]
    assert who.patch(f"/api/tasks/{task}", json={"remind_at": "2020-01-01T00:00:00"}).status_code == 200
    return task


def test_a_reminder_goes_only_to_its_owners_devices(person, people, sent):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    bob.post("/api/push/subscribe", json={"endpoint": "https://push.example.com/bob", "keys": {"p256dh": "k", "auth": "a"}})
    carol.post("/api/push/subscribe", json={"endpoint": "https://push.example.com/carol", "keys": {"p256dh": "k", "auth": "a"}})
    due_task(bob, "bobs-reminder")
    due_task(carol, "carols-reminder")
    reminders.check_everyones_reminders()
    assert sorted(sent) == [("https://push.example.com/bob", "bobs-reminder"), ("https://push.example.com/carol", "carols-reminder")]


def test_a_person_with_a_reminder_but_no_device_sends_nothing_to_anyone_elses(person, people, sent):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    carol.post("/api/push/subscribe", json={"endpoint": "https://push.example.com/carol", "keys": {"p256dh": "k", "auth": "a"}})
    due_task(bob, "bobs-reminder")
    reminders.check_everyones_reminders()
    assert sent == []


def test_nobody_removed_gets_reminders(person, people, sent, make_user):
    bob = person("bob@example.com")
    bob.post("/api/push/subscribe", json={"endpoint": "https://push.example.com/bob", "keys": {"p256dh": "k", "auth": "a"}})
    due_task(bob, "bobs-reminder")
    person(ADMIN).patch(f"/api/users/{people['bob']}", json={"status": "removed"})
    reminders.check_everyones_reminders()
    assert sent == []


def test_a_device_registered_to_one_person_is_never_taken_over_by_another(person, people, sent):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    device = {"endpoint": "https://push.example.com/shared-phone", "keys": {"p256dh": "k", "auth": "a"}}
    assert bob.post("/api/push/subscribe", json=device).status_code == 200
    taken = carol.post("/api/push/subscribe", json={**device, "keys": {"p256dh": "carols-key", "auth": "carols-auth"}})
    assert taken.status_code == 409 and "someone else" in taken.json()["detail"]
    assert devices_of(people["bob"]) == [device["endpoint"]] and devices_of(people["carol"]) == []
    with owned.scope(people["bob"]), SessionLocal() as db:
        assert db.query(models.PushSubscription).one().p256dh == "k"  # Carol did not even replace the keys
    due_task(carol, "carols-reminder")
    reminders.check_everyones_reminders()
    assert sent == []  # Carol's reminder is not pushed to Bob's device, and Bob's device is not Carol's
    # after Bob turns reminders off (which frees the device) Carol can register it
    assert bob.post("/api/push/unsubscribe", json={"endpoint": device["endpoint"]}).status_code == 200
    assert carol.post("/api/push/subscribe", json=device).status_code == 200


def test_nobody_can_remove_someone_elses_device(person, people):
    bob, carol = person("bob@example.com"), person("carol@example.com")
    fill_bobs_data(bob)
    carol.post("/api/push/unsubscribe", json={"endpoint": BOB_ENDPOINT})
    assert devices_of(people["bob"]) == [BOB_ENDPOINT]


# --- what acts as the administrator stays the administrator's ---------------------------------------------------------------------------


RESUME_ROUTES = [
    ("POST", "/api/jobs/1/generate-resume", None), ("GET", "/api/jobs/1/resume.pdf", None), ("GET", "/api/jobs/1/resume.docx", None),
    ("GET", "/api/jobs/1/cover-letter.pdf", None), ("GET", "/api/jobs/1/cover-letter.docx", None),
    ("POST", "/api/jobs/generate-resumes-bulk", {"job_ids": [1]}), ("GET", "/api/jobs/generate-resumes-bulk/abc", None),
    ("GET", "/api/people/resume-people", None),
]


def test_only_an_administrator_can_use_resume_generation_or_see_the_resume_apps_people(person, people):
    carol = person("carol@example.com")
    for method, path, body in RESUME_ROUTES:
        assert carol.request(method, path, json=body).status_code == 403, (method, path)
    me = carol.get("/api/me").json()
    assert me["is_admin"] is False and me["can_use"] == {"resume": False}
    assert person(ADMIN).get("/api/me").json()["can_use"] == {"resume": True}


def test_only_an_administrator_can_name_which_resume_a_person_uses(person, people):
    carol, admin = person("carol@example.com"), person(ADMIN)
    assert carol.post("/api/people", json={"name": "X", "color": "#000000", "resume_person_slug": "evan"}).status_code == 403
    mine = carol.post("/api/people", json={"name": "Y", "color": "#000000"}).json()["id"]
    assert carol.patch(f"/api/people/{mine}", json={"resume_person_slug": "evan"}).status_code == 403
    assert carol.patch(f"/api/people/{mine}", json={"name": "Renamed"}).status_code == 200  # the rest is theirs to edit
    assert admin.post("/api/people", json={"name": "Z", "color": "#000000", "resume_person_slug": "rach"}).json()["resume_person_slug"] == "rach"


def test_nothing_in_another_persons_resume_generation_batch_is_readable(person, people, monkeypatch):
    from app.routers import jobs as jobs_router

    jobs_router._BULK_BATCHES["feedface"] = {"total": 1, "done": 1, "status": "done", "owner_id": people["bob"],
                                            "results": [{"job_id": 1, "name": BOB_JOB, "ok": True, "error": None}]}
    try:
        assert person(ADMIN).get("/api/jobs/generate-resumes-bulk/feedface").status_code == 404  # an administrator's, but not theirs
        assert BOB_JOB not in person(ADMIN).get("/api/jobs/generate-resumes-bulk/feedface").text
    finally:
        jobs_router._BULK_BATCHES.pop("feedface", None)


# --- who may invite: only administrators ---------------------------------------------------------------------------------------------


def test_only_an_administrator_may_list_add_change_or_delete_people(person, people):
    carol = person("carol@example.com")
    assert carol.get("/api/users").status_code == 403
    assert carol.post("/api/users", json={"email": "friend@example.com"}).status_code == 403
    assert carol.patch(f"/api/users/{people['bob']}", json={"status": "removed"}).status_code == 403
    assert carol.delete(f"/api/users/{people['bob']}/data").status_code == 403
    assert person("bob@example.com").get("/api/tasks/backlog").status_code == 200  # untouched
    assert person("friend@example.com").get("/api/tasks/backlog").status_code == 403  # and nobody was let in


def test_an_administrator_lets_someone_in_and_they_are_told_by_email(person, production, people):
    admin = person(ADMIN)
    resp = admin.post("/api/users", json={"email": "  Newbie@Example.COM "})
    assert resp.status_code == 200 and resp.json()["email"] == "newbie@example.com"
    assert production == [("newbie@example.com", ADMIN)]
    newbie = person("newbie@example.com")
    assert newbie.get("/api/tasks/backlog").json() == [] and len(newbie.get("/api/categories").json()) == 3
    assert admin.post("/api/users", json={"email": "newbie@example.com"}).status_code == 200
    assert production == [("newbie@example.com", ADMIN)]  # not told again: nothing changed


def test_adding_a_removed_person_restores_them_and_tells_them(person, production, people):
    admin = person(ADMIN)
    assert person("eve@example.com").get("/api/tasks/backlog").status_code == 403
    assert admin.post("/api/users", json={"email": "eve@example.com"}).status_code == 200
    assert person("eve@example.com").get("/api/tasks/backlog").status_code == 200 and production == [("eve@example.com", ADMIN)]


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "x@y.", "@example.com", "legacy-owner@time.invalid", "a b@example.com"])
def test_a_bad_address_is_refused(person, people, email):
    assert person(ADMIN).post("/api/users", json={"email": email or " "}).status_code in (400, 422)


def test_an_administrators_access_cannot_be_changed_or_removed_from_the_users_page(person, production, people, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {ADMIN, "second@example.com"})
    admin = person(ADMIN)
    person("second@example.com").get("/api/me")
    users = {u["email"]: u for u in admin.get("/api/users").json()}
    assert users["second@example.com"]["is_admin"] is True
    assert admin.patch(f"/api/users/{users['second@example.com']['id']}", json={"status": "removed"}).status_code == 409
    me = admin.get("/api/me").json()["id"]
    assert admin.patch(f"/api/users/{me}", json={"status": "removed"}).status_code == 409


def test_deleting_a_removed_persons_data_deletes_exactly_theirs(person, people, as_user):
    bob, carol, admin = person("bob@example.com"), person("carol@example.com"), person(ADMIN)
    fill_bobs_data(bob)
    carol.post("/api/tasks", json={"title": "carols-task", "category_id": carol.get("/api/categories").json()[0]["id"]})
    assert admin.delete(f"/api/users/{people['bob']}/data").status_code == 409  # not removed yet
    admin.patch(f"/api/users/{people['bob']}", json={"status": "removed"})
    deleted = admin.delete(f"/api/users/{people['bob']}/data").json()["deleted"]
    assert deleted["jobs"] == 1 and deleted["people"] == 1 and deleted["tasks"] >= 2 and deleted["reminder_devices"] == 1
    assert deleted["categories"] == 4
    with as_user(people["bob"]) as db:
        assert all(db.query(model).count() == 0 for model in OWNED_TABLES)
    assert [t["title"] for t in carol.get("/api/tasks/backlog").json()] == ["carols-task"]
    assert len(carol.get("/api/categories").json()) == 3


# --- the data from before accounts -------------------------------------------------------------------------------------------------


def test_the_first_administrator_takes_over_the_data_that_existed_before_accounts_and_nobody_else_does(person, people):
    with owned.unscoped(), SessionLocal() as s:
        legacy = models.User(email=crud.LEGACY_OWNER_EMAIL)
        s.add(legacy)
        s.flush()
        cat = models.Category(name="Old", color="#000000", owner_id=legacy.id)
        s.add(cat)
        s.flush()
        s.add(models.Task(title="from-before-accounts", category_id=cat.id, owner_id=legacy.id))
        s.commit()
    assert person("bob@example.com").get("/api/tasks/backlog").json() == []  # an ordinary person gets none of it
    assert [t["title"] for t in person(ADMIN).get("/api/tasks/backlog").json()] == ["from-before-accounts"]
    assert person("carol@example.com").get("/api/tasks/backlog").json() == []
    assert all(u["email"] != crud.LEGACY_OWNER_EMAIL for u in person(ADMIN).get("/api/users").json())


# --- the rest of the gate ----------------------------------------------------------------------------------------------------------------------


def test_the_manifest_icons_and_service_worker_are_public_and_nothing_else_is(person, people):
    signed_out = TestClient(app, base_url="https://time.example.org", follow_redirects=False)
    for path in ("/manifest.json", "/icons/icon-192.png", "/sw.js"):
        assert signed_out.get(path).status_code == 200
    for path in ("/app.js", "/jobs.js", "/admin.js", "/users.js", "/nav.js", "/api/tasks", "/icons/../app.js"):
        assert signed_out.get(path).status_code in (302, 401, 404)
    body = signed_out.get("/sw.js").text.lower()
    assert "api/tasks?" not in body and "token" not in body.replace("push", "")  # no data, no secrets


def test_every_route_that_changes_something_refuses_a_request_from_another_app_or_site(person, people):
    bob = person("bob@example.com")
    tried = 0
    for method, shown in every_route():
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            continue
        for site in ("same-site", "cross-site"):
            resp = bob.request(method, fill(shown, {}), json={}, headers={"Sec-Fetch-Site": site, "Origin": "https://lists.example.org"})
            assert resp.status_code == 403 and "didn't come from this app" in resp.text, (method, shown, site)
            tried += 1
    assert tried > 10
    assert bob.get("/api/tasks/backlog").json() == []


def test_me_says_who_is_signed_in_and_where_log_out_goes(person, people):
    me = person("bob@example.com").get("/api/me").json()
    assert me["email"] == "bob@example.com" and me["logout_url"] == FRONT + "/auth/logout" and me["is_admin"] is False


def test_locally_the_dev_user_is_an_administrator_with_an_account(client, client_as, make_user):
    assert client.get("/api/me").json()["is_admin"] is True
    make_user("bob@example.com")
    assert client_as("bob@example.com").get("/api/me").json()["is_admin"] is False
    assert client_as("nobody@example.com").get("/api/me").status_code == 403


def test_no_code_in_the_app_bypasses_the_owner_filter():
    owned.assert_no_raw_sql(["app"])


def test_every_table_of_a_persons_data_has_an_owner_and_the_filter_covers_it():
    for model in OWNED_TABLES:
        assert issubclass(model, owned.OwnedMixin) and not model.__table__.c.owner_id.nullable
    owned_names = {m.__tablename__ for m in OWNED_TABLES}
    others = {t for t in models.Base.metadata.tables if t not in owned_names}
    assert others == {"users"}  # a new table of someone's data must be added to this list (and gets an owner)
    assert access.PUBLIC_PATHS == ("/manifest.json", "/icons/", "/sw.js")


def fake_apps(tmp_path, monkeypatch, **emails_by_folder):
    """Other apps' databases next to this one, each with the given people (see shared_python.directory)."""
    for folder, (filename, emails) in emails_by_folder.items():
        (tmp_path / folder).mkdir(exist_ok=True)
        connection = sqlite3.connect(tmp_path / folder / filename)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        connection.executemany("INSERT INTO users (email) VALUES (?)", [(e,) for e in emails])
        connection.commit()
        connection.close()
    monkeypatch.setenv("PEOPLE_APPS_DIR", str(tmp_path))


def test_suggestions_are_everyone_from_any_app_minus_people_already_here(person, people, tmp_path, monkeypatch):
    fake_apps(
        tmp_path, monkeypatch,
        **{"lists": ("gifts.db", ["Zed@example.com", "bob@example.com"]), "finances": ("finances.db", ["amy@example.com"])},
    )
    resp = person(ADMIN).get("/api/users/suggestions")
    assert resp.status_code == 200
    # the administrator and Bob already have access here, so they are not offered again
    assert [x["email"] for x in resp.json()] == ["amy@example.com", "zed@example.com"]


def test_suggestions_say_who_uses_the_apps_so_only_an_administrator_gets_them(person, people, tmp_path, monkeypatch):
    fake_apps(tmp_path, monkeypatch, lists=("gifts.db", ["secret-person@example.com"]))
    resp = person("carol@example.com").get("/api/users/suggestions")
    assert resp.status_code == 403 and "secret-person" not in resp.text
