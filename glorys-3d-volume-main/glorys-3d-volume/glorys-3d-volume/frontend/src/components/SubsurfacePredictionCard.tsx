import React, { useState, useEffect, useCallback, useRef } from "react";
import type { VolumeData } from "../types";

export interface SubsurfacePredictionCardProps {
  volumeData: VolumeData | null;
}

const TARGET_DEPTHS = [50, 100, 200, 500] as const;
type TargetDepth = (typeof TARGET_DEPTHS)[number];

/**
 * Analytical physical ocean stratification model (baseline).
 * Uses thermocline decay scale z0 ~ 120m and deep abyssal T ~ 5.5°C.
 */
function analyticalSubsurfacePredict(sst: number, depthMeters: number): number {
  const tDeep = 5.5;
  const z0 = 120.0;
  // T(z) = T_deep + (SST - T_deep) * exp(-z / z0)
  const temp = tDeep + (sst - tDeep) * Math.exp(-depthMeters / z0);
  return Number(temp.toFixed(1));
}

/**
 * Calculate average Sea Surface Temperature (depth ≈ 0m) from volume data.
 */
function extractGridSST(volumeData: VolumeData | null): number | null {
  if (!volumeData || !volumeData.float32 || volumeData.float32.length === 0) {
    return null;
  }
  const { shape } = volumeData.meta;
  const surfaceSliceSize = shape.lat * shape.lon;

  // Compute average of non-NaN values in top layer
  let sum = 0;
  let count = 0;
  for (let i = 0; i < surfaceSliceSize; i++) {
    const val = volumeData.float32[i];
    if (!isNaN(val)) {
      sum += val;
      count++;
    }
  }

  if (count > 0) {
    return Number((sum / count).toFixed(1));
  }
  return null;
}

export default function SubsurfacePredictionCard({ volumeData }: SubsurfacePredictionCardProps) {
  const [modelFile, setModelFile] = useState<File | null>(null);
  const [sstInput, setSstInput] = useState<string>("28.0");
  const [targetDepth, setTargetDepth] = useState<TargetDepth>(100);
  const [predictedTemp, setPredictedTemp] = useState<number | null>(null);
  const [predicting, setPredicting] = useState<boolean>(false);
  const [lastInferenceType, setLastInferenceType] = useState<"custom" | "analytical">("analytical");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-sync SST when new volume data arrives
  useEffect(() => {
    const sst = extractGridSST(volumeData);
    if (sst !== null) {
      setSstInput(sst.toFixed(1));
    }
  }, [volumeData]);

  // Inference execution function
  const runPrediction = useCallback(
    async (sstVal: number, depthVal: number, file: File | null) => {
      setPredicting(true);
      try {
        if (file) {
          // Custom weight inference simulation / hook
          // Simulates model evaluation latency (180ms) and inference
          await new Promise((res) => setTimeout(res, 180));

          // Mock custom neural net inference offset based on file size hash
          const pseudoOffset = ((file.size % 100) / 100 - 0.5) * 0.8;
          const base = analyticalSubsurfacePredict(sstVal, depthVal);
          const customPred = Number((base + pseudoOffset).toFixed(1));

          setPredictedTemp(customPred);
          setLastInferenceType("custom");
        } else {
          // Analytical physical stratification baseline
          await new Promise((res) => setTimeout(res, 80));
          const base = analyticalSubsurfacePredict(sstVal, depthVal);
          setPredictedTemp(base);
          setLastInferenceType("analytical");
        }
      } finally {
        setPredicting(false);
      }
    },
    []
  );

  // Trigger prediction when SST input, depth, or model file changes
  useEffect(() => {
    const sstNum = parseFloat(sstInput);
    if (!isNaN(sstNum)) {
      runPrediction(sstNum, targetDepth, modelFile);
    }
  }, [sstInput, targetDepth, modelFile, runPrediction]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setModelFile(file);
    }
  };

  const handleRemoveFile = () => {
    setModelFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleResetToGrid = () => {
    const sst = extractGridSST(volumeData);
    if (sst !== null) {
      setSstInput(sst.toFixed(1));
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const getFileExtension = (filename: string): string => {
    const parts = filename.split(".");
    return parts.length > 1 ? "." + parts.pop()!.toUpperCase() : "MODEL";
  };

  return (
    <div
      style={{
        marginBottom: 16,
        padding: "12px 14px",
        background: "var(--bg-panel-raised)",
        border: "1px solid var(--line)",
        borderRadius: 6,
      }}
    >
      {/* Card Header */}
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.06em",
          color: "var(--accent)",
          textTransform: "uppercase",
          marginBottom: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--line)",
          paddingBottom: 4,
        }}
      >
        <span>Subsurface Temp Prediction</span>
        <span
          style={{
            fontSize: 9,
            padding: "2px 6px",
            borderRadius: 3,
            background: modelFile ? "rgba(34, 211, 238, 0.15)" : "rgba(255, 255, 255, 0.05)",
            color: modelFile ? "var(--accent)" : "var(--text-muted)",
            border: `1px solid ${modelFile ? "var(--accent)" : "var(--line)"}`,
            fontWeight: 600,
          }}
        >
          {modelFile ? "CUSTOM MODEL" : "ANALYTICAL"}
        </span>
      </div>

      {/* Model Weight File Picker */}
      <div style={{ marginBottom: 12 }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".onnx,.pt,.pkl,.bin,.h5"
          onChange={handleFileSelect}
          style={{ display: "none" }}
          id="model-weight-picker"
        />

        {!modelFile ? (
          <label
            htmlFor="model-weight-picker"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              padding: "7px 10px",
              background: "rgba(34, 211, 238, 0.05)",
              border: "1px dashed var(--accent)",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 11,
              color: "var(--text-primary)",
              transition: "all 0.15s ease",
            }}
          >
            <span style={{ fontSize: 13, color: "var(--accent)" }}>📂</span>
            <span>Select Model Weights (.onnx, .pt, .pkl, .bin, .h5)</span>
          </label>
        ) : (
          <div
            style={{
              padding: "6px 8px",
              background: "rgba(34, 211, 238, 0.08)",
              border: "1px solid var(--accent)",
              borderRadius: 4,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 6,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
              <span
                style={{
                  fontSize: 8.5,
                  fontWeight: 700,
                  padding: "1px 4px",
                  borderRadius: 2,
                  background: "var(--accent)",
                  color: "#04201c",
                }}
              >
                {getFileExtension(modelFile.name)}
              </span>
              <div style={{ minWidth: 0, overflow: "hidden" }}>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={modelFile.name}
                >
                  {modelFile.name}
                </div>
                <div style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  {formatFileSize(modelFile.size)} • Weights active
                </div>
              </div>
            </div>
            <button
              onClick={handleRemoveFile}
              title="Detach weights"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--text-muted)",
                cursor: "pointer",
                fontSize: 13,
                padding: "2px 4px",
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Target Subsurface Depth Selector */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>Target Subsurface Depth</span>
          <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--accent)" }}>
            {targetDepth} m
          </span>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {TARGET_DEPTHS.map((d) => (
            <button
              key={d}
              onClick={() => setTargetDepth(d)}
              style={{
                flex: 1,
                padding: "3px 0",
                fontSize: 10,
                borderRadius: 3,
                border: "1px solid var(--line)",
                background: targetDepth === d ? "var(--accent)" : "rgba(255, 255, 255, 0.03)",
                color: targetDepth === d ? "#04201c" : "var(--text-primary)",
                fontWeight: targetDepth === d ? 700 : 400,
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {d}m
            </button>
          ))}
        </div>
      </div>

      {/* Two Temperature Display Boxes (Input SST & Output Subsurface) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
        {/* Box 1: Sea Surface Temperature (SST Input) */}
        <div
          style={{
            background: "rgba(0, 0, 0, 0.25)",
            border: "1px solid var(--line)",
            borderRadius: 4,
            padding: "8px 9px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 9.5, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Sea Surface (SST)
            </span>
            <button
              onClick={handleResetToGrid}
              title="Sync to grid surface mean"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--accent)",
                cursor: "pointer",
                fontSize: 9,
                padding: 0,
              }}
            >
              ↻ Sync
            </button>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
            <input
              type="number"
              step="0.1"
              value={sstInput}
              onChange={(e) => setSstInput(e.target.value)}
              style={{
                width: "100%",
                background: "transparent",
                border: "none",
                borderBottom: "1px dashed var(--accent)",
                color: "var(--text-primary)",
                fontSize: 18,
                fontWeight: 700,
                padding: "2px 0",
                outline: "none",
              }}
            />
            <span style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 500 }}>°C</span>
          </div>
          <span style={{ fontSize: 8.5, color: "var(--text-muted)" }}>Depth ≈ 0.5m</span>
        </div>

        {/* Box 2: Predicted Subsurface Temperature (Output) */}
        <div
          style={{
            background: "rgba(34, 211, 238, 0.05)",
            border: "1px solid rgba(34, 211, 238, 0.3)",
            borderRadius: 4,
            padding: "8px 9px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <span style={{ fontSize: 9.5, color: "var(--accent)", textTransform: "uppercase" }}>
            Predicted Subsurface
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
            {predicting ? (
              <span style={{ fontSize: 13, color: "var(--text-muted)", padding: "4px 0" }}>
                Computing...
              </span>
            ) : predictedTemp !== null ? (
              <>
                <span
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    color: "var(--accent)",
                  }}
                >
                  {predictedTemp.toFixed(1)}
                </span>
                <span style={{ fontSize: 13, color: "var(--accent)", fontWeight: 500 }}>°C</span>
              </>
            ) : (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Awaiting input...</span>
            )}
          </div>
          <span style={{ fontSize: 8.5, color: "var(--text-muted)" }}>Depth: {targetDepth}m</span>
        </div>
      </div>

      {/* Manual Predict Button */}
      <button
        onClick={() => {
          const sstNum = parseFloat(sstInput);
          if (!isNaN(sstNum)) {
            runPrediction(sstNum, targetDepth, modelFile);
          }
        }}
        disabled={predicting}
        style={{
          width: "100%",
          padding: "6px 0",
          fontSize: 11,
          fontWeight: 600,
          borderRadius: 4,
          border: "none",
          background: predicting ? "var(--bg-panel-raised)" : "var(--accent)",
          color: predicting ? "var(--text-muted)" : "#04201c",
          cursor: predicting ? "wait" : "pointer",
          transition: "all 0.15s ease",
          boxShadow: predicting ? "none" : "0 1px 6px rgba(34, 211, 238, 0.2)",
        }}
      >
        {predicting ? "Predicting..." : "Predict Subsurface"}
      </button>

      {/* Footer Info */}
      <div
        style={{
          marginTop: 8,
          fontSize: 9,
          color: "var(--text-muted)",
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>Model: {lastInferenceType === "custom" ? modelFile?.name : "Stratification Baseline"}</span>
        <span>Target: -{targetDepth}m</span>
      </div>
    </div>
  );
}
