import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { GROUP_COLOR } from '../lib/relations';
import { useTheme } from '../theme/ThemeContext';
import type { GraphData, RelationGroup } from '../types';

interface Props {
  data: GraphData;
  activeGroups: Set<RelationGroup>;
  minWeight: number;
  selectedId: string | null;
  onSelect: (node: { id: string; name: string }) => void;
  onSelectEdge: (l: any) => void;
  onExpandMeta: (metaKind: string) => void;
  // 하위 호환: 기존 onSelectNode 도 받을 수 있도록
  onSelectNode?: (n: { id: string; name: string }) => void;
}

// 마인드맵 — 중심 회사 고정, 이웃이 방사. 노드=라벨 박스(라벨 안에), 크기=관계강도(연결 weight 합).
// meta 노드: 점선 테두리 + "(N)" 카운트 표시. 클릭 시 onExpandMeta 호출.
// selectedId: 파랑 링으로 강조. hover-dim 유지.
export default function GraphCanvas({
  data,
  activeGroups,
  minWeight,
  selectedId,
  onSelect,
  onSelectEdge,
  onExpandMeta,
  onSelectNode,
}: Props) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 800, height: 600 });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());
  // 사용자가 줌/팬 제스처를 취한 뒤에는 auto zoomToFit 을 막는 플래그
  const userInteracted = useRef(false);

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
    // meta 노드는 연결 없어도 항상 포함 (seed도 마찬가지)
    (data.nodes as any[]).forEach((n) => {
      if (n.seed || n.kind === 'meta') connected.add(n.id);
      n._w = wsum[n.id] || 1;
    });
    const nodes = (data.nodes as any[]).filter((n) => connected.has(n.id));

    // 결정론적 마인드맵 배치(force 클러스터 X): 중심 고정 + 관계그룹별 섹터 링.
    // fx/fy 를 노드 객체에 미리 박아 force-graph 가 받기 전에 위치 확정 → 타이밍 의존 제거.
    const seed = nodes.find((n) => n.seed);
    if (seed) { seed.fx = 0; seed.fy = 0; seed.x = 0; seed.y = 0; }
    const ORDER = ['compete', 'supply', 'partner', 'invest', 'dispute', 'govern'];
    const byGroup = new Map<string, any[]>();
    for (const n of nodes) {
      if (n.seed) continue;
      const g = (n.group as string) || 'etc';
      if (!byGroup.has(g)) byGroup.set(g, []);
      byGroup.get(g)!.push(n);
    }
    for (const arr of byGroup.values()) arr.sort((a, b) => (b._w || 1) - (a._w || 1));
    const present = [
      ...ORDER.filter((g) => byGroup.has(g)),
      ...[...byGroup.keys()].filter((g) => !ORDER.includes(g)),
    ];
    const G = present.length || 1;
    const TAU = Math.PI * 2;
    present.forEach((g, gi) => {
      const arr = byGroup.get(g)!;
      const mid = -Math.PI / 2 + ((gi + 0.5) / G) * TAU; // 12시부터 시계방향
      const wedge = (TAU / G) * 0.78;
      const m = arr.length;
      const perRing = Math.max(3, Math.ceil(Math.sqrt(m * 1.6)));
      arr.forEach((n, j) => {
        const ring = Math.floor(j / perRing);
        const rs = ring * perRing;
        const rc = Math.min(perRing, m - rs);
        const idx = j - rs;
        const r = 160 + ring * 100;
        const a = rc === 1 ? mid : mid - wedge / 2 + (idx / (rc - 1)) * wedge;
        n.fx = Math.cos(a) * r; n.fy = Math.sin(a) * r;
        n.x = n.fx; n.y = n.fy;
      });
    });
    // 댕글링 링크 제거: 양끝이 실제 노드에 있는 엣지만 (meta collapse/patch 실패 시 크래시 방지)
    const _nodeIds = new Set(nodes.map((n: any) => n.id));
    const safeLinks = links.filter((l: any) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      return _nodeIds.has(s) && _nodeIds.has(t);
    });
    return { nodes, links: safeLinks };
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

  // 데이터(filtered) 변경 시 → 새 그래프이므로 인터랙션 플래그 리셋 후 fit 1회.
  useEffect(() => {
    userInteracted.current = false;
    const fg = fgRef.current;
    if (!fg || filtered.nodes.length === 0) return;
    fg.d3ReheatSimulation?.();
    const t = setTimeout(() => {
      if (!userInteracted.current) fg.zoomToFit?.(450, 70);
    }, 300);
    return () => clearTimeout(t);
  }, [filtered]);

  // 관계강도 → 폰트/박스 배율 (선굵기 대신 노드크기로)
  const wScale = (n: any) => (n.seed ? 1.9 : Math.max(0.78, Math.min(1.5, 0.62 + Math.sqrt(n._w || 1) * 0.13)));

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D) => {
      const x: number = node.x ?? 0;
      const y: number = node.y ?? 0;
      const isSeed = !!node.seed;
      const isMeta = node.kind === 'meta';
      const isSelected = selectedId !== null && node.id === selectedId;
      const accent = isSeed
        ? (isDark ? '#e2e8f0' : '#334155')
        : isMeta
        ? (isDark ? '#8E99A8' : '#8E99A8') // govern 계열 뮤트
        : (GROUP_COLOR[node.group as RelationGroup] ?? '#94a3b8');
      const isHovered = hoveredId === node.id;
      const isNbr = !!neighbourSet?.has(node.id);
      const dimmed = hoveredId !== null && !isHovered && !isNbr;

      const FS = 5 * wScale(node);
      ctx.font = `${isSeed ? 700 : 500} ${FS}px system-ui, sans-serif`;

      // meta 노드: 라벨에 카운트 포함
      const baseName = (node.name ?? node.id ?? '') as string;
      const label = isMeta && node.count != null ? `${baseName} (${node.count})` : baseName;
      const tw = ctx.measureText(label).width;

      const img = node.logo ? imgCache.current.get(node.logo) : undefined;
      const logoReady = !!(img && img.complete && img.naturalWidth > 0);
      const logoSz = logoReady ? FS * 1.25 : 0;
      const padX = FS * 0.7, padY = FS * 0.5, gap = logoReady ? FS * 0.45 : 0;
      const boxW = tw + logoSz + gap + padX * 2;
      const boxH = Math.max(FS, logoSz) + padY * 2;
      node.__bw = boxW; node.__bh = boxH;

      ctx.save();
      ctx.globalAlpha = dimmed ? 0.18 : 1;

      // 박스
      ctx.beginPath();
      (ctx as any).roundRect(x - boxW / 2, y - boxH / 2, boxW, boxH, boxH * 0.32);
      ctx.fillStyle = isDark ? '#1e293b' : '#ffffff';
      ctx.fill();

      if (isMeta) {
        // 점선 테두리
        ctx.save();
        ctx.setLineDash([3.5, 2.5]);
        ctx.strokeStyle = isSelected ? '#3b82f6' : isHovered ? '#3b82f6' : accent;
        ctx.lineWidth = isSelected ? 2.2 : (isHovered ? 1.8 : 1.1);
        ctx.beginPath();
        (ctx as any).roundRect(x - boxW / 2, y - boxH / 2, boxW, boxH, boxH * 0.32);
        ctx.stroke();
        ctx.restore();
      } else {
        // 실선 테두리
        // selectedId 강조: 파랑 링 (외부 링)
        if (isSelected) {
          ctx.save();
          ctx.beginPath();
          (ctx as any).roundRect(
            x - boxW / 2 - 3,
            y - boxH / 2 - 3,
            boxW + 6,
            boxH + 6,
            (boxH + 6) * 0.32
          );
          ctx.strokeStyle = '#3b82f6';
          ctx.lineWidth = 2.4;
          ctx.stroke();
          ctx.restore();
        }
        ctx.strokeStyle = isHovered ? '#3b82f6' : accent;
        ctx.lineWidth = (isSeed ? 1.4 : 0.9) * (isHovered ? 1.8 : 1);
        ctx.beginPath();
        (ctx as any).roundRect(x - boxW / 2, y - boxH / 2, boxW, boxH, boxH * 0.32);
        ctx.stroke();
      }

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
      ctx.fillStyle = isMeta
        ? (isDark ? '#94a3b8' : '#64748b') // meta는 뮤트 텍스트
        : (isDark ? '#f1f5f9' : '#1e293b');
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cx, y);
      ctx.restore();
    },
    [isDark, hoveredId, neighbourSet, selectedId]
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

  const handleNodeClick = useCallback(
    (n: any) => {
      if (n.kind === 'meta') {
        // meta 노드 클릭 = 펼치기 (group 또는 id 기반)
        const metaKind = n.group ?? n.id ?? 'govern';
        onExpandMeta(String(metaKind));
      } else {
        const payload = { id: n.id, name: n.name };
        onSelect(payload);
        onSelectNode?.(payload); // 하위 호환
      }
    },
    [onSelect, onSelectNode, onExpandMeta]
  );

  const bgColor = isDark ? '#0b1120' : '#eef2fb';

  // 단일 안정 컨테이너: empty-state ↔ canvas 가 같은 ref 박스 안에서 토글되어야
  // ResizeObserver 가 언마운트된 노드를 추적하는 폭=0 버그가 안 생긴다.
  return (
    <div ref={containerRef} className="absolute inset-0 overflow-hidden" style={{ background: bgColor }}>
      {filtered.nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm text-slate-400 dark:text-slate-500">관계 데이터 연결 시 표시됩니다</span>
        </div>
      ) : (
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
          linkCurvature={0.12}
          linkDirectionalArrowLength={(l: any) => (l.directed ? 3 : 0)}
          linkDirectionalArrowRelPos={1}
          onNodeHover={(n: any) => setHoveredId(n ? n.id : null)}
          onNodeClick={handleNodeClick}
          onLinkClick={(l: any) => onSelectEdge(l)}
          cooldownTicks={120}
          onEngineStop={() => {
            if (!userInteracted.current) fgRef.current?.zoomToFit?.(500, 60);
          }}
          onZoomEnd={() => { userInteracted.current = true; }}
          d3AlphaDecay={0.028}
          d3VelocityDecay={0.4}
          enableNodeDrag
        />
      )}
    </div>
  );
}
