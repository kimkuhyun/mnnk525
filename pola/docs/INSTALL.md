# INSTALL

GPU 백엔드를 자기 환경에 맞춰 1개만 선택해서 설치합니다.

## 1. 공통 (모든 환경)

```bash
git clone https://github.com/polaris/polaris-rag
cd polaris-rag
cp .env.example .env       # 비밀·포트·회사 목록 (필요시 수정)
docker compose -f docker/docker-compose.yml up -d   # Qdrant + MariaDB + Neo4j 기동
```

## 2. Python 의존성 + GPU 백엔드

### NVIDIA (CUDA)
```bash
pip install -e .[cuda]
```

### Windows + AMD GPU (DirectML)
```bash
pip install -e .[directml]
```
torch 2.4 + torch-directml. RX 6000/7000 시리즈 모두 가속.

### Linux + AMD GPU (ROCm)
```bash
pip install -e .[rocm] --index-url https://download.pytorch.org/whl/rocm6.2
```
RX 7800/7900 시리즈 + Linux/WSL2. ROCm 6.4.1+ 공식 지원.

### CPU only (GPU 없음)
```bash
pip install -e .[cpu]
```
검색은 동작. rerank (bge-reranker-v2-m3) 만 느림 (200쿼리×50청크 ≈ 10분).

## 3. Ollama (임베딩 + LLM)
호스트에 별도 설치 또는 외부 GPU (SSH 등) 서버 사용. `.env` 의 `OLLAMA_BASE` 가 그 호스트 가리키도록.
```bash
ollama pull bge-m3:latest         # 임베딩 (1024d)
ollama pull qwen3.5:9b            # LLM 기본값 (가벼움, 단일 GPU OK)
# 더 큰 모델 쓰려면 환경변수만 변경
# OLLAMA_LLM_MODEL=qwen3.6:27b  / llama3.3:70b  등 — 코드 변경 X
```

## 4. 동작 검증
```bash
polaris verify              # 3DB 적재 정합 8/8
polaris eval                # 벡터 검색 6/6 PASS 기대
polaris graph-eval          # 그래프 Cypher F1=1.0 기대
```

## 자주 묻는 문제

- **Qdrant client version 경고**: server 1.12 / client 1.18 호환. 무시 가능.
- **transformers 5.x 에러**: `pip install "transformers>=4.45,<5.0"` (torch 2.4 와 호환성)
- **Windows 콘솔 한글 깨짐**: `set PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING="utf-8"`)
- **AMD 7800XT Windows native ROCm**: 미지원. **directml** 또는 **WSL2 + ROCm** 권장.
