import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            // 개발 중 /api → 백엔드(FastAPI). CORS 신경 안 써도 됨.
            '/api': 'http://localhost:8000',
        },
    },
});
