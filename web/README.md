# Stock Prediction Dashboard

주식 데이터를 기반으로 단기 및 중장기 주가 예측 결과를 시각화하는 웹 대시보드입니다.  
FastAPI 백엔드와 React 프론트엔드를 통해 예측 결과를 조회하고 차트로 확인할 수 있습니다.

Docker를 통해 Frontend + Backend를 한 번에 실행할 수 있습니다.

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
│   ├── Dockerfile.backend
│   └── .dockerignore
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
│   ├── vite.config.ts
│   ├── Dockerfile.frontend
│   └── .dockerignore
│
├── docker-compose.yml
└── README.md
```

---

# Tech Stack

## Frontend

- React  
- TypeScript  
- Vite  
- TailwindCSS  
- Recharts  

## Backend

- FastAPI  
- Python  
- SQLAlchemy  
- Pandas / NumPy  

## DevOps

- Docker  
- Docker Compose  

---

# Running the Project (Recommended: Docker)

Docker를 사용하면 Frontend + Backend를 한 번에 실행할 수 있습니다.

## Docker Desktop 실행

Docker Desktop이 실행 중인지 확인합니다.

## 프로젝트 루트에서 실행

```
docker compose up --build
```

## 접속

### Frontend
```
http://localhost:5173
```

### Backend API
```
http://localhost:8000
```

### Swagger API Docs
```
http://localhost:8000/docs
```

---

# Running Without Docker (Optional)

Docker 없이 로컬에서 직접 실행하는 방법입니다.

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