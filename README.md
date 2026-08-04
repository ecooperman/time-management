# Time Management

A small local task/calendar app for managing job-search time across three
buckets: Home, Resume-Building, and Applying for Jobs.

## Run it

```bash
cd time-management
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

Then open http://127.0.0.1:8010 (host/port are set in `app/config.py` - change it there if 8010 ever collides with something else).

The SQLite database (`tasks.db`) is not created by the app itself - `alembic
upgrade head` creates it (and the three default categories get seeded in on
first app startup). This only needs to be run once for a fresh install; see
below for how schema changes are handled from here on.

## Schema changes (Alembic)

Schema is owned by migrations under `migrations/versions/`, not by wiping
`tasks.db`. To change the schema:

```bash
# 1. Edit app/models.py as usual
# 2. Generate a migration from the diff
alembic revision --autogenerate -m "short description"
# 3. Look over the generated file in migrations/versions/ - autogenerate
#    is good but not infallible (e.g. it won't detect a plain column rename
#    on its own)
# 4. Apply it
alembic upgrade head
```

This preserves existing data. Useful commands: `alembic current` (what
revision the db is at), `alembic check` (does the db match `models.py`
right now), `alembic downgrade -1` (undo the last migration).

SQLite can't `ALTER TABLE` to add a constraint (e.g. a new foreign key)
directly, so `migrations/env.py` has `render_as_batch=True` set, which makes
autogenerate wrap those changes in `op.batch_alter_table(...)` (SQLite
rebuilds the table under the hood). If autogenerate produces a
`batch_op.create_foreign_key(None, ...)` / `drop_constraint(None, ...)` call,
give it an explicit name (e.g. `'fk_tasks_job_id_jobs'`) in both `upgrade()`
and `downgrade()` - SQLite's batch mode needs a name to reference, and will
fail with `ValueError: Constraint must have a name` otherwise.

## Deploying

Runs as a systemd service on the Digital Ocean droplet, reached through a
Cloudflare Tunnel (no inbound ports opened on the droplet) and gated by
Cloudflare Access - see `deploy/time-management.service`.

One-time setup on the droplet:

```bash
sudo mkdir -p /opt/apps/time-management && sudo chown deploy:deploy /opt/apps/time-management
# as the deploy user:
git clone https://github.com/ecooperman/time-management.git /opt/apps/time-management
cd /opt/apps/time-management
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo cp deploy/time-management.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now time-management
```

Then add an ingress entry for `127.0.0.1:8010` to `/etc/cloudflared/config.yml`,
route DNS for its hostname (`cloudflared tunnel route dns <tunnel-name>
<hostname>`), and add a Cloudflare Access policy for that hostname.

Ongoing deploys are automatic: `.github/workflows/deploy.yml` runs on every
push to `main` - it SSHes in, pulls, reinstalls dependencies, runs `alembic
upgrade head`, and restarts the service. Needs these repo secrets set once
(Settings -> Secrets and variables -> Actions): `DO_HOST`, `DO_USER` (the
`deploy` user), `DO_SSH_KEY` (that user's private key).

## Notes

- New tasks start in the backlog (sidebar) unscheduled; drag them onto the
  calendar to place them on a day.
- Categories (name/color) are managed from the "Manage categories" link in
  the sidebar, which opens `/admin.html`. A category can't be deleted while
  any task still references it.
- `due_date` and `scheduled_date` are stored as separate columns, but for now
  both are set together whenever a task is placed on the calendar - there's
  no UI yet to make them diverge.
- Any task still marked "open" whose scheduled day has passed automatically
  rolls forward to today the next time the app is opened - except recurring
  tasks (the origin or any of its materialized occurrences), which stay put
  on their original day if left unfinished. Rolling those forward would land
  them on a day that already has (or will get) its own occurrence, producing
  a duplicate.
- Jobs (name/URL/applied, plus optional company name/URL) live in their own
  sidebar section below the backlog. Company name shows on both the job card
  and any task linked to that job (as a link, if a company URL was given). A
  job is a drag *source*, not something you reorder into place:
  dragging a job card onto a day (or onto the backlog) clones out a new task
  titled "Apply to `<job name>`", linked to that job, defaulting to the
  "Applying for Jobs" category - the job card itself stays put, so you can
  drag it again later for a follow-up or interview-prep task. Marking a
  job-linked task done sets that job's `applied` flag to true; using
  "Reopen" on that same task sets it back to false. The job's `applied`
  checkbox can also be toggled directly, independent of any task. A job
  can't be deleted while any task still links to it. Clicking a job card
  (anywhere except its URL link, Applied checkbox, or delete button) opens
  an edit modal for all of its fields.
- The calendar defaults to Work Week view on load.
- A task can be set to repeat daily from its modal (only once it's been
  scheduled on a day - repeating needs a start date). Occurrences for days
  you haven't viewed yet are created lazily, only from today forward, when
  you browse to a range that includes them; each occurrence is otherwise a
  fully independent task once it exists - marking one done, editing it, or
  dragging it to another day never affects the others. An optional "repeat
  until" date bounds the series; leaving it blank repeats indefinitely.
  Unchecking "repeat daily" (or pulling the end date in, or deleting the
  origin task) deletes not-yet-passed future occurrences of that series -
  past occurrences are left alone as history.
- The backend (`app/`) is a plain JSON REST API; the frontend
  (`static/app.js`) is a thin vanilla-JS client (drag-and-drop via SortableJS)
  with no build step. That split is intentional so the frontend can later be
  swapped for something richer (e.g. React, or a native iOS app) without
  touching the API.
