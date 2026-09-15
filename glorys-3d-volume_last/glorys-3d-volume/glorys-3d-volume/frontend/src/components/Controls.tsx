import React from "react";
import Globe from "./Globe";
import SubsurfacePredictionCard from "./SubsurfacePredictionCard";
import type { TimeRangeResponse, VolumeMeta, VolumeData, GlorysHealth, OceanVariable, ProbePoint } from "../types";
import { VARIABLE_CATALOGUE } from "../types";

interface ControlsProps {
  timeRange: TimeRangeResponse | null;
  health: GlorysHealth | null;
  meta: VolumeMeta | null;
  volumeData?: VolumeData | null;

  // Selected query params
  selectedDate: string;
  onDateChange: (d: string) => void;
  lonMin: number;
  onLonMinChange: (v: number) => void;
  lonMax: number;
  onLonMaxChange: (v: number) => void;
  latMin: number;
  onLatMinChange: (v: number) => void;
  latMax: number;
  onLatMaxChange: (v: number) => void;
  depthMin: number;
  onDepthMinChange: (v: number) => void;
  depthMax: number;
  onDepthMaxChange: (v: number) => void;
  lod: number;
  onLodChange: (lod: number) => void;

  // Variable selection (new)
  selectedVariable: OceanVariable;
  onVariableChange: (v: OceanVariable) => void;

  // Globe region select with instant load
  onSelectRegion?: (coords: {
    lonMin: number;
    lonMax: number;
    latMin: number;
    latMax: number;
  }) => void;
  onPickPoint?: (probe: ProbePoint) => void;

  // Action
  onLoadVolume: () => void;
  loading: boolean;
  loadingMessage?: string;
  error: string | null;

  // Depth Slicing
  sliceMode: "volume" | "layer";
  onSliceModeChange: (m: "volume" | "layer") => void;
  sliceStep: number;
  onSliceStepChange: (step: number) => void;
  activeSlice: number;
  onActiveSliceChange: (slice: number) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.06em",
          color: "var(--accent)",
          textTransform: "uppercase",
          marginBottom: 8,
          borderBottom: "1px solid var(--line)",
          paddingBottom: 4,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
      </div>
      {children}
    </div>
  );
}

function shiftDate(dateStr: string, days: number): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    d.setDate(d.getDate() + days);
    return d.toISOString().split("T")[0];
  } catch {
    return dateStr;
  }
}

export default function Controls(props: ControlsProps) {
  const {
    timeRange,
    health,
    meta,
    selectedDate,
    onDateChange,
    lonMin,
    onLonMinChange,
    lonMax,
    onLonMaxChange,
    latMin,
    onLatMinChange,
    latMax,
    onLatMaxChange,
    depthMin,
    onDepthMinChange,
    depthMax,
    onDepthMaxChange,
    lod,
    onLodChange,
    selectedVariable,
    onVariableChange,
    onLoadVolume,
    loading,
    loadingMessage,
    error,
    volumeData,
    sliceMode,
    onSliceModeChange,
    sliceStep,
    onSliceStepChange,
    activeSlice,
    onActiveSliceChange,
  } = props;

  const isRemote = (health?.mode === "remote" && health.copernicus_credentials_configured);

  // For 2D variables, depth controls are not meaningful
  const varInfo = VARIABLE_CATALOGUE.find((v) => v.variable === selectedVariable);
  const is2d = varInfo?.is_2d ?? false;
  const isClimateOnly = varInfo?.climate_only ?? false;

  return (
    <div
      style={{
        width: 320,
        height: "100%",
        background: "var(--bg-panel)",
        borderLeft: "1px solid var(--line)",
        padding: "16px 18px",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        userSelect: "none",
      }}
    >
      {/* Title & Mode Indicator */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
            GLORYS 3D Remote
          </div>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: 4,
              letterSpacing: "0.04em",
              background: isRemote ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
              color: isRemote ? "#10b981" : "#f59e0b",
              border: `1px solid ${isRemote ? "#10b981" : "#f59e0b"}`,
            }}
          >
            {isRemote ? "REMOTE COPERNICUS" : "LOCAL FIXTURE"}
          </span>
        </div>
        <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}>
          Copernicus Marine GLORYS12V1
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.12)",
            border: "1px solid var(--danger)",
            color: "var(--danger)",
            padding: "8px 10px",
            borderRadius: 6,
            fontSize: 11,
            lineHeight: 1.4,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}

      {/* ── Variable Selector ── */}
      <Section title="Ocean Variable">
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {VARIABLE_CATALOGUE.map((v) => {
            const isSelected = selectedVariable === v.variable;
            return (
              <button
                key={v.variable}
                onClick={() => onVariableChange(v.variable)}
                disabled={loading}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "7px 10px",
                  borderRadius: 5,
                  border: isSelected
                    ? "1px solid var(--accent)"
                    : "1px solid var(--line)",
                  background: isSelected
                    ? "rgba(95, 211, 196, 0.12)"
                    : "var(--bg-panel-raised)",
                  color: isSelected ? "var(--accent)" : "var(--text-primary)",
                  cursor: loading ? "not-allowed" : "pointer",
                  fontWeight: isSelected ? 600 : 400,
                  fontSize: 12,
                  textAlign: "left",
                  transition: "all 0.15s ease",
                }}
              >
                <span>{v.label}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span
                    style={{
                      fontSize: 9.5,
                      color: isSelected ? "var(--accent)" : "var(--text-muted)",
                      background: "rgba(255,255,255,0.06)",
                      padding: "1px 5px",
                      borderRadius: 3,
                    }}
                  >
                    {v.unit}
                  </span>
                  {v.climate_only && (
                    <span
                      title="Only available for December 2004 local dataset"
                      style={{
                        fontSize: 8.5,
                        fontWeight: 700,
                        letterSpacing: "0.03em",
                        color: "#f59e0b",
                        background: "rgba(245, 158, 11, 0.1)",
                        border: "1px solid rgba(245, 158, 11, 0.4)",
                        padding: "0px 4px",
                        borderRadius: 3,
                      }}
                    >
                      DEC 2004
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>

        {/* Dec 2004 dataset notice for climate variables */}
        {isClimateOnly && (
          <div
            style={{
              marginTop: 8,
              padding: "6px 9px",
              borderRadius: 5,
              background: "rgba(245, 158, 11, 0.08)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              fontSize: 10.5,
              color: "#fbbf24",
              lineHeight: 1.4,
            }}
          >
            ⚠ This variable is only available from the local December 2004 fixture.
            Date picker is fixed to Dec 2004 range. Run the ingest script first if you
            haven&apos;t already.
          </div>
        )}
      </Section>

      {/* Remote Subset & Date Query Section */}
      <Section title="Remote Data Query">
        <Row label="GLORYS Date (YYYY-MM-DD)">
          <input
            type="date"
            value={selectedDate}
            min={isClimateOnly ? "2004-12-01" : (timeRange?.start ?? "1993-01-01")}
            max={isClimateOnly ? "2004-12-31" : (timeRange?.end ?? "2026-06-23")}
            onChange={(e) => onDateChange(e.target.value)}
            disabled={loading}
            style={{
              width: "100%",
              background: "var(--bg-panel-raised)",
              color: "var(--text-primary)",
              border: "1px solid var(--line)",
              borderRadius: 4,
              padding: "5px 8px",
              fontSize: 12,
            }}
          />

          {/* Quick Date Scrub / Step Buttons */}
          <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
            {[-30, -7, -1, 1, 7, 30].map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => onDateChange(shiftDate(selectedDate, days))}
                disabled={loading}
                title={`Shift ${days > 0 ? "+" + days : days} days`}
                style={{
                  flex: 1,
                  padding: "2px 0",
                  fontSize: 9,
                  borderRadius: 3,
                  border: "1px solid var(--line)",
                  background: "var(--bg-panel-raised)",
                  color: "var(--text-muted)",
                  cursor: loading ? "wait" : "pointer",
                  transition: "background 0.15s",
                }}
              >
                {days > 0 ? `+${days}d` : `${days}d`}
              </button>
            ))}
          </div>

          {timeRange && (
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
              Available:{" "}
              {isClimateOnly ? "2004-12-01 → 2004-12-31" : `${timeRange.start} → ${timeRange.end}`}
            </div>
          )}
        </Row>

        {/* Interactive 3D Globe for Point-and-Click Region Selection */}
        <Globe
          lonMin={lonMin}
          lonMax={lonMax}
          latMin={latMin}
          latMax={latMax}
          onSelectRegion={(coords) => {
            onLonMinChange(coords.lonMin);
            onLonMaxChange(coords.lonMax);
            onLatMinChange(coords.latMin);
            onLatMaxChange(coords.latMax);
            if (props.onSelectRegion) {
               props.onSelectRegion(coords);
            }
          }}
          onPickPoint={props.onPickPoint}
          disabled={loading}
        />

        {/* Geographic Bounds */}
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
            Geographic Bounds (Longitude × Latitude)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            <div>
              <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Lon Min (°)</label>
              <input
                type="number"
                step="0.5"
                value={lonMin}
                onChange={(e) => onLonMinChange(parseFloat(e.target.value) || 0)}
                disabled={loading}
                style={{
                  width: "100%",
                  background: "var(--bg-panel-raised)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--line)",
                  borderRadius: 4,
                  padding: "4px 6px",
                  fontSize: 11,
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Lon Max (°)</label>
              <input
                type="number"
                step="0.5"
                value={lonMax}
                onChange={(e) => onLonMaxChange(parseFloat(e.target.value) || 0)}
                disabled={loading}
                style={{
                  width: "100%",
                  background: "var(--bg-panel-raised)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--line)",
                  borderRadius: 4,
                  padding: "4px 6px",
                  fontSize: 11,
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Lat Min (°)</label>
              <input
                type="number"
                step="0.5"
                value={latMin}
                onChange={(e) => onLatMinChange(parseFloat(e.target.value) || 0)}
                disabled={loading}
                style={{
                  width: "100%",
                  background: "var(--bg-panel-raised)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--line)",
                  borderRadius: 4,
                  padding: "4px 6px",
                  fontSize: 11,
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Lat Max (°)</label>
              <input
                type="number"
                step="0.5"
                value={latMax}
                onChange={(e) => onLatMaxChange(parseFloat(e.target.value) || 0)}
                disabled={loading}
                style={{
                  width: "100%",
                  background: "var(--bg-panel-raised)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--line)",
                  borderRadius: 4,
                  padding: "4px 6px",
                  fontSize: 11,
                }}
              />
            </div>
          </div>
        </div>

        {/* Depth Bounds — hidden for 2D variables */}
        {!is2d && (
          <>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                Depth Bounds (Meters)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                <div>
                  <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Min Depth (m)</label>
                  <input
                    type="number"
                    step="10"
                    min="0"
                    value={depthMin}
                    onChange={(e) => onDepthMinChange(parseFloat(e.target.value) || 0)}
                    disabled={loading}
                    style={{
                      width: "100%",
                      background: "var(--bg-panel-raised)",
                      color: "var(--text-primary)",
                      border: "1px solid var(--line)",
                      borderRadius: 4,
                      padding: "4px 6px",
                      fontSize: 11,
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 9.5, color: "var(--text-muted)" }}>Max Depth (m)</label>
                  <input
                    type="number"
                    step="50"
                    value={depthMax}
                    onChange={(e) => onDepthMaxChange(parseFloat(e.target.value) || 0)}
                    disabled={loading}
                    style={{
                      width: "100%",
                      background: "var(--bg-panel-raised)",
                      color: "var(--text-primary)",
                      border: "1px solid var(--line)",
                      borderRadius: 4,
                      padding: "4px 6px",
                      fontSize: 11,
                    }}
                  />
                </div>
              </div>
            </div>

            <Section title="Depth Slicing">
              <Row label="View Mode">
                <div style={{ display: "flex", gap: 5 }}>
                  <button
                    onClick={() => onSliceModeChange("volume")}
                    style={{
                      flex: 1,
                      padding: "5px 0",
                      fontSize: 11,
                      borderRadius: 4,
                      border: sliceMode === "volume" ? "1px solid var(--accent)" : "1px solid var(--line)",
                      background: sliceMode === "volume" ? "rgba(95, 211, 196, 0.12)" : "var(--bg-panel-raised)",
                      color: sliceMode === "volume" ? "var(--accent)" : "var(--text-primary)",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    Full Volume
                  </button>
                  <button
                    onClick={() => onSliceModeChange("layer")}
                    style={{
                      flex: 1,
                      padding: "5px 0",
                      fontSize: 11,
                      borderRadius: 4,
                      border: sliceMode === "layer" ? "1px solid var(--accent)" : "1px solid var(--line)",
                      background: sliceMode === "layer" ? "rgba(95, 211, 196, 0.12)" : "var(--bg-panel-raised)",
                      color: sliceMode === "layer" ? "var(--accent)" : "var(--text-primary)",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    Layer/Slice
                  </button>
                </div>
              </Row>

              {sliceMode === "layer" && (
                <>
                  <Row label="Slice Thickness">
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <input
                        type="number"
                        min={1}
                        step={1}
                        value={sliceStep}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10);
                          if (!isNaN(v) && v >= 1) onSliceStepChange(v);
                        }}
                        style={{
                          flex: 1,
                          background: "var(--bg-panel-raised)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--line)",
                          borderRadius: 4,
                          padding: "4px 6px",
                          fontSize: 11,
                        }}
                      />
                      <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>m</span>
                    </div>
                  </Row>

                  <Row label="Active Layer">
                    {(() => {
                      const maxSlices = Math.max(1, Math.floor(Math.max(1, depthMax - depthMin) / sliceStep));
                      const startM = depthMin + (activeSlice - 1) * sliceStep;
                      const endM = Math.min(depthMax, depthMin + activeSlice * sliceStep);
                      // Clamp activeSlice if maxSlices changed
                      const clampedSlice = Math.min(activeSlice, maxSlices);
                      if (clampedSlice !== activeSlice) onActiveSliceChange(clampedSlice);
                      return (
                        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                          <input
                            type="range"
                            min={1}
                            max={maxSlices}
                            value={activeSlice}
                            onChange={(e) => onActiveSliceChange(parseInt(e.target.value, 10))}
                            style={{ width: "100%", accentColor: "var(--accent)" }}
                          />
                          <div style={{ fontSize: 10, color: "var(--accent)", textAlign: "center", background: "rgba(95,211,196,0.1)", padding: "4px", borderRadius: 3 }}>
                            Slice {activeSlice} of {maxSlices}: {startM.toFixed(0)}m – {endM.toFixed(0)}m
                          </div>
                        </div>
                      );
                    })()}
                  </Row>
                </>
              )}
            </Section>
          </>
        )}

        {/* Depth N/A notice for 2D variables */}
        {is2d && (
          <div
            style={{
              marginBottom: 10,
              padding: "5px 8px",
              borderRadius: 4,
              background: "rgba(95, 211, 196, 0.06)",
              border: "1px solid rgba(95, 211, 196, 0.2)",
              fontSize: 10,
              color: "var(--text-muted)",
            }}
          >
            Depth controls not applicable — this variable is depth-integrated.
          </div>
        )}

        {/* Level of Detail (LOD) */}
        <Row label="Resolution / Grid Density">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              value={lod}
              onChange={(e) => onLodChange(parseInt(e.target.value, 10))}
              disabled={loading}
              style={{
                flex: 1,
                cursor: loading ? "not-allowed" : "pointer",
                accentColor: "var(--accent)",
              }}
            />
            <span
              style={{
                fontSize: 11,
                color: "var(--accent)",
                fontWeight: 600,
                width: 30,
                textAlign: "right",
              }}
            >
              {lod} / 10
            </span>
          </div>
        </Row>

        {/* Load Volume Button */}
        <button
          onClick={onLoadVolume}
          disabled={loading}
          style={{
            width: "100%",
            marginTop: 6,
            padding: "9px 0",
            fontSize: 12.5,
            fontWeight: 700,
            letterSpacing: "0.04em",
            borderRadius: 6,
            border: "none",
            background: loading ? "var(--bg-panel-raised)" : "var(--accent)",
            color: loading ? "var(--text-muted)" : "#04201c",
            cursor: loading ? "wait" : "pointer",
            transition: "all 0.15s ease",
            boxShadow: loading ? "none" : "0 2px 8px rgba(34, 211, 238, 0.25)",
          }}
        >
          {loading ? (loadingMessage || "Loading GLORYS12V1...") : "LOAD GLORYS VOLUME"}
        </button>
      </Section>

      {/* Subsurface Temperature Prediction Card */}
      <SubsurfacePredictionCard volumeData={volumeData ?? null} />

      {/* Active Dataset Metadata Summary */}
      {meta && (
        <Section title="Active Dataset Metadata">
          <div className="mono" style={{ fontSize: 10.5, lineHeight: 1.6, color: "var(--text-muted)" }}>
            <div><strong style={{ color: "var(--text-primary)" }}>Date:</strong> {meta.date || selectedDate}</div>
            <div>
              <strong style={{ color: "var(--text-primary)" }}>Variable:</strong>{" "}
              {meta.variable}{meta.label ? ` (${meta.label})` : ""} — {meta.units}
            </div>
            {meta.is_2d && (
              <div>
                <strong style={{ color: "var(--accent)" }}>2D surface field</strong>
                {" "}(depth-integrated, flat heatmap)
              </div>
            )}
            <div><strong style={{ color: "var(--text-primary)" }}>Lon:</strong> {meta.longitude_min.toFixed(2)}° → {meta.longitude_max.toFixed(2)}°</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Lat:</strong> {meta.latitude_min.toFixed(2)}° → {meta.latitude_max.toFixed(2)}°</div>
            {!meta.is_2d && (
              <div><strong style={{ color: "var(--text-primary)" }}>Depth:</strong> {meta.depth_min.toFixed(1)}–{meta.depth_max.toFixed(1)} m ({meta.shape.depth} levels)</div>
            )}
            <div>
              <strong style={{ color: "var(--text-primary)" }}>
                {meta.is_2d ? "Pixels:" : "Voxels:"}
              </strong>{" "}
              {meta.is_2d
                ? `${meta.shape.lon} × ${meta.shape.lat} (${meta.shape.lon * meta.shape.lat})`
                : `${meta.shape.lon} × ${meta.shape.lat} × ${meta.shape.depth} (${meta.shape.lon * meta.shape.lat * meta.shape.depth})`}
            </div>
            <div><strong style={{ color: "var(--text-primary)" }}>Payload:</strong> {(meta.byte_length / (1024 * 1024)).toFixed(2)} MB Float32</div>
            <div><strong style={{ color: "var(--text-primary)" }}>Source:</strong> {meta.mode === "remote" ? "Remote Copernicus Marine" : "Local Fixture"}</div>
          </div>
        </Section>
      )}

      <div style={{ marginTop: "auto", paddingTop: 8, fontSize: 10, color: "var(--text-muted)", lineHeight: 1.4 }}>
        Click any point in the 3D volume to inspect the real vertical profile.
      </div>
    </div>
  );
}
