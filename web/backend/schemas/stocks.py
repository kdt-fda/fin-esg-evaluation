from pydantic import BaseModel

class StockItem(BaseModel):
    code: str
    name: str
    sector: str | None = None
    sector_code: str | None = None
    is_active: bool | None = None


class StockPricePoint(BaseModel):
    date: str
    actual: float | None = None