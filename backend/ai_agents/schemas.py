from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

class ExtractedFact(BaseModel):
    path: str
    value: Union[str, List[Any], Dict[str, Any]]
    confidence: float = 0.95
    verified: bool = True
    source: str = "agent"
    note: Optional[str] = None

class ProfileExtractionResult(BaseModel):
    facts: List[ExtractedFact]
    missing_fields: List[str]
    followup_questions: List[str]
