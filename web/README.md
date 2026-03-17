
# Running with Docker (Recommended)

Docker를 사용하면 Frontend + Backend를 한 번에 실행할 수 있습니다.


### 프로젝트 루트에서 실행

```
docker compose up --build
```

### 접속

#### Frontend
```
http://localhost:5173
```

#### Backend API
```
http://localhost:8000
```

#### Swagger API Docs
```
http://localhost:8000/docs
```

---

# Running Without Docker (Optional)

Docker 없이 로컬에서 직접 실행하는 방법입니다.

## Backend Setup

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

## Frontend Setup

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