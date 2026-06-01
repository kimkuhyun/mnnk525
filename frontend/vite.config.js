import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            // 개발 중 /api → 백엔드(FastAPI). CORS 신경 안 써도 됨.
            // localhost 는 IPv6(::1)로 풀려 WSL 포트포워딩과 충돌할 수 있어 127.0.0.1 고정.
            '/api': 'http://127.0.0.1:8000',
        },
    },
});
