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

### Environment variables (resume generation)

The "Generate Resume" feature on the Jobs page (see the Notes section below)
needs three environment variables - unset, the feature fails with a clear
error rather than crashing the app:

| Variable | Required for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Calling Claude to tailor the resume/cover letter | Standard Anthropic API key |
| `INTERNAL_API_TOKEN` | Talking to the `resume` app's internal API | Must be the exact same value set on that app's `INTERNAL_API_TOKEN` - see its README |
| `RESUME_ADMIN_URL` | Finding the `resume` app's admin API | Optional - defaults to `http://127.0.0.1:8041`, correct for the shared droplet |

Locally, export these in your shell before running the app. On the droplet,
set them directly in `/etc/systemd/system/time-management.service` (never
commit real values - see `deploy/time-management.service` for the
placeholder lines and `DEPLOYMENT.md`).

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
- Jobs can be bulk-imported from a CSV export of the
  [job-application-chrome-extension](../job-application-chrome-extension)
  fit-scoring tool ("Import Jobs from CSV" on the Jobs page). Expected
  columns: `url, title, company, salary, tier, summary, matched, gaps,
  strengths, scored_at, jd_text` (`salary` is free text - often blank, since
  most postings don't disclose it; `tier` is one of Weak/Possible/Good/Strong
  and shows as a colored badge on job cards, the task modal, and the Jobs
  page, where the rest of the scoring detail - salary, summary,
  matched/gaps/strengths, and the full job description - is viewable by
  expanding a card). Matching is by
  `url`: importing a job that's already here refreshes only the scoring
  fields, never `applied` or anything edited by hand, so re-running the
  extension and re-importing is always safe to repeat.
- Each job card on the Jobs page can generate a tailored resume + cover
  letter ("Generate Resume + Cover Letter", or "Generate Resumes for
  Filtered Jobs" to do a whole filtered batch at once, with a confirmation
  modal listing exactly which jobs first). This fetches the live resume
  data from the `resume` app - the job owner's own person if they've picked
  one in People (Settings), else the resume app's default person - asks
  Claude to tailor it to that job's stored JD text
  (reordering/trimming/rephrasing only - never inventing experience) plus
  write a cover letter, and stores the result on the job. The People
  section's "Resume" dropdown is populated live from the resume app itself
  (`GET /api/people/resume-people` here, proxying the resume app's own
  `GET /api/resume-people`) - time-management never stores or manages any
  resume content itself, that all lives in the resume app's own People
  admin page (a completely separate, browser-facing UI from this proxy -
  see the `resume` app's README). "Download PDF"/"Download DOCX" then
  render on demand through the `resume` app's own
  Jinja2/Playwright/python-docx pipeline (see `app/resume_gen.py` and the
  `resume` app's `app/render.py`/`app/admin.py`) - the output is styled
  like the real resume, not a plain-text dump. Regenerating overwrites the
  previous result for that job. See "Environment variables" above for what
  this needs configured; the
  `resume` app must be running and reachable for it to work.
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
  (most likely a lapsed Cloudflare Access session, which needs a real
  browser to re-authenticate), it falls back to opening the app instead of
  silently doing nothing.
- The backend (`app/`) is a plain JSON REST API; the frontend
  (`static/app.js`) is a thin vanilla-JS client (drag-and-drop via SortableJS)
  with no build step. That split is intentional so the frontend can later be
  swapped for something richer (e.g. React, or a native iOS app) without
  touching the API.
