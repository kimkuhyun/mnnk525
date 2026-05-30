# POLARIS Frontend (React + Vite + TS)

## 로컬 실행
```powershell
cd frontend
copy .env.example .env
npm install
npm run dev        # → http://localhost:5173  (/api 는 vite proxy 로 :8000 백엔드 전달)
```
백엔드(`../backend`)도 `uvicorn app.main:app --reload` 로 같이 띄워야 데이터가 옵니다.

## 구조
```
src/
├─ main.tsx              엔트리 (BrowserRouter)
├─ App.tsx               라우팅 (6페이지)
├─ index.css            전역 스타일 (흰/파랑)
├─ api/client.ts        백엔드 호출 래퍼 api()
├─ components/Layout.tsx 상단바 + 사이드바 (네비)
└─ pages/               Dashboard / Workbench / Ask / Patents / Signals / Evidence
```

## 화면 작업
`web/*.html` 와이어프레임을 각 `pages/*.tsx` 로 옮기면 됩니다. 스타일은 Tailwind CDN(이미 index.html).
데이터는 `api('/...')` 로 백엔드 호출. (운영 빌드 시 Tailwind CDN → postcss 빌드통합 권장)
