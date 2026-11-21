"""Who may use this app, and whose data they see.

Several people can have an account, each with completely private tasks and reminders. The app has no accounts of
its own to check against until someone is let in (default-deny): an administrator adds a person on the Users page,
or, for an administrator, the account is made on their first sign-in (taking over the data that existed before accounts).

shared_python.accounts_gate wraps the WHOLE app: every page, API route and file refuses anyone without an account,
and runs each request inside that person's scope, so every database read and write is filtered to them below the
routes' own code (shared_python.owned). Only an administrator may let people in (the Users page).

Nothing calls this app, so there is no machine-to-machine exception. Three files are public because a browser fetches them with no cookie and they hold nothing private:
the installable-app manifest, the icons, and the push-notification service worker (a service worker script that
redirects to a login page is refused by the browser, which would break push for a signed-out device)."""
from typing import Union

from shared_python import accounts_gate, usage
from shared_python.accounts_gate import Account

from . import config, crud, models
from .database import SessionLocal

PUBLIC_PATHS = ("/manifest.json", "/icons/", "/sw.js")
seen = usage.LastSeen(SessionLocal)  # when each person was last here, for the dashboard's stats pages


def account_for(email: str) -> Union[Account, str]:
    """This person's account in the app: administrators always have one (made on first sign-in), anyone else only
    if an administrator let them in and has not since removed them."""
    is_admin = email in config.ADMIN_EMAILS
    with SessionLocal() as db:
        user = crud.get_user_by_email(db, email)
        if user is None:
            if not is_admin:
                return "none"
            user = crud.adopt_or_create_admin(db, email)
        if user.status != models.USER_ACTIVE and not is_admin:
            return "removed"
        return Account(id=user.id, email=user.email, is_admin=is_admin)


def install(app) -> None:
    accounts_gate.install(
        app,
        account_for=account_for,
        dev_user_email=config.DEV_USER_EMAIL,
        public_paths=PUBLIC_PATHS,
        seen=seen,
    )
