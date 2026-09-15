import React from "react";
import type { ProfileResponse } from "../types";

interface ProfileChartProps {
  profile: ProfileResponse | null;
  loading: boolean;
  onClose: () => void;
}

const W = 260;
const H = 320;
const PAD_L = 42;
const PAD_R = 14;
const PAD_T = 16;
const PAD_B = 28;

export default function ProfileChart({ profile, loading, onClose }: ProfileChartProps) {
  if (!loading && !profile) return null;

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;

  let pathD = "";
  let points: { x: number; y: number; t: number; d: number }[] = [];
  let tMin = 0;
  let tMax = 1;
  let dMax = 1;

  if (profile) {
    const validPairs = profile.depth
      .map((d, i) => ({ d, t: profile.temperature[i] }))
      .filter((p): p is { d: number; t: number } => p.t !== null);

    if (validPairs.length > 0) {
      tMin = Math.min(...validPairs.map((p) => p.t));
      tMax = Math.max(...validPairs.map((p) => p.t));
      if (tMin === tMax) {
        tMin -= 1;
        tMax += 1;
      }
      dMax = Math.max(...validPairs.map((p) => p.d));

      points = validPairs.map((p) => ({
        x: PAD_L + ((p.t - tMin) / (tMax - tMin)) * plotW,
        y: PAD_T + (p.d / dMax) * plotH,
        t: p.t,
        d: p.d,
      }));
      pathD = points.map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(" ");
    }
  }

  return (
    <div
      style={{
        position: "absolute",
        right: 16,
        bottom: 16,
        width: W,
        background: "var(--bg-panel)",
        border: "1px solid var(--line)",
        borderRadius: 6,
        padding: "10px 12px 14px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>Depth profile</span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            fontSize: 14,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>

      {loading && (
        <div style={{ height: H, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 12 }}>
          Loading real GLORYS column…
        </div>
      )}

      {!loading && profile && (
        <>
          <div className="mono" style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 6 }}>
            {profile.matched_latitude.toFixed(3)}°, {profile.matched_longitude.toFixed(3)}°
          </div>
          <svg width={W} height={H} style={{ display: "block" }}>
            {/* axes */}
            <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={PAD_T + plotH} stroke="var(--line)" />
            <line x1={PAD_L} y1={PAD_T + plotH} x2={PAD_L + plotW} y2={PAD_T + plotH} stroke="var(--line)" />

            {/* depth labels */}
            <text x={4} y={PAD_T + 4} fontSize="9" fill="var(--text-muted)">0m</text>
            <text x={4} y={PAD_T + plotH} fontSize="9" fill="var(--text-muted)">{dMax.toFixed(0)}m</text>

            {/* temp labels */}
            <text x={PAD_L} y={H - 8} fontSize="9" fill="var(--text-muted)">{tMin.toFixed(1)}°</text>
            <text x={PAD_L + plotW - 20} y={H - 8} fontSize="9" fill="var(--text-muted)">{tMax.toFixed(1)}°</text>

            {points.length > 0 && (
              <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
            )}
            {points.map((pt, i) => (
              <circle key={i} cx={pt.x} cy={pt.y} r={1.6} fill="var(--accent)" />
            ))}
          </svg>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
            Real thetao values, {points.length} depth levels — unsmoothed
          </div>
        </>
      )}
    </div>
  );
}
