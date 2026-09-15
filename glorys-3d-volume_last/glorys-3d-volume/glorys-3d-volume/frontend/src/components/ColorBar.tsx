import type { VolumeRenderMode } from "../types";

interface ColorBarProps {
  min: number;
  max: number;
  units: string;
  label?: string; // variable human label (e.g. "Salinity", "Ocean Heat Content (0–700m)")
  renderMode?: VolumeRenderMode;
  salinityWeight?: number;
  onSalinityWeightChange?: (val: number) => void;
  chlIntensity?: number;
  onChlIntensityChange?: (val: number) => void;
}

// Mirrors the GLSL colormap() function in volume.frag / slice.frag
const STOPS = [
  { t: 0.0, c: "rgb(5,5,89)" },
  { t: 0.2, c: "rgb(26,115,230)" },
  { t: 0.4, c: "rgb(26,217,191)" },
  { t: 0.6, c: "rgb(242,242,64)" },
  { t: 0.8, c: "rgb(242,89,26)" },
  { t: 1.0, c: "rgb(191,13,13)" },
];

/** Format a value with the appropriate unit for display */
function formatValue(value: number, units: string): string {
  if (Math.abs(value) >= 1e8) {
    return value.toExponential(1);
  }
  return value.toFixed(1);
}

export default function ColorBar({
  min,
  max,
  units,
  label,
  renderMode = "temperature",
  salinityWeight,
  onSalinityWeightChange,
  chlIntensity,
  onChlIntensityChange,
}: ColorBarProps) {
  let gradientStops = STOPS;
  let legendMinLabel = "Cold";
  let legendMaxLabel = "Warm";

  if (renderMode === "salinity" || (label && label.toLowerCase().includes("salinity"))) {
    gradientStops = [
      { t: 0.0, c: "rgb(0, 235, 245)" },
      { t: 0.33, c: "rgb(38, 140, 242)" },
      { t: 0.66, c: "rgb(153, 51, 224)" },
      { t: 1.0, c: "rgb(122, 8, 133)" },
    ];
    legendMinLabel = "Fresh (<32)";
    legendMaxLabel = "Saline (>37)";
  } else if (renderMode === "chlorophyll" || (label && label.toLowerCase().includes("chlorophyll"))) {
    gradientStops = [
      { t: 0.0, c: "rgb(10, 64, 46)" },
      { t: 0.5, c: "rgb(20, 184, 89)" },
      { t: 1.0, c: "rgb(0, 255, 102)" },
    ];
    legendMinLabel = "0.0 mg/m³";
    legendMaxLabel = "2.0+ mg/m³ (Bloom)";
  } else if (renderMode === "composite") {
    gradientStops = [
      { t: 0.0, c: "rgb(26,115,230)" },
      { t: 0.35, c: "rgb(242,89,26)" },
      { t: 0.65, c: "rgb(153, 51, 224)" },
      { t: 1.0, c: "rgb(0, 255, 102)" },
    ];
    legendMinLabel = "Thermal (T)";
    legendMaxLabel = "Algal Bloom (Chl)";
  }

  const activeColorGradientCss = `linear-gradient(to right, ${gradientStops
    .map((s) => `${s.c} ${s.t * 100}%`)
    .join(", ")})`;
  const mid = (min + max) / 2;

  // Clean up the unit string for display (remove "degrees_" prefix if present)
  const displayUnit = units.replace("degrees_C", "°C").replace("degrees_c", "°C");

  return (
    <div
      className="absolute top-20 left-4 z-20 pointer-events-auto bg-slate-950/85 backdrop-blur-md border border-slate-800 rounded-xl p-3 shadow-xl flex flex-col gap-1.5 w-64"
      style={{
        position: "absolute",
        top: 80,
        left: 16,
        zIndex: 20,
        pointerEvents: "auto",
        background: "rgba(2, 6, 23, 0.85)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(30, 41, 59, 0.8)",
        borderRadius: 12,
        padding: "12px",
        boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        width: 256,
      }}
    >
      <div
        className="flex justify-between text-[10px] text-slate-400 font-medium"
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "#94a3b8",
          fontWeight: 500,
        }}
      >
        <span>{legendMinLabel}</span>
        <span>{legendMaxLabel}</span>
      </div>
      <div
        className="h-2.5 w-full rounded-sm shadow-inner"
        style={{
          height: 10,
          width: "100%",
          borderRadius: 4,
          background: activeColorGradientCss,
          boxShadow: "inset 0 1px 2px rgba(0,0,0,0.5)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
        }}
      />
      <div
        className="flex justify-between text-[11px] font-mono text-slate-300"
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 11,
          fontFamily: "IBM Plex Mono, monospace",
          color: "#cbd5e1",
        }}
      >
        <span>{formatValue(min, units)}</span>
        <span className="text-slate-400" style={{ color: "#94a3b8" }}>
          {formatValue(mid, units)} {displayUnit}
        </span>
        <span>{formatValue(max, units)}</span>
      </div>

      {renderMode === "composite" && onSalinityWeightChange && onChlIntensityChange && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 8,
            borderTop: "1px solid rgba(51, 65, 85, 0.6)",
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "#00e5ff", fontWeight: 500 }}>💧 Salinity</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input
                type="range"
                min="0.0"
                max="2.5"
                step="0.1"
                value={salinityWeight ?? 1.0}
                onChange={(e) => onSalinityWeightChange(parseFloat(e.target.value))}
                style={{ width: 70, height: 4, accentColor: "#00e5ff", cursor: "pointer" }}
              />
              <span style={{ fontSize: 11, fontFamily: "IBM Plex Mono, monospace", color: "#00e5ff", width: 28, textAlign: "right" }}>
                {(salinityWeight ?? 1.0).toFixed(1)}×
              </span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "#10b981", fontWeight: 500 }}>🌿 Bloom</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input
                type="range"
                min="0.0"
                max="3.0"
                step="0.1"
                value={chlIntensity ?? 1.5}
                onChange={(e) => onChlIntensityChange(parseFloat(e.target.value))}
                style={{ width: 70, height: 4, accentColor: "#10b981", cursor: "pointer" }}
              />
              <span style={{ fontSize: 11, fontFamily: "IBM Plex Mono, monospace", color: "#10b981", width: 28, textAlign: "right" }}>
                {(chlIntensity ?? 1.5).toFixed(1)}×
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
