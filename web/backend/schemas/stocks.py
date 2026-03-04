from pydantic import BaseModel

class StockItem(BaseModel):
    code: str
    name: str
    sector: str | None = None  # 지금은 없을 수 있으니 optional