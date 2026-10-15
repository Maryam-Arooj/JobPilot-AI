from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from ..db.database import Base

class ProfileFactHistory(Base):
    __tablename__ = "profile_fact_history"
    id = Column(Integer, primary_key=True)
    fact_id = Column(Integer, ForeignKey("profile_facts.id"))
    old_value = Column(String)
    new_value = Column(String)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_reason = Column(String)
    changed_by = Column(String)
