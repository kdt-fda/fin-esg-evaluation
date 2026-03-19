from pydantic import BaseModel
from typing import List, Optional

class PredictionReason(BaseModel):
    factor: str
    impact: str
    contribution: Optional[float] = None

class ChartDataPoint(BaseModel):
    date: str
    actual: Optional[float] = None
    predicted: Optional[float] = None
    reason: Optional[List[PredictionReason]] = None
    changeReason: Optional[str] = None

class PredictionResponse(BaseModel):
    confidence: float
    data: List[ChartDataPoint]
    pastCount: Optional[int] = None