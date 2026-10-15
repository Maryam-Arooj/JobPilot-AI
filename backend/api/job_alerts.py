from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..services.auth_middleware import get_current_user_id
from ..models.applications import JobAlert
from pydantic import BaseModel

router = APIRouter(prefix="/job-alerts", tags=["job-alerts"])

class AlertIn(BaseModel):
    query: str
    filters: dict = {}
    frequency: str = "daily"

@router.post("/")
def create_alert(a: AlertIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    alert = JobAlert(user_id=user_id, query=a.query, filters=a.filters, frequency=a.frequency)
    db.add(alert)
    db.commit()
    return {"id": alert.id}

@router.get("/")
def list_alerts(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    alerts = db.query(JobAlert).filter(JobAlert.user_id == user_id).all()
    return [{"id": al.id, "query": al.query, "frequency": al.frequency} for al in alerts]
