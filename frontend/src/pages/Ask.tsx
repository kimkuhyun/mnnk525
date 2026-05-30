// 묻기 — web/ask.html 참고 (GraphRAG Q&A + 근거)
export default function Ask() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">POLARIS에게 묻기</h1>
      <p className="text-sm text-slate-500">web/ask.html 참고 · POST /api/ask (Qdrant→Neo4j→LLM)</p>
    </div>
  )
}
