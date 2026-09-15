import React, { useMemo } from "react";
import VerticalColumnProfileChart, { type DepthSample } from "./VerticalColumnProfileChart";
import type {
  ProbePoint,
  ProfileResponse,
  VolumeData,
  OceanVariable,
  VerticalColumnResponse,
} from "../types";

interface PointInspectionCardProps {
  probe: ProbePoint | null;
  profile: ProfileResponse | null;
  verticalColumn?: VerticalColumnResponse | null;
  loading: boolean;
  variable?: OceanVariable;
  volumeData?: VolumeData | null;
  activeSlice?: number;
  totalSlices?: number;
  sliceStep?: number;
  onSliceChange?: (sliceIndex: number) => void;
  onClose: () => void;
}

export default function PointInspectionCard({
  probe,
  profile,
  verticalColumn,
  loading,
  volumeData,
  onClose,
}: PointInspectionCardProps) {
  if (!probe) return null;

  const isLand = Boolean(probe.is_land || verticalColumn?.is_land);

  // 1. Multi-variable resolution (only in ocean water)
  let tempVal: number | null = isLand ? null : (probe.temperature ?? null);
  let salVal: number | null = isLand ? null : (probe.salinity ?? null);
  let chlVal: number | null = isLand ? null : (probe.chlorophyll ?? null);

  if (!isLand && verticalColumn && verticalColumn.profile && verticalColumn.profile.length > 0) {
    let closestPt = verticalColumn.profile[0];
    let minDiff = Infinity;
    for (const pt of verticalColumn.profile) {
      const diff = Math.abs(pt.depth_m - probe.depth);
      if (diff < minDiff) {
        minDiff = diff;
        closestPt = pt;
      }
    }
    if (closestPt) {
      if (tempVal === null) tempVal = closestPt.temperature;
      if (salVal === null) salVal = closestPt.salinity;
      if (chlVal === null) chlVal = closestPt.chlorophyll;
    }
  }

  if (!isLand && tempVal === null && profile && profile.temperature && profile.temperature.length > 0) {
    let closestIdx = 0;
    let minDiff = Infinity;
    profile.depth.forEach((d, i) => {
      const diff = Math.abs(d - probe.depth);
      if (diff < minDiff && profile.temperature[i] !== null) {
        minDiff = diff;
        closestIdx = i;
      }
    });
    const val = profile.temperature[closestIdx];
    if (val !== null && val !== undefined) {
      tempVal = val;
    }
  }

  if (!isLand && tempVal === null && probe.voxelValue !== undefined && probe.voxelValue !== null && !isNaN(probe.voxelValue)) {
    tempVal = probe.voxelValue;
  }

  const dMax = Math.max(10, volumeData?.meta?.depth_max || verticalColumn?.max_depth_m || 500);

  // 2. Multi-Variable Graph Curves Data Preparation
  const chartData: DepthSample[] = useMemo(() => {
    if (isLand) return [];
    if (verticalColumn?.profile && verticalColumn.profile.length > 0) {
      const sorted = [...verticalColumn.profile].sort((a, b) => a.depth_m - b.depth_m);
      const result: DepthSample[] = [];

      for (let i = 0; i < sorted.length; i++) {
        const pt = sorted[i];
        if (pt.depth_m <= dMax) {
          result.push({
            depth: pt.depth_m,
            temperature: pt.temperature,
            salinity: pt.salinity,
            chlorophyll: pt.chlorophyll,
          });
        } else {
          const prev = sorted[i - 1];
          if (prev && prev.depth_m < dMax) {
            const span = pt.depth_m - prev.depth_m;
            const factor = span > 0 ? (dMax - prev.depth_m) / span : 0;
            result.push({
              depth: dMax,
              temperature: prev.temperature + factor * (pt.temperature - prev.temperature),
              salinity: prev.salinity + factor * (pt.salinity - prev.salinity),
              chlorophyll: prev.chlorophyll + factor * (pt.chlorophyll - prev.chlorophyll),
            });
          }
          break;
        }
      }
      return result;
    }
    if (profile?.depth && profile.temperature) {
      const samples: DepthSample[] = [];
      profile.depth.forEach((d, i) => {
        const t = profile.temperature[i];
        if (t !== null && t !== undefined && !isNaN(t) && d <= dMax) {
          samples.push({
            depth: d,
            temperature: t,
          });
        }
      });
      return samples;
    }
    return [];
  }, [isLand, verticalColumn, profile, dMax]);

  const isFeaturePin = Boolean(probe.isFeaturePin);
  const isChl = probe.featureName?.toLowerCase().includes("chlorophyll") ?? false;
  const pinType = isChl ? "chlorophyll" : "salinity";

  const lonStr = probe.lon !== undefined && probe.lon !== null
    ? `${probe.lon >= 0 ? `${probe.lon.toFixed(3)}°E` : `${Math.abs(probe.lon).toFixed(3)}°W`}`
    : "—";
  const latStr = probe.lat !== undefined && probe.lat !== null
    ? `${probe.lat >= 0 ? `${probe.lat.toFixed(3)}°N` : `${Math.abs(probe.lat).toFixed(3)}°S`}`
    : "—";
  const depthStr = probe.depth !== undefined && probe.depth !== null
    ? `${probe.depth.toFixed(1)}m`
    : "0.0m";

  return (
    <div
      className={`absolute bottom-6 left-4 z-50 pointer-events-auto bg-slate-950/95 backdrop-blur-md rounded-xl p-4 shadow-2xl w-[320px] text-white ${
        isLand ? "border border-amber-500/50" : "border border-cyan-500/40"
      }`}
      style={{
        position: "absolute",
        bottom: 24,
        left: 16,
        zIndex: 50,
        pointerEvents: "auto",
        background: "rgba(2, 6, 23, 0.95)",
        backdropFilter: "blur(12px)",
        border: isLand ? "1px solid rgba(245, 158, 11, 0.5)" : "1px solid rgba(6, 182, 212, 0.4)",
        borderRadius: 12,
        padding: 16,
        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.8)",
        width: 320,
        minHeight: 180,
        color: "#ffffff",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        boxSizing: "border-box",
      }}
    >
      {/* Header */}
      <div
        className="flex justify-between items-start border-b border-slate-800 pb-2 mb-3"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          borderBottom: "1px solid rgba(30, 41, 59, 0.8)",
          paddingBottom: 8,
          marginBottom: 4,
        }}
      >
        <div>
          <div
            className="flex items-center gap-1.5 font-bold text-sm"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontWeight: 700,
              fontSize: 14,
              color: isLand ? "#fbbf24" : isChl ? "#34d399" : "#67e8f9",
            }}
          >
            <span>{isLand ? "⚠️" : pinType === "chlorophyll" ? "🌿" : "💧"}</span>
            <span>
              {isLand
                ? "TERRESTRIAL LANDMASS"
                : isFeaturePin
                ? (pinType === "chlorophyll" ? "Euphotic Chlorophyll Hotspot" : "Salinity Reference Core")
                : "OCEAN WATER COLUMN"}
            </span>
          </div>
          <span
            className="text-[10px] text-slate-400 font-mono"
            style={{
              fontSize: 10,
              color: isLand ? "#fcd34d" : "#94a3b8",
              fontFamily: "IBM Plex Mono, monospace",
              display: "block",
              marginTop: 2,
            }}
          >
            {isLand
              ? "Continental Topography / Non-Marine Grid Cell"
              : isFeaturePin
              ? (pinType === "chlorophyll"
                  ? "Copernicus BGC Biogeochemical Peak"
                  : "GLORYS12V1 Haline Anomaly")
              : "GLORYS12V1 In-Situ Sample"}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 text-xs font-mono"
          style={{
            background: "transparent",
            border: "none",
            color: "#94a3b8",
            cursor: "pointer",
            padding: "4px 8px",
            borderRadius: 4,
            fontSize: 13,
            fontFamily: "IBM Plex Mono, monospace",
          }}
          aria-label="Close details"
        >
          ✕
        </button>
      </div>

      {/* Coordinates & Depth */}
      <div
        className="grid grid-cols-3 gap-2 text-xs font-mono bg-slate-900/80 p-2 rounded-lg mb-3 border border-slate-800"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 8,
          fontSize: 12,
          fontFamily: "IBM Plex Mono, monospace",
          background: "rgba(15, 23, 42, 0.8)",
          padding: 8,
          borderRadius: 8,
          border: "1px solid rgba(30, 41, 59, 0.8)",
          textAlign: "center",
        }}
      >
        <div>
          <span
            className="text-[9px] text-slate-500 block"
            style={{ fontSize: 9, color: "#64748b", display: "block" }}
          >
            LON
          </span>
          <strong className="text-white" style={{ color: "#ffffff" }}>
            {lonStr}
          </strong>
        </div>
        <div>
          <span
            className="text-[9px] text-slate-500 block"
            style={{ fontSize: 9, color: "#64748b", display: "block" }}
          >
            LAT
          </span>
          <strong className="text-white" style={{ color: "#ffffff" }}>
            {latStr}
          </strong>
        </div>
        <div>
          <span
            className="text-[9px] text-slate-500 block"
            style={{ fontSize: 9, color: "#64748b", display: "block" }}
          >
            DEPTH
          </span>
          <strong className={isLand ? "text-amber-300" : "text-cyan-300"} style={{ color: isLand ? "#fcd34d" : "#67e8f9" }}>
            {depthStr}
          </strong>
        </div>
      </div>

      {/* Conditional: Terrestrial Landmass Warning State vs Oceanographic Metrics */}
      {isLand ? (
        <div
          className="bg-amber-950/40 border border-amber-500/30 rounded-lg p-3 text-xs flex flex-col gap-2"
          style={{
            background: "rgba(69, 26, 3, 0.45)",
            border: "1px solid rgba(245, 158, 11, 0.35)",
            borderRadius: 8,
            padding: 12,
            fontSize: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            className="flex items-center gap-1.5 text-amber-300 font-bold text-[11px] font-mono uppercase tracking-wider"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              color: "#fcd34d",
              fontWeight: 700,
              fontSize: 11,
              fontFamily: "IBM Plex Mono, monospace",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            <span>🛡️</span>
            <span>Land Rejection Mask Active</span>
          </div>
          <p
            className="text-slate-300 text-[11px] leading-relaxed m-0"
            style={{
              color: "#cbd5e1",
              fontSize: 11,
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Selected coordinates fall on continental landmass. Oceanographic telemetry (temperature, salinity, chlorophyll-a) and vertical subsurface water column profiles are unavailable for terrestrial topography.
          </p>
          <div
            className="text-[10px] text-amber-400/80 font-mono pt-1.5 border-t border-amber-500/20"
            style={{
              fontSize: 10,
              color: "rgba(251, 191, 36, 0.8)",
              fontFamily: "IBM Plex Mono, monospace",
              paddingTop: 6,
              borderTop: "1px solid rgba(245, 158, 11, 0.2)",
            }}
          >
            GLORYS12V1 / Copernicus Oceanic Mask: NaN
          </div>
        </div>
      ) : (
        <>
          {/* Metric Cards */}
          <div
            className="grid grid-cols-3 gap-2 mb-3"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 8,
            }}
          >
            <div
              className="bg-slate-900/90 border border-red-500/30 rounded-lg p-1.5 text-center"
              style={{
                background: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: 8,
                padding: 6,
                textAlign: "center",
              }}
            >
              <span
                className="text-[9px] text-red-400 font-bold block"
                style={{ fontSize: 9, color: "#f87171", fontWeight: 700, display: "block" }}
              >
                TEMP
              </span>
              <span
                className="text-xs font-mono font-bold text-red-200"
                style={{
                  fontSize: 12,
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 700,
                  color: "#fecaca",
                }}
              >
                {tempVal !== null ? `${tempVal.toFixed(1)}°C` : "—"}
              </span>
            </div>

            <div
              className="bg-slate-900/90 border border-cyan-500/30 rounded-lg p-1.5 text-center"
              style={{
                background: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(6, 182, 212, 0.3)",
                borderRadius: 8,
                padding: 6,
                textAlign: "center",
              }}
            >
              <span
                className="text-[9px] text-cyan-400 font-bold block"
                style={{ fontSize: 9, color: "#22d3ee", fontWeight: 700, display: "block" }}
              >
                SALINITY
              </span>
              <span
                className="text-xs font-mono font-bold text-cyan-200"
                style={{
                  fontSize: 12,
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 700,
                  color: "#cffafe",
                }}
              >
                {salVal !== null ? salVal.toFixed(2) : "—"}
              </span>
              <span
                className="text-[8px] text-slate-400 block"
                style={{ fontSize: 8, color: "#94a3b8", display: "block" }}
              >
                PSU
              </span>
            </div>

            <div
              className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-1.5 text-center"
              style={{
                background: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
                borderRadius: 8,
                padding: 6,
                textAlign: "center",
              }}
            >
              <span
                className="text-[9px] text-emerald-400 font-bold block"
                style={{ fontSize: 9, color: "#34d399", fontWeight: 700, display: "block" }}
              >
                CHL-A
              </span>
              <span
                className="text-xs font-mono font-bold text-emerald-200"
                style={{
                  fontSize: 12,
                  fontFamily: "IBM Plex Mono, monospace",
                  fontWeight: 700,
                  color: "#a7f3d0",
                }}
              >
                {chlVal !== null ? chlVal.toFixed(3) : "—"}
              </span>
              <span
                className="text-[8px] text-slate-400 block"
                style={{ fontSize: 8, color: "#94a3b8", display: "block" }}
              >
                mg/m³
              </span>
            </div>
          </div>

          {/* Vertical Column Depth Profile Graph */}
          {chartData.length > 0 ? (
            <div
              className="border-t border-slate-800 pt-2"
              style={{
                borderTop: "1px solid rgba(30, 41, 59, 0.8)",
                paddingTop: 8,
              }}
            >
              <VerticalColumnProfileChart
                activeDepth={probe.depth}
                data={chartData}
                height={120}
                maxDepth={dMax}
                width={288}
              />
            </div>
          ) : loading ? (
            <div
              style={{
                height: 120,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                color: "#22d3ee",
                fontStyle: "italic",
                borderTop: "1px solid rgba(30, 41, 59, 0.8)",
                paddingTop: 8,
              }}
            >
              Streaming vertical column profile…
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
