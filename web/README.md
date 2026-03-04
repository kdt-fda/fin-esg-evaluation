# prediction-web

React + Vite + TypeScript 기반 웹 UI 프로젝트입니다.  
(예: 주가 예측 차트/근거 팝업/상세 모달 UI)

## 요구 사항
- Node.js 18 이상 권장
- npm 사용

## 설치 및 실행
```bash
# 의존성 설치
npm install

# 개발 서버 실행
npm run dev

```

## 프로젝트 구조
```
test-web/
├─ public/                 # 정적 파일 (그대로 배포됨)
│  └─ vite.svg
│
├─ src/
│  ├─ components/          # UI 컴포넌트 모음
│  │  ├─ PredictionChart.tsx
│  │  ├─ PredictionDetailPage.tsx
│  │  └─ StockSidebar.tsx
│  │
│  ├─ styles/              # 전역 스타일
│  │  ├─ index.css
│  │  ├─ tailwind.css
│  │  └─ theme.css
│  │
│  ├─ App.tsx              # 전체 화면 구성 (최상위 컴포넌트)
│  └─ main.tsx             # React 시작점 (root에 App 마운트)
│
├─ index.html              # 브라우저 진입점
├─ vite.config.ts          # Vite 설정 파일
├─ tsconfig.json           # TypeScript 기본 설정
├─ package.json            # 프로젝트 설정 및 의존성 목록
└─ package-lock.json       # 정확한 의존성 버전 기록
```