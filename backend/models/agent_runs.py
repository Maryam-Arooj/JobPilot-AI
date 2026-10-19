from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from ..db.database import Base


class AgentRun(Base):
    """One execution of an agent task (CV, Job or Email agent), shown on the live dashboard.

    tool_calls / logs / events are JSON lists in the shape of the frontend contract
    (frontend/src/features/agent-transparency/types.ts). Everything stored is sanitised
    by services/agent_runs.py: no API keys, tokens or full documents.
    """

    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent = Column(String(16), nullable=False, index=True)  # cv | job | email
    task = Column(String(300), nullable=False)
    status = Column(String(16), nullable=False, default="running", index=True)  # running | success | failed | pending | waiting
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    current_step = Column(JSON, nullable=True)
    input_summary = Column(JSON, nullable=True)
    output_summary = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    logs = Column(JSON, nullable=True)
    events = Column(JSON, nullable=True)
