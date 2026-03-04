# Stock Prediction Dashboard

주식 데이터를 기반으로 단기 및 중장기 주가 예측 결과를 시각화하는 웹 대시보드입니다.
FastAPI 백엔드와 React 프론트엔드를 통해 예측 결과를 조회하고 차트로 확인할 수 있습니다.

---

# Project Structure

```
web/
│
├── backend/
│   ├── core/
│   ├── db/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── __init__.py
│   ├── main.py
│   ├── requirements.txt
│   └── database.db
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PredictionChart.tsx
│   │   │   ├── PredictionDetailPage.tsx
│   │   │   └── StockSidebar.tsx
│   │   ├── styles/
│   │   ├── App.tsx
│   │   └── main.tsx
│   │
│   ├── index.html
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```

---

# Tech Stack

## Frontend

* React
* TypeScript
* Vite
* TailwindCSS
* Recharts

## Backend

* FastAPI
* Python
* Pandas / NumPy

---

# Backend Setup

backend 디렉토리로 이동

```
cd backend
```

가상환경 생성

```
python -m venv .venv
```

가상환경 실행 (Windows)

```
.venv\Scripts\activate
```

패키지 설치

```
pip install -r requirements.txt
```

서버 실행

```
uvicorn main:app --reload
```

API 문서

```
http://127.0.0.1:8000/docs
```

---

# Frontend Setup

frontend 디렉토리로 이동

```
cd frontend
```

패키지 설치

```
npm install
```

개발 서버 실행

```
npm run dev
```

접속

```
http://localhost:5173
```

---

# API Example

단기 예측 조회

```
GET /api/predictions/short?code=005930
```

Response

```
{
  "data": [
    {
      "date": "2026-03-01",
      "price": 72000
    }
  ],
  "confidence": 0.82
}
```

---

# Roadmap

Backend

* 주가 데이터 수집 자동화
* 예측 모델 학습 파이프라인 구축
* MySQL 데이터베이스 연동

Frontend

* 종목 검색 기능 개선
* 차트 UI 개선
* 로딩 및 에러 처리 개선

DevOps

* Docker 환경 구성
* CI/CD 파이프라인 구축
