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

## Accounts and privacy

Several people can use the app, and **everyone's tasks, categories and reminder devices are
completely private to them.** It signs in through the shared front door (the dashboard) and is default-deny: signing
in is not enough, a person needs an account here. Only administrators (`ADMIN_EMAILS`) can create accounts, from the
**Users** page (also remove, restore, or delete a removed person's data); an administrator's own account is made on their
first sign-in, and they take over the data that existed before accounts (it was parked on a placeholder user by the
migration).

How it is enforced, so a forgotten check in one route cannot leak: `shared_python.accounts_gate` wraps the whole app and
runs every request inside the signed-in person's scope, and `shared_python.owned` filters every database read and write
to that person below the app's own code (and refuses a row that points at another person's row). `app/access.py` and
`tests/test_accounts.py` (a second person calls every route against the first person's data) are the places to look.
Anything new that holds a person's data must inherit `owned.OwnedMixin` (a test fails otherwise) and must not use raw SQL.

Reminders are sent per person, only to that person's own devices; a device registered to one account is never taken over by another
(turn reminders off in the browser and on again to move a shared device).

**Jobs are not here any more (2026-11-20).** The job tracker, fit scoring, tailored resume and cover letter, and the Chrome extension's CSV import all
moved to the resume app (its Jobs page). A task can still carry a plain **link** (`tasks.link_url`, shown as "link" on its card and editable in the task
window and the New task form), which is where an "Apply to ..." task keeps its posting. The old `jobs` and `people` tables, and `tasks.job_id`, are
left in the database untouched as a record (nothing reads them; deleting a removed person's data still clears them). Marking such a task done no
longer marks anything applied: that lives on the job in the resume app.

### Environment variables (task reminder push notifications)

The "Remind me" fields on a task (see Notes below) need a VAPID keypair -
this app's own Web Push identity, not a secret shared with anyone else.
Generate one once:

```bash
source venv/bin/activate
python -m app.push generate-vapid-keys
```

which prints both values below - both are plain base64url text (only
`A-Z`/`a-z`/`0-9`/`-`/`_`), so they're safe to drop straight into a
`systemd` `Environment=` line with no quoting surprises.

| Variable | Required for | Notes |
|---|---|---|
| `VAPID_PUBLIC_KEY` | The browser's push subscription call, and the frontend | Same string the frontend uses as `applicationServerKey` |
| `VAPID_PRIVATE_KEY` | Actually signing/sending each push | Keep this one secret - it's what proves pushes came from this app |
| `VAPID_SUBJECT` | Required by the Web Push spec | Optional - defaults to a `mailto:` for Evan; a push service can contact this if your usage looks like a problem |

Without these set, generating/editing a reminder still works fine - the
scheduler just logs a failure each check cycle instead of sending anything,
rather than crashing the app.

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

## Tests

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
```

They run against a throwaway SQLite file built by the real migrations (the app reads
`DATABASE_URL`, which `tests/conftest.py` points at it), so your `tasks.db` is never touched.
The same variable lets you try the app on a copy of your data:
`DATABASE_URL=sqlite:////tmp/copy.db alembic upgrade head`, then start uvicorn with it set.

## Deploying

Runs as a systemd service on the Digital Ocean droplet, reached through a
Cloudflare Tunnel (no inbound ports opened on the droplet) and gated by
the dashboard sign-in plus an account in this app (`app/access.py`; see
`../DEPLOYMENT.md`, "Signing in with Auth0") - see `deploy/time-management.service`.

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
<hostname>`). Sign-in is handled by the app itself, so no Cloudflare Access
policy is needed for the hostname (until the cutover in `../DEPLOYMENT.md`
is finished, an existing Access policy in front of it is harmless).

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
  any task still references it. Everyone starts with the three defaults.
- `due_date` and `scheduled_date` are stored as separate columns, but for now
  both are set together whenever a task is placed on the calendar - there's
  no UI yet to make them diverge.
- Any task still marked "open" whose scheduled day has passed automatically
  rolls forward to today the next time the app is opened - except recurring
  tasks (the origin or any of its materialized occurrences), which stay put
  on their original day if left unfinished. Rolling those forward would land
  them on a day that already has (or will get) its own occurrence, producing
  a duplicate.
- A task can carry an optional plain link (for example a job posting): it shows as "link" on the card and an "Open the link" entry in the task window. Added in the New
  task form or the task window; it is copied onto each occurrence of a repeating task. (Jobs themselves live in the resume app now; see "Accounts and privacy".)
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
- A scheduled task can be set to send a push notification if it's still
  open at a chosen time ("Remind me if not done" in its edit modal - only
  available once the task is scheduled on a day, since a reminder needs a
  concrete date+time). Optionally repeat the nag every 15/30/60/120
  minutes as long as the task is still open, up to a chosen max count (or
  unlimited). Notifications go to every device that's enabled reminders,
  not just one - there's no per-person routing. Enable this per-device
  from Settings ("Enable reminders on this device"); it's independent
  per browser/phone, so everyone who wants nagging needs to enable it on
  their own device. Editing the reminder time/snooze/max, or reopening a
  done task, restarts the count from zero. Backed by a small in-process
  scheduler (checks every 15 seconds) and Web Push - see "Environment
  variables" below for the VAPID keys this needs configured, and note
  iOS requires 16.4+ and the app added to the home screen (push
  permission can't be requested from a plain Safari tab). The notification
  itself has a "Mark done" action (long-press/pull-down to reveal it, same
  as any native notification) that PATCHes the task straight from the
  service worker with no app UI involved - if that fails for any reason
  (most likely a lapsed sign-in session, which needs a real
  browser to sign in again), it falls back to opening the app instead of
  silently doing nothing.
- The backend (`app/`) is a plain JSON REST API; the frontend
  (`static/app.js`) is a thin vanilla-JS client (drag-and-drop via SortableJS)
  with no build step. That split is intentional so the frontend can later be
  swapped for something richer (e.g. React, or a native iOS app) without
  touching the API.

## To do

The running to-do list for all projects is `../TODO.md` (in the personal-projects
folder, one level up; not in git).
