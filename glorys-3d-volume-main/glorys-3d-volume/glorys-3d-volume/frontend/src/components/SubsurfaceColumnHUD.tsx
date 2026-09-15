import React, { useState } from "react";
import type { ProbeVariable, VerticalColumnResponse, VerticalColumnPoint } from "../types";
import { formatProbeValue } from "../utils/geoCoordinates";

interface SubsurfaceColumnHUDProps {
  data: VerticalColumnResponse | null;
  loading: boolean;
  activeVariable: ProbeVariable;
  onVariableChange: (variable: ProbeVariable) => void;
  onClose: () => void;
}

const W = 280;
const H = 220;
const PAD_L = 40;
const PAD_R = 18;
const PAD_T = 16;
const PAD_B = 26;

export default function SubsurfaceColumnHUD({
  data,
  loading,
  activeVariable,
  onVariableChange,
  onClose,
}: SubsurfaceColumnHUDProps) {
  const [hoverPoint, setHoverPoint] = useState<VerticalColumnPoint | null>(null);

  if (!loading && !data) return null;

  if (data?.is_land) {
    return (
      <div
        className="glass-panel"
        style={{
          width: W,
          padding: "16px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          borderRadius: 8,
          background: "rgba(10, 15, 26, 0.94)",
          border: "1px solid rgba(245, 158, 11, 0.5)",
          color: "#f59e0b",
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.6)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <span>⚠️</span>
            <span>Terrestrial Landmass</span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            ✕
          </button>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4 }}>
          {data.message || "Oceanographic profile unavailable for continental land coordinates."}
        </div>
        <div style={{ fontSize: 10, color: "#94a3b8", fontFamily: "var(--font-mono)" }}>
          Lat: {data.lat.toFixed(2)}° | Lon: {data.lon.toFixed(2)}°
        </div>
      </div>
    );
  }

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;

  // Compute domain bounds for active variable
  let vMin = 0;
  let vMax = 1;
  let dMax = 1000;
  let points: { x: number; y: number; pt: VerticalColumnPoint }[] = [];
  let pathD = "";

  if (data && data.profile.length > 0) {
    const vals = data.profile.map((p) => p[activeVariable]);
    vMin = Math.min(...vals);
    vMax = Math.max(...vals);

    // Padding for visual appeal
    if (vMin === vMax) {
      vMin -= 1;
      vMax += 1;
    } else {
      const span = vMax - vMin;
      vMin -= span * 0.05;
      vMax += span * 0.05;
    }

    dMax = Math.max(...data.profile.map((p) => p.depth_m)) || 1000;

    points = data.profile.map((p) => {
      const v = p[activeVariable];
      const x = PAD_L + ((v - vMin) / (vMax - vMin)) * plotW;
      const y = PAD_T + (p.depth_m / dMax) * plotH;
      return { x, y, pt: p };
    });

    pathD = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ");
  }

  // Active variable theme colors
  const themeColor =
    activeVariable === "temperature"
      ? "#ef4444"
      : activeVariable === "salinity"
      ? "#a855f7"
      : "#10b981";

  return (
    <div
      style={{
        marginTop: 8,
        background: "rgba(5, 15, 25, 0.95)",
        border: "1px solid var(--line)",
        borderRadius: 6,
        padding: "8px 10px 10px 10px",
        boxShadow: "0 6px 20px rgba(0,0,0,0.5)",
      }}
    >
      {/* Header with Title & Close */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: themeColor }}>
            📍 Subsurface Core Probe
          </span>
          {data && (
            <span
              style={{
                fontSize: 9.5,
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
              }}
            >
              ({data.lat.toFixed(1)}°N, {data.lon.toFixed(1)}°E)
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            fontSize: 14,
            cursor: "pointer",
            lineHeight: 1,
            padding: "0 2px",
          }}
          title="Dismiss probe"
        >
          ✕
        </button>
      </div>

      {/* Variable Toggle Switch */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 4,
          marginBottom: 8,
        }}
      >
        {(
          [
            { id: "temperature", label: "Temperature", unit: "°C", color: "#ef4444" },
            { id: "salinity", label: "Salinity", unit: "PSU", color: "#a855f7" },
            { id: "chlorophyll", label: "Chlorophyll", unit: "mg/m³", color: "#10b981" },
          ] as const
        ).map((v) => {
          const active = activeVariable === v.id;
          return (
            <button
              key={v.id}
              type="button"
              onClick={() => onVariableChange(v.id)}
              style={{
                fontSize: 9.5,
                padding: "4px 2px",
                borderRadius: 4,
                border: active ? `1px solid ${v.color}` : "1px solid var(--line)",
                background: active ? `${v.color}22` : "rgba(255,255,255,0.02)",
                color: active ? v.color : "var(--text-muted)",
                fontWeight: active ? 700 : 500,
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {v.label}
            </button>
          );
        })}
      </div>

      {loading && (
        <div
          style={{
            height: 140,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          Sampling multi-variable ocean column…
        </div>
      )}

      {!loading && data && (
        <>
          {/* 2D Depth Profile Line Chart */}
          <div style={{ position: "relative", width: "100%", overflow: "hidden" }}>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              style={{ width: "100%", height: "auto", display: "block" }}
            >
              {/* Photic Zone / Euphotic Boundary Guide (<200m) */}
              <rect
                x={PAD_L}
                y={PAD_T}
                width={plotW}
                height={(200.0 / dMax) * plotH}
                fill="rgba(56, 189, 248, 0.05)"
              />
              <line
                x1={PAD_L}
                y1={PAD_T + (200.0 / dMax) * plotH}
                x2={PAD_L + plotW}
                y2={PAD_T + (200.0 / dMax) * plotH}
                stroke="rgba(56, 189, 248, 0.25)"
                strokeDasharray="3 3"
              />
              <text
                x={PAD_L + plotW - 4}
                y={PAD_T + (200.0 / dMax) * plotH - 3}
                fontSize="7.5"
                fill="rgba(56, 189, 248, 0.6)"
                textAnchor="end"
              >
                Photic Zone (200m)
              </text>

              {/* Grid axes */}
              <line
                x1={PAD_L}
                y1={PAD_T}
                x2={PAD_L}
                y2={PAD_T + plotH}
                stroke="var(--line)"
                strokeWidth={1}
              />
              <line
                x1={PAD_L}
                y1={PAD_T + plotH}
                x2={PAD_L + plotW}
                y2={PAD_T + plotH}
                stroke="var(--line)"
                strokeWidth={1}
              />

              {/* Depth axis labels */}
              <text x={PAD_L - 4} y={PAD_T + 4} fontSize="8" fill="var(--text-muted)" textAnchor="end">
                0m
              </text>
              <text
                x={PAD_L - 4}
                y={PAD_T + (500.0 / dMax) * plotH + 3}
                fontSize="8"
                fill="var(--text-muted)"
                textAnchor="end"
              >
                500m
              </text>
              <text
                x={PAD_L - 4}
                y={PAD_T + plotH}
                fontSize="8"
                fill="var(--text-muted)"
                textAnchor="end"
              >
                1000m
              </text>

              {/* Variable horizontal value labels */}
              <text x={PAD_L} y={H - 8} fontSize="8" fill="var(--text-muted)">
                {vMin.toFixed(1)}
              </text>
              <text
                x={PAD_L + plotW}
                y={H - 8}
                fontSize="8"
                fill="var(--text-muted)"
                textAnchor="end"
              >
                {vMax.toFixed(1)}
              </text>

              {/* Continuous Profile Curve */}
              {pathD && (
                <path
                  d={pathD}
                  fill="none"
                  stroke={themeColor}
                  strokeWidth={2}
                  strokeLinecap="round"
                />
              )}

              {/* Node markers */}
              {points.map((p, i) => {
                const isHover = hoverPoint?.depth_m === p.pt.depth_m;
                return (
                  <g
                    key={i}
                    onMouseEnter={() => setHoverPoint(p.pt)}
                    onMouseLeave={() => setHoverPoint(null)}
                    style={{ cursor: "pointer" }}
                  >
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={isHover ? 4.5 : 2.5}
                      fill={themeColor}
                      stroke="#050f19"
                      strokeWidth={1.5}
                    />
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Hover / Point Readout */}
          <div
            style={{
              marginTop: 4,
              padding: "4px 6px",
              background: "rgba(255,255,255,0.03)",
              borderRadius: 4,
              fontSize: 9.5,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontFamily: "var(--font-mono)",
            }}
          >
            {hoverPoint ? (
              <>
                <span style={{ color: "var(--text-muted)" }}>
                  Depth: <strong style={{ color: "#fff" }}>{hoverPoint.depth_m}m</strong>
                </span>
                <span style={{ color: themeColor, fontWeight: 700 }}>
                  {formatProbeValue(activeVariable, hoverPoint[activeVariable])}
                </span>
              </>
            ) : (
              <>
                <span style={{ color: "var(--text-muted)" }}>Surface (0m):</span>
                <span style={{ color: themeColor, fontWeight: 700 }}>
                  {formatProbeValue(activeVariable, data.profile[0]?.[activeVariable] ?? 0)}
                </span>
                <span style={{ color: "var(--text-muted)" }}>
                  Deep ({data.profile[data.profile.length - 1]?.depth_m}m):
                </span>
                <span style={{ color: themeColor }}>
                  {formatProbeValue(
                    activeVariable,
                    data.profile[data.profile.length - 1]?.[activeVariable] ?? 0
                  )}
                </span>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
