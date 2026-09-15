import React, { useMemo, useState } from 'react';

export interface DepthSample {
  depth: number;
  temperature?: number;
  salinity?: number;
  chlorophyll?: number;
}

export interface ProfileChartProps {
  data: DepthSample[];
  activeDepth?: number;
  maxDepth?: number;
  width?: number;
  height?: number;
}

export const VerticalColumnProfileChart: React.FC<ProfileChartProps> = ({
  data = [],
  activeDepth = 0,
  maxDepth = 454,
  width = 280,
  height = 180
}) => {
  const [filter, setFilter] = useState<'all' | 'temp' | 'sal' | 'chl'>('all');

  const padding = { top: 12, right: 16, bottom: 20, left: 34 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  // 1. Sort strictly by ascending depth and constrain to maxDepth
  const sortedData = useMemo(() => {
    return [...data]
      .filter(d => d.depth <= maxDepth * 1.001)
      .sort((a, b) => a.depth - b.depth);
  }, [data, maxDepth]);

  // 2. Compute dynamic variable bounds
  const bounds = useMemo(() => {
    const temps = sortedData.map(d => d.temperature).filter((v): v is number => v !== undefined && !isNaN(v));
    const sals = sortedData.map(d => d.salinity).filter((v): v is number => v !== undefined && !isNaN(v));
    const chls = sortedData.map(d => d.chlorophyll).filter((v): v is number => v !== undefined && !isNaN(v));

    return {
      tMin: temps.length ? Math.min(...temps) : 10,
      tMax: temps.length ? Math.max(...temps) : 30,
      sMin: sals.length ? Math.min(...sals) : 33,
      sMax: sals.length ? Math.max(...sals) : 37,
      cMin: chls.length ? Math.min(...chls) : 0.01,
      cMax: chls.length ? Math.max(...chls) : 2.0
    };
  }, [sortedData]);

  // 3. SVG Path Generator
  const generatePath = (accessor: (d: DepthSample) => number | undefined, minVal: number, maxVal: number) => {
    const points: [number, number][] = [];
    const span = Math.max(0.0001, maxVal - minVal);

    sortedData.forEach((d) => {
      const val = accessor(d);
      if (val === undefined || isNaN(val)) return;

      const normX = Math.max(0, Math.min(1, (val - minVal) / span));
      const normY = Math.max(0, Math.min(1, d.depth / maxDepth));

      const x = padding.left + normX * innerWidth;
      const y = padding.top + normY * innerHeight;
      points.push([x, y]);
    });

    if (points.length < 2) return '';
    return points.reduce((acc, [x, y], idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)},${y.toFixed(1)}`, '');
  };

  const tempPath = useMemo(() => generatePath(d => d.temperature, bounds.tMin, bounds.tMax), [sortedData, bounds]);
  const salPath = useMemo(() => generatePath(d => d.salinity, bounds.sMin, bounds.sMax), [sortedData, bounds]);
  const chlPath = useMemo(() => generatePath(d => d.chlorophyll, bounds.cMin, bounds.cMax), [sortedData, bounds]);

  // Active sampled depth line
  const activeY = padding.top + Math.min(1, Math.max(0, activeDepth / maxDepth)) * innerHeight;

  return (
    <div className="flex flex-col gap-2 select-none">
      {/* Header & Filter Tabs */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
          Vertical Column Profile
        </span>
        <div className="flex bg-slate-900 border border-slate-800 rounded-md p-0.5 text-[10px]">
          {(['all', 'temp', 'sal', 'chl'] as const).map((key) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`px-2 py-0.5 rounded capitalize font-mono transition-all ${
                filter === key
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {key === 'temp' ? 'Temp' : key === 'sal' ? 'Sal' : key === 'chl' ? 'Chl' : 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* SVG Coordinate Grid */}
      <div className="relative bg-slate-950/80 border border-slate-800/80 rounded-lg p-1">
        <svg width={width} height={height} className="overflow-visible">
          {/* Depth Horizontal Grid Lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padding.top + ratio * innerHeight;
            const depthLabel = Math.round(ratio * maxDepth);
            return (
              <g key={ratio}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={padding.left + innerWidth}
                  y2={y}
                  stroke="#1e293b"
                  strokeDasharray="3 3"
                />
                <text
                  x={padding.left - 6}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-slate-500 text-[9px] font-mono"
                >
                  {depthLabel}m
                </text>
              </g>
            );
          })}

          {/* Active Depth Slice Marker Line */}
          {activeDepth > 0 && (
            <g>
              <line
                x1={padding.left}
                y1={activeY}
                x2={padding.left + innerWidth}
                y2={activeY}
                stroke="#ef4444"
                strokeWidth={1.5}
                strokeDasharray="4 4"
              />
              <circle cx={padding.left} cy={activeY} r={3} fill="#ef4444" />
              <rect
                x={padding.left + 6}
                y={activeY - 9}
                width={78}
                height={15}
                rx={3}
                fill="#0f172a"
                stroke="#ef4444"
                strokeWidth={0.8}
              />
              <text
                x={padding.left + 10}
                y={activeY + 2}
                className="fill-red-300 text-[9px] font-mono font-bold"
              >
                Depth: {activeDepth.toFixed(0)}m
              </text>
            </g>
          )}

          {/* Parameter Depth Curves */}
          {(filter === 'all' || filter === 'temp') && tempPath && (
            <path d={tempPath} fill="none" stroke="#f87171" strokeWidth={2} strokeLinecap="round" />
          )}
          {(filter === 'all' || filter === 'sal') && salPath && (
            <path d={salPath} fill="none" stroke="#38bdf8" strokeWidth={2} strokeLinecap="round" />
          )}
          {(filter === 'all' || filter === 'chl') && chlPath && (
            <path d={chlPath} fill="none" stroke="#34d399" strokeWidth={2} strokeLinecap="round" />
          )}
        </svg>

        {/* Legend Footer */}
        <div className="flex items-center justify-center gap-4 pt-1 pb-1 border-t border-slate-900 text-[10px] font-mono">
          {(filter === 'all' || filter === 'temp') && (
            <span className="flex items-center gap-1 text-red-400">
              <span className="w-2 h-0.5 bg-red-400 rounded" />
              Temp ({bounds.tMin.toFixed(1)}–{bounds.tMax.toFixed(1)}°C)
            </span>
          )}
          {(filter === 'all' || filter === 'sal') && (
            <span className="flex items-center gap-1 text-sky-400">
              <span className="w-2 h-0.5 bg-sky-400 rounded" />
              Sal ({bounds.sMin.toFixed(1)}–{bounds.sMax.toFixed(1)})
            </span>
          )}
          {(filter === 'all' || filter === 'chl') && (
            <span className="flex items-center gap-1 text-emerald-400">
              <span className="w-2 h-0.5 bg-emerald-400 rounded" />
              Chl ({bounds.cMin.toFixed(2)}–{bounds.cMax.toFixed(2)})
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerticalColumnProfileChart;
