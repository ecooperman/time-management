import os

HOST = "127.0.0.1"
PORT = 8010

# "local" (default, for `uvicorn app.main:app --reload` on a dev machine) or
# "production" (set once, droplet-wide, via systemd's DefaultEnvironment -
# see DEPLOYMENT.md - so every app inherits it with no per-service config).
# Drives which shared-assets host the app's templates point at, so
# switching between local iteration and the real deploy never means
# hand-editing a URL and remembering to revert it.
ENV = os.environ.get("APP_ENV", "local")
SHARED_ASSETS_BASE = "https://static.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8070"

# Where this app lives, for the links in the emails that tell people they have been let in.
PUBLIC_URL = "https://time.evancooperman.com" if ENV == "production" else f"http://{HOST}:{PORT}"

# Who is signed in (shared_python): only people with an account get in, each into their own private data (see
# app/access.py). ADMIN_EMAILS (comma-separated) comes from the shared secrets file on the droplet: they always have an
# account and are the only ones who can let others in. Locally the dev user is one, and is
# who every request is treated as.
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev@localhost.test").strip().lower()
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
if ENV != "production":
    ADMIN_EMAILS.add(DEV_USER_EMAIL)

# Task reminder push notifications (see app/push.py, app/reminders.py).
# The VAPID keypair is this app's own Web Push identity - not a secret
# issued by/shared with anyone else, so there's no external account it
# has to match. Generate once with
# `python -m app.push generate-vapid-keys`, then set these the same way as
# the rest (systemd env on the droplet, exported in your shell locally).
# VAPID_SUBJECT is a mailto: URI the push services use to contact you if
# your usage looks like a problem - required by the Web Push spec.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:evanjcooperman@gmail.com")
