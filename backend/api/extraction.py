from fastapi import APIRouter, Depends
from ..ai_agents.profile_agent import ProfileAgent
from ..services.auth_middleware import get_current_user_id

router = APIRouter(prefix="/extract", tags=["extraction"])
agent = ProfileAgent()

@router.post("/text")
def extract_text(payload: dict, user_id: int = Depends(get_current_user_id)):
    text = payload.get("text", "")
    result = agent.extract_from_text(text)
    return result
