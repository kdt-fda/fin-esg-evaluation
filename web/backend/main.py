from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers.stocks import router as stocks_router
from routers.predictions import router as predictions_router

app = FastAPI(
    title="Stock Prediction API",
    description="API for serving stock data and predictions",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 설정
allowed_origins = settings.allowed_origins_list()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(stocks_router, prefix=settings.API_PREFIX)
app.include_router(predictions_router, prefix=settings.API_PREFIX)

# 헬스 체크(디버깅에 유용)
@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)