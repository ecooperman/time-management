"""
Web Push sending, and the VAPID keypair this app uses to identify itself
to push services (Apple's, Google's, etc.) - not a secret issued by or
shared with anyone else, unlike ANTHROPIC_API_KEY/INTERNAL_API_TOKEN, so
there's no external account it has to match. Generate once:

    python -m app.push generate-vapid-keys

then set VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY from the printed output (see
app/config.py). Both are stored in the same compact base64url "raw" point
form - a single line each, so they drop straight into a systemd
Environment= line with no PEM/newline awkwardness. VAPID_PUBLIC_KEY is
also literally the applicationServerKey the frontend hands to
pushManager.subscribe() - same string, two consumers.
"""
import base64
import json
import sys

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from . import config, crud


def generate_vapid_keys() -> None:
    """One-time setup helper - see module docstring. Prints both keys in
    the compact form config.py expects; nothing is written to disk."""
    vapid = Vapid02()
    vapid.generate_keys()

    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    private_b64url = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()

    public_raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64url = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()

    print(f"VAPID_PRIVATE_KEY={private_b64url}")
    print(f"VAPID_PUBLIC_KEY={public_b64url}")


def _vapid_private_key() -> Vapid02:
    if not config.VAPID_PRIVATE_KEY:
        raise RuntimeError(
            "VAPID_PRIVATE_KEY is not set - run `python -m app.push generate-vapid-keys` "
            "once and set it (see README.md)."
        )
    return Vapid02.from_raw(config.VAPID_PRIVATE_KEY.encode())


def send_push_to_all(db: Session, title: str, body: str, url: str = "/") -> None:
    """Sends one push message to every subscribed device. A subscription
    that comes back 404/410 (Gone) means the browser dropped it - the
    user uninstalled the PWA, cleared data, or revoked permission - so we
    delete it rather than let it fail forever on every future send."""
    subscriptions = crud.get_push_subscriptions(db)
    if not subscriptions:
        return

    vapid_private_key = _vapid_private_key()
    payload = {"title": title, "body": body, "url": url}

    for sub in subscriptions:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": config.VAPID_SUBJECT},
            )
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                crud.delete_push_subscription_by_endpoint(db, sub.endpoint)
            else:
                print(f"push to {sub.endpoint[:60]}... failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "generate-vapid-keys":
        generate_vapid_keys()
    else:
        print("Usage: python -m app.push generate-vapid-keys", file=sys.stderr)
        sys.exit(1)
