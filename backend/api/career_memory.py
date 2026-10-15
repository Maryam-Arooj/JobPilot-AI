from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..services.auth_middleware import get_current_user_id
from ..models.applications import CareerMemory
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/career-memory", tags=["career-memory"])

class MemoryIn(BaseModel):
    memory_type: str
    content: str
    tags: List[str] = []

@router.post("/")
def store_memory(mem: MemoryIn, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    m = CareerMemory(user_id=user_id, memory_type=mem.memory_type, content=mem.content, tags=mem.tags)
    db.add(m)
    db.commit()
    return {"id": m.id}

@router.get("/")
def list_memories(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    mems = db.query(CareerMemory).filter(CareerMemory.user_id == user_id).all()
    return [{"id": m.id, "type": m.memory_type, "content": m.content} for m in mems]
