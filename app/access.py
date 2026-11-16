"""Who may use this app: its administrators, and nobody else.

The app has no accounts of its own; it used to rely wholly on Cloudflare Access in front of it. Now it signs in
through the shared front door (the dashboard), and shared_python.owner_gate wraps the whole app, so every page,
API route and file refuses anyone but an administrator.

Nothing else calls this app (it calls the resume app, not the other way round), so there is no machine-to-machine
exception. Three files are public because a browser fetches them with no cookie and they hold nothing private:
the installable-app manifest, the icons, and the push-notification service worker (a service worker script that
redirects to a login page is refused by the browser, which would break push for a signed-out device)."""
from shared_python import owner_gate

from . import config

PUBLIC_PATHS = ("/manifest.json", "/icons/", "/sw.js")


def install(app) -> None:
    owner_gate.install(
        app,
        admin_emails=lambda: config.ADMIN_EMAILS,
        dev_user_email=config.DEV_USER_EMAIL,
        public_paths=PUBLIC_PATHS,
    )
