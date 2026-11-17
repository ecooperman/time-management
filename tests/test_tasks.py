from datetime import datetime, timedelta


def make_task(client, category, **fields):
    body = {"title": "Do the thing", "category_id": category["id"], **fields}
    response = client.post("/api/tasks", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def backlog_ids(client):
    return [t["id"] for t in client.get("/api/tasks/backlog").json()]


def test_a_new_task_with_no_date_is_in_the_backlog(client, category):
    task = make_task(client, category)
    assert task["status"] == "open" and task["scheduled_date"] is None
    assert backlog_ids(client) == [task["id"]]


def test_scheduling_a_task_takes_it_out_of_the_backlog(client, category):
    task = make_task(client, category)
    tomorrow = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    client.patch(f"/api/tasks/{task['id']}", json={"scheduled_date": tomorrow})
    assert backlog_ids(client) == []


def test_marking_done_stamps_the_time_and_reopening_clears_it(client, category):
    task = make_task(client, category)
    done = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"] is not None
    reopened = client.patch(f"/api/tasks/{task['id']}", json={"status": "open"}).json()
    assert reopened["completed_at"] is None


def test_finishing_a_job_task_marks_the_job_applied_and_reopening_undoes_it(client, category):
    job = client.post("/api/jobs", json={"name": "Analyst", "url": "https://example.com/job"}).json()
    task = make_task(client, category, job_id=job["id"])

    client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert [j["applied"] for j in client.get("/api/jobs").json()] == [True]

    client.patch(f"/api/tasks/{task['id']}", json={"status": "open"})
    assert [j["applied"] for j in client.get("/api/jobs").json()] == [False]


def test_putting_a_scheduled_task_on_hold_returns_it_to_the_backlog(client, category):
    today = datetime.now().replace(microsecond=0).isoformat()
    task = make_task(client, category)
    client.patch(f"/api/tasks/{task['id']}", json={"scheduled_date": today})
    held = client.patch(f"/api/tasks/{task['id']}", json={"status": "on_hold"}).json()
    assert held["scheduled_date"] is None
    assert backlog_ids(client) == [task["id"]]


def test_an_open_task_scheduled_in_the_past_rolls_forward_to_today(client, category):
    task = make_task(client, category)
    yesterday = (datetime.now() - timedelta(days=1)).replace(microsecond=0).isoformat()
    client.patch(f"/api/tasks/{task['id']}", json={"scheduled_date": yesterday})
    client.get("/api/tasks/backlog")  # rollover happens on read
    moved = client.get(f"/api/tasks/{task['id']}").json()
    assert moved["scheduled_date"][:10] == datetime.now().date().isoformat()


def test_a_finished_task_stays_on_its_day(client, category):
    task = make_task(client, category)
    yesterday = (datetime.now() - timedelta(days=1)).replace(microsecond=0).isoformat()
    client.patch(f"/api/tasks/{task['id']}", json={"scheduled_date": yesterday, "status": "done"})
    client.get("/api/tasks/backlog")
    assert client.get(f"/api/tasks/{task['id']}").json()["scheduled_date"][:10] == yesterday[:10]


def test_a_missing_task_is_a_404(client):
    assert client.get("/api/tasks/9999").status_code == 404


def test_a_category_with_tasks_cannot_be_deleted(client, category):
    make_task(client, category)
    assert client.delete(f"/api/categories/{category['id']}").status_code == 409


def test_an_unused_category_can_be_deleted(client):
    created = client.post("/api/categories", json={"name": "Errands", "color": "#112233"}).json()
    assert client.delete(f"/api/categories/{created['id']}").status_code == 200
    assert created["id"] not in [c["id"] for c in client.get("/api/categories").json()]


def test_a_job_with_tasks_cannot_be_deleted(client, category):
    job = client.post("/api/jobs", json={"name": "Analyst", "url": "https://example.com/j"}).json()
    make_task(client, category, job_id=job["id"])
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409


def test_a_recurring_task_is_never_filled_in_further_ahead_than_a_calendar_could_show(client, category, db):
    from datetime import datetime

    from app import crud, models

    task = client.post("/api/tasks", json={"title": "daily", "category_id": category["id"]}).json()
    client.patch(f"/api/tasks/{task['id']}", json={"scheduled_date": datetime.now().isoformat(), "repeat_daily": True})
    client.get("/api/tasks", params={"start": "2000-01-01T00:00:00", "end": "2100-01-01T00:00:00"})
    made = db.query(models.Task).filter(models.Task.series_id == task["id"]).count()
    assert 0 < made <= crud.MAX_DAYS_AHEAD
