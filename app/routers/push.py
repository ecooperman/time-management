from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key")
def get_vapid_public_key():
    if not config.VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications are not configured yet")
    return {"key": config.VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(subscription: schemas.PushSubscriptionCreate, db: Session = Depends(get_db)):
    crud.upsert_push_subscription(db, subscription)
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: schemas.PushUnsubscribeRequest, db: Session = Depends(get_db)):
    crud.delete_push_subscription_by_endpoint(db, body.endpoint)
    return {"ok": True}
