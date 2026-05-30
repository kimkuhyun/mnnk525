import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { GROUP_COLOR } from '../lib/relations';
import { useTheme } from '../theme/ThemeContext';
import type { GraphData, RelationGroup } from '../types';

interface Props {
  data: GraphData;
  activeGroups: Set<RelationGroup>;
  minWeight: number;
  onSelectNode: (n: { id: string; name: string }) => void;
  onSelectEdge: (l: any) => void;
}

// 마인드맵 — 중심 회사 고정, 이웃이 방사. 노드=라벨 박스(라벨 안에), 크기=관계강도(연결 weight 합).
export default function GraphCanvas({ data, activeGroups, minWeight, onSelectNode, onSelectEdge }: Props) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setDims({ width: Math.floor(width), height: Math.floor(height) });
    });
    ro.observe(el);
    setDims({ width: el.clientWidth, height: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // 필터 + 노드별 관계강도(_w = 연결 엣지 weight 합) 를 원본 노드에 주입(참조 유지 → 위치 안정)
  const filtered = useMemo(() => {
    const links = (data.links as any[]).filter(
      (l) => activeGroups.has(l.group as RelationGroup) && (l.weight ?? 1) >= minWeight
    );
    const wsum: Record<string, number> = {};
    const connected = new Set<string>();
    links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      connected.add(s); connected.add(t);
      wsum[s] = (wsum[s] || 0) + (l.weight || 1);
      wsum[t] = (wsum[t] || 0) + (l.weight || 1);
    });
    (data.nodes as any[]).forEach((n) => { if (n.seed) connected.add(n.id); n._w = wsum[n.id] || 1; });
    return { nodes: (data.nodes as any[]).filter((n) => connected.has(n.id)), links };
  }, [data, activeGroups, minWeight]);

  const neighbourSet = useMemo<Set<string> | null>(() => {
    if (!hoveredId) return null;
    const s = new Set<string>([hoveredId]);
    filtered.links.forEach((l: any) => {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      if (src === hoveredId) s.add(tgt);
      if (tgt === hoveredId) s.add(src);
    });
    return s;
  }, [hoveredId, filtered.links]);

  // 로고 프리로드 (sz=128 고해상도)
  useEffect(() => {
    filtered.nodes.forEach((n: any) => {
      if (n.logo && !imgCache.current.has(n.logo)) {
        const img = new Image();
        img.onload = () => { imgCache.current.set(n.logo, img); fgRef.current?.refresh?.(); };
        img.onerror = () => imgCache.current.set(n.logo, img);
        img.src = n.logo;
        imgCache.current.set(n.logo, img);
      }
    });
  }, [filtered.nodes]);

  // 마인드맵 레이아웃: 중심 고정 + 적당한 반발/링크거리. (클러스터 force 제거)
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const seed = filtered.nodes.find((n: any) => n.seed);
    if (seed) { seed.fx = 0; seed.fy = 0; }
    fg.d3Force('charge')?.strength(-320);
    fg.d3Force('link')?.distance(95);
    fg.d3ReheatSimulation?.();
  }, [filtered]);

  // 관계강도 → 폰트/박스 배율 (선굵기 대신 노드크기로)
  const wScale = (n: any) => (n.seed ? 1.9 : Math.max(0.78, Math.min(1.5, 0.62 + Math.sqrt(n._w || 1) * 0.13)));

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D) => {
      const x: number = node.x ?? 0;
      const y: number = node.y ?? 0;
      const isSeed = !!node.seed;
      const accent = isSeed ? (isDark ? '#e2e8f0' : '#334155') : (GROUP_COLOR[node.group as RelationGroup] ?? '#94a3b8');
      const isHovered = hoveredId === node.id;
      const isNbr = !!neighbourSet?.has(node.id);
      const dimmed = hoveredId !== null && !isHovered && !isNbr;

      const FS = 5 * wScale(node); // 그래프 좌표 폰트 (줌과 함께 스케일)
      ctx.font = `${isSeed ? 700 : 500} ${FS}px system-ui, sans-serif`;
      const label = (node.name ?? node.id ?? '') as string;
      const tw = ctx.measureText(label).width;

      const img = node.logo ? imgCache.current.get(node.logo) : undefined;
      const logoReady = !!(img && img.complete && img.naturalWidth > 0);
      const logoSz = logoReady ? FS * 1.25 : 0;
      const padX = FS * 0.7, padY = FS * 0.5, gap = logoReady ? FS * 0.45 : 0;
      const boxW = tw + logoSz + gap + padX * 2;
      const boxH = Math.max(FS, logoSz) + padY * 2;
      node.__bw = boxW; node.__bh = boxH; // 클릭영역용

      ctx.save();
      ctx.globalAlpha = dimmed ? 0.18 : 1;

      // 박스
      ctx.beginPath();
      (ctx as any).roundRect(x - boxW / 2, y - boxH / 2, boxW, boxH, boxH * 0.32);
      ctx.fillStyle = isDark ? '#1e293b' : '#ffffff';
      ctx.fill();
      ctx.strokeStyle = isHovered ? '#3b82f6' : accent;
      ctx.lineWidth = (isSeed ? 1.4 : 0.9) * (isHovered ? 1.8 : 1);
      ctx.stroke();

      // 내용: 로고(원형) + 라벨, 박스 안에 좌측정렬
      let cx = x - boxW / 2 + padX;
      if (logoReady) {
        const lr = logoSz / 2;
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx + lr, y, lr, 0, 2 * Math.PI);
        ctx.clip();
        ctx.drawImage(img as HTMLImageElement, cx, y - lr, logoSz, logoSz);
        ctx.restore();
        cx += logoSz + gap;
      }
      ctx.fillStyle = isDark ? '#f1f5f9' : '#1e293b';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cx, y);
      ctx.restore();
    },
    [isDark, hoveredId, neighbourSet]
  );

  const nodePointerAreaPaint = useCallback((node: any, color: string, ctx: CanvasRenderingContext2D) => {
    const bw = node.__bw || 40, bh = node.__bh || 18;
    ctx.fillStyle = color;
    ctx.fillRect((node.x ?? 0) - bw / 2, (node.y ?? 0) - bh / 2, bw, bh);
  }, []);

  // 엣지: 균일 가는 선 (강도는 노드크기로 옮김)
  const linkColor = useCallback(
    (l: any): string => {
      const base = GROUP_COLOR[l.group as RelationGroup] ?? '#94a3b8';
      if (hoveredId === null) return base + 'aa';
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      return src === hoveredId || tgt === hoveredId ? base + 'ee' : base + '14';
    },
    [hoveredId]
  );

  const bgColor = isDark ? '#0f172a' : '#f8fafc';

  if (filtered.nodes.length === 0) {
    return (
      <div ref={containerRef} className="absolute inset-0 flex items-center justify-center" style={{ background: bgColor }}>
        <span className="text-sm text-slate-400 dark:text-slate-500">관계 데이터 연결 시 표시됩니다</span>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="absolute inset-0 overflow-hidden" style={{ background: bgColor }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={filtered as any}
        width={dims.width}
        height={dims.height}
        backgroundColor={bgColor}
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={() => 'replace'}
        nodePointerAreaPaint={nodePointerAreaPaint}
        linkColor={linkColor as any}
        linkWidth={() => 1.2}
        linkDirectionalArrowLength={(l: any) => (l.directed ? 3 : 0)}
        linkDirectionalArrowRelPos={1}
        onNodeHover={(n: any) => setHoveredId(n ? n.id : null)}
        onNodeClick={(n: any) => onSelectNode({ id: n.id, name: n.name })}
        onLinkClick={(l: any) => onSelectEdge(l)}
        cooldownTicks={120}
        onEngineStop={() => fgRef.current?.zoomToFit?.(500, 60)}
        d3AlphaDecay={0.028}
        d3VelocityDecay={0.4}
        enableNodeDrag
      />
    </div>
  );
}
