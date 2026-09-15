import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import VolumeViewer from "./components/VolumeViewer";
import Controls from "./components/Controls";
import ColorBar from "./components/ColorBar";
import PointInspectionCard from "./components/PointInspectionCard";
import LayerSliceHUD from "./components/LayerSliceHUD";
import { computeNumericLayers, type NumericLayerData } from "./utils/layerSegmentation";
import { fetchHealth, fetchTimeRange, fetchVolume, fetchProfile, fetchSubsurfaceVolume, fetchVerticalColumn, fetchPointProbe } from "./api";
import type { TimeRangeResponse, VolumeData, ProfileResponse, VerticalColumnResponse, GlorysHealth, OceanVariable, ProbePoint, VolumeRenderMode } from "./types";
import { VARIABLE_CATALOGUE, isOpendapVariable } from "./types";
import { calculateLayerSliceStats } from "./utils/layerStats";
import { readIncomingBounds } from "./utils/incomingBounds";

// Bounds handed over from YARA (1° x 1° cell of the clicked point), if any.
// Read once at module load so the very first volume fetch already uses them.
const incomingBounds = readIncomingBounds();

export default function App() {
  const [health, setHealth] = useState<GlorysHealth | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRangeResponse | null>(null);
  const [volumeData, setVolumeData] = useState<VolumeData | null>(null);
  const [loadingVolume, setLoadingVolume] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState("Initializing GLORYS12V1...");
  const [error, setError] = useState<string | null>(null);

  // Selected query parameters (focused regional default for sub-second/fast interactive responsiveness)
  const [selectedDate, setSelectedDate] = useState("2026-06-23");
  const [selectedVariable, setSelectedVariable] = useState<OceanVariable>("thetao");
  // Coordinates supplied by YARA take priority; the regional defaults below are
  // only used when the app is opened directly without bounds in the URL.
  const [lonMin, setLonMin] = useState(incomingBounds?.lonMin ?? 70.0);
  const [lonMax, setLonMax] = useState(incomingBounds?.lonMax ?? 85.0);
  const [latMin, setLatMin] = useState(incomingBounds?.latMin ?? 8.0);
  const [latMax, setLatMax] = useState(incomingBounds?.latMax ?? 20.0);
  const [depthMin, setDepthMin] = useState(0.0);
  const [depthMax, setDepthMax] = useState(500.0);
  const [lod, setLod] = useState(1); // 0=Coarse, 1=Balanced, 2=Fine

  // 3D Volume Rendering defaults & dynamic colormap fitting
  const enabled = true;
  const mode = "volume" as const;
  const [tempMin, setTempMin] = useState(15);
  const [tempMax, setTempMax] = useState(32);
  const [opacity, setOpacity] = useState(1.0);
  const [chlIntensity, setChlIntensity] = useState(1.2);
  const [salinityWeight, setSalinityWeight] = useState(1.0);
  const [volumeRenderMode, setVolumeRenderMode] = useState<VolumeRenderMode>("temperature");
  const [showVolumeMarkers, setShowVolumeMarkers] = useState(true);
  const verticalExaggeration = 500;
  const steps = 256;

  // Profile & Point-Probe picking
  const [probePoint, setProbePoint] = useState<ProbePoint | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [verticalColumn, setVerticalColumn] = useState<VerticalColumnResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Depth Slicing state
  const [sliceMode, setSliceMode] = useState<"volume" | "layer">("volume");
  const [sliceStep, setSliceStep] = useState(100);
  const [activeSlice, setActiveSlice] = useState(1);

  // Track last payload hash to detect whether data actually changed
  const prevHashRef = useRef<string | null>(null);

  // AbortController for cancelling in-flight requests when date or region changes rapidly
  const abortControllerRef = useRef<AbortController | null>(null);
  const isInitialMountRef = useRef<boolean>(true);

  // ── Rollback refs ──────────────────────────────────────────────────────────
  // Tracks the variable that produced the last *successful* volumeData load.
  // On fetch failure we restore selectedVariable to this value so the selector
  // and the HUD badge never diverge from the actually-rendered geometry.
  const prevValidVariableRef = useRef<OceanVariable>("thetao");

  // When handleVariableChange fires it calls handleLoadVolume directly AND may
  // also call setSelectedDate (for climate-only vars). That date change would
  // trigger the selectedDate useEffect → a second (duplicate) fetch.
  // Setting this flag to true tells that effect to skip exactly one cycle.
  const skipNextDateEffectRef = useRef<boolean>(false);

  // ── Derived per-variable info ──────────────────────────────────────────────
  const varInfo = VARIABLE_CATALOGUE.find((v) => v.variable === selectedVariable);
  const is2d = volumeData?.meta.is_2d ?? varInfo?.is_2d ?? false;

  // ── Load volume callback ───────────────────────────────────────────────────
  const handleLoadVolume = useCallback(async (customParams?: Partial<{
    date: string;
    variable: OceanVariable;
    lonMin: number;
    lonMax: number;
    latMin: number;
    latMax: number;
    depthMin: number;
    depthMax: number;
    lod: number;
  }>) => {
    // Abort previous in-flight request if any to avoid race conditions
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoadingVolume(true);
    setError(null);

    const targetDate     = customParams?.date     ?? selectedDate;
    const targetVariable = customParams?.variable ?? selectedVariable;
    const qLonMin = customParams?.lonMin    ?? lonMin;
    const qLonMax = customParams?.lonMax    ?? lonMax;
    const qLatMin = customParams?.latMin    ?? latMin;
    const qLatMax = customParams?.latMax    ?? latMax;
    const qDepthMin = customParams?.depthMin ?? depthMin;
    const qDepthMax = customParams?.depthMax ?? depthMax;
    const qLod    = customParams?.lod      ?? lod;

    const varLabel = VARIABLE_CATALOGUE.find((v) => v.variable === targetVariable)?.label ?? targetVariable;
    setLoadingMessage(`Fetching ${varLabel} from backend...`);

    const t0 = performance.now();
    try {
      let vol: VolumeData;
      if (isOpendapVariable(targetVariable)) {
        // Route derived variables to the OPeNDAP endpoint
        setLoadingMessage(`Fetching ${varLabel} from OPeNDAP THREDDS...`);
        vol = await fetchSubsurfaceVolume({
          variable:         targetVariable,
          latMin:           qLatMin,
          latMax:           qLatMax,
          lonMin:           qLonMin,
          lonMax:           qLonMax,
          depthMin:         qDepthMin,
          depthMax:         qDepthMax,
          downsampleStride: Math.max(1, qLod),
        }, controller.signal);
      } else {
        setLoadingMessage(`Downloading Float32 volume for ${targetDate}...`);
        vol = await fetchVolume({
          date:     targetDate,
          variable: targetVariable,
          lonMin:   qLonMin,
          lonMax:   qLonMax,
          latMin:   qLatMin,
          latMax:   qLatMax,
          depthMin: qDepthMin,
          depthMax: qDepthMax,
          lod:      qLod,
        }, controller.signal);
      }
      const t1 = performance.now();

      setVolumeData(vol);

      // Record the variable that produced this successful load
      prevValidVariableRef.current = targetVariable;

      // Automatically fit colormap bounds to the incoming dataset range
      const vMin = vol.meta.value_min ?? vol.meta.temperature_min;
      const vMax = vol.meta.value_max ?? vol.meta.temperature_max;
      setTempMin(Number(vMin.toFixed(1)));
      setTempMax(Number(vMax.toFixed(1)));

      // Log download details and hash comparison
      const nVoxels = vol.meta.shape.depth * vol.meta.shape.lat * vol.meta.shape.lon;
      const currentHash = vol.meta.payload_hash ?? "N/A";
      const prevHash = prevHashRef.current;
      const dataChanged = prevHash === null
        ? "(first load)"
        : (currentHash !== prevHash
          ? `✅ DATA CHANGED (was ${prevHash})`
          : `❌ IDENTICAL PAYLOAD (hash unchanged: ${currentHash})`);
      prevHashRef.current = currentHash;

      console.log(
        `[GLORYS] Volume received:\n` +
        `  variable: ${vol.meta.variable} (${vol.meta.label ?? ""})\n` +
        `  date:     ${vol.meta.date}\n` +
        `  mode:     ${vol.meta.mode}\n` +
        `  is_2d:    ${vol.meta.is_2d ?? false}\n` +
        `  shape:    ${vol.meta.shape.lon}×${vol.meta.shape.lat}×${vol.meta.shape.depth} (${nVoxels} voxels)\n` +
        `  bytes:    ${vol.meta.byte_length} (${(vol.meta.byte_length / 1e6).toFixed(2)} MB Float32)\n` +
        `  range:    ${vMin.toFixed(2)} – ${vMax.toFixed(2)} ${vol.meta.units}\n` +
        `  hash:     ${currentHash}\n` +
        `  Δ data:   ${dataChanged}\n` +
        `  fetch ms: ${(t1 - t0).toFixed(0)} ms`
      );
    } catch (e: unknown) {
      const err = e as { name?: string; message?: string };
      if (err.name === "AbortError" || controller.signal.aborted) {
        console.log(`[GLORYS] Request aborted for date=${targetDate}`);
        return;
      }
      console.error("Volume loading failed:", e);
      const errMsg = err.message || String(e);
      setError(errMsg);

      // If continental landmass was selected, remove false ocean volume
      if (errMsg.includes("Terrestrial Landmass")) {
        setVolumeData(null);
      }

      // ── State rollback ────────────────────────────────────────────────────
      // The fetch failed (e.g. climate fixture missing). The volumeData still
      // holds the previous variable's geometry — keep it. Roll selectedVariable
      // back to the last successfully loaded variable so the HUD badge, the
      // variable selector highlight, and the rendered mesh stay consistent.
      // Only roll back if we actually have a previous valid dataset to show.
      setSelectedVariable((current) => {
        if (current !== prevValidVariableRef.current && volumeData !== null) {
          console.log(
            `[GLORYS] Fetch failed — rolling back variable selector ` +
            `from "${current}" → "${prevValidVariableRef.current}"`
          );
          return prevValidVariableRef.current;
        }
        return current;
      });
    } finally {
      // Only clear loading spinner if this is still the active in-flight request
      if (abortControllerRef.current === controller) {
        setLoadingVolume(false);
      }
    }
  }, [selectedDate, selectedVariable, lonMin, lonMax, latMin, latMax, depthMin, depthMax, lod]);

  // Initial load: fetch health, time-range, then first volume
  useEffect(() => {
    (async () => {
      try {
        setLoadingMessage("Checking GLORYS service health...");
        const h = await fetchHealth().catch(() => null);
        if (h) setHealth(h);

        setLoadingMessage("Querying GLORYS available dates...");
        const tr = await fetchTimeRange("thetao");
        setTimeRange(tr);

        // Set initial date to latest available date
        const initialDate = tr.end || "2026-06-23";
        setSelectedDate(initialDate);

        // Load initial volume. When YARA handed over a grid cell, pass it
        // explicitly so the first fetch targets that region rather than the
        // app's own default bounds.
        await handleLoadVolume({ date: initialDate, ...(incomingBounds ?? {}) });
        isInitialMountRef.current = false;
      } catch (e: unknown) {
        const err = e as { message?: string };
        setError(err.message ?? String(e));
        setLoadingVolume(false);
        isInitialMountRef.current = false;
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Dynamic Date Reactive Update:
  // Whenever selectedDate changes after initial mount, automatically re-fetch volume
  const handleLoadVolumeRef = useRef(handleLoadVolume);
  handleLoadVolumeRef.current = handleLoadVolume;

  useEffect(() => {
    if (isInitialMountRef.current) return;

    // Suppress this one cycle if a variable change already fired a load
    // (handleVariableChange sets this flag before calling setSelectedDate).
    if (skipNextDateEffectRef.current) {
      skipNextDateEffectRef.current = false;
      return;
    }

    // Small debounce (200ms) to allow rapid date scrubbing without saturating the connection
    const timer = setTimeout(() => {
      handleLoadVolumeRef.current({ date: selectedDate });
    }, 200);

    return () => clearTimeout(timer);
  }, [selectedDate]);

  // Variable change handler: when switching to climate-only variable, clamp date to Dec 2004;
  // when switching to OPeNDAP 3D variable, expand depth ceiling to 6,000m abyssal depth.
  const handleVariableChange = useCallback((newVar: OceanVariable) => {
    setSelectedVariable(newVar);

    // Keep top toolbar volumeRenderMode in 100% lockstep with selected variable
    if (newVar === "composite") {
      setVolumeRenderMode("composite");
    } else if (newVar === "so" || newVar === "salinity") {
      setVolumeRenderMode("salinity");
    } else if (newVar === "chl") {
      setVolumeRenderMode("chlorophyll");
    } else if (newVar === "thetao" || newVar === "temperature") {
      setVolumeRenderMode("temperature");
    }

    const newVarInfo = VARIABLE_CATALOGUE.find((v) => v.variable === newVar);

    let targetDate = selectedDate;
    if (newVarInfo?.climate_only) {
      // Clamp to December 2004 range
      if (selectedDate < "2004-12-01" || selectedDate > "2004-12-31") {
        targetDate = "2004-12-15";
        // Tell the selectedDate useEffect to skip this synthetic date change.
        // Without this flag, that effect would fire a second handleLoadVolume
        // call immediately after this one, producing duplicate error toasts.
        skipNextDateEffectRef.current = true;
        setSelectedDate(targetDate);
      }
    }

    let targetDepthMax = depthMax;
    if (isOpendapVariable(newVar)) {
      if (depthMax < 4000) {
        targetDepthMax = 6000.0;
        setDepthMax(6000.0);
      }
    } else {
      if (depthMax > 1500) {
        targetDepthMax = 500.0;
        setDepthMax(500.0);
      }
    }

    handleLoadVolume({ variable: newVar, date: targetDate, depthMax: targetDepthMax });
  }, [selectedDate, depthMax, handleLoadVolume]);

  // Globe click handler: snaps coordinates, updates state, and immediately triggers backend fetch
  const handleRegionSelect = useCallback(
    (coords: { lonMin: number; lonMax: number; latMin: number; latMax: number }) => {
      setLonMin(coords.lonMin);
      setLonMax(coords.lonMax);
      setLatMin(coords.latMin);
      setLatMax(coords.latMax);

      // Auto-load GLORYS volume immediately for the clicked grid box
      handleLoadVolume({
        lonMin: coords.lonMin,
        lonMax: coords.lonMax,
        latMin: coords.latMin,
        latMax: coords.latMax,
      });
    },
    [handleLoadVolume]
  );

  // Universal Point-Probe picking handler
  const handlePick = useCallback(async (probe: ProbePoint) => {
    setProbePoint(probe);
    setProfileLoading(true);

    let isLocalLand = Boolean(probe.is_land);

    // 1. Instant column profile extraction from local 3D volume buffer (zero latency)
    if (volumeData && volumeData.meta && volumeData.float32 && !volumeData.meta.is_2d) {
      const { meta, float32 } = volumeData;
      const latIdx = Math.max(0, Math.min(meta.shape.lat - 1, Math.round(probe.localV * (meta.shape.lat - 1))));
      const lonIdx = Math.max(0, Math.min(meta.shape.lon - 1, Math.round(probe.localU * (meta.shape.lon - 1))));
      const channels = meta.channel_count ?? (meta.is_multi_channel ? 4 : 1);

      const depthArr: number[] = [];
      const tempArr: (number | null)[] = [];
      let validCount = 0;

      for (let d = 0; d < meta.shape.depth; d++) {
        const idx = ((d * meta.shape.lat + latIdx) * meta.shape.lon + lonIdx) * (channels > 1 ? channels : 1);
        let val: number | null = null;
        if (channels >= 4) {
          const valid = float32[idx + 3];
          if (valid > 0.5) {
            val = Number((24.0 + float32[idx] * 8.0).toFixed(2));
          }
        } else {
          const raw = float32[idx];
          if (!isNaN(raw) && raw > -9000 && raw < 900000000) {
            val = raw;
          }
        }

        depthArr.push(meta.depth[d] ?? (meta.depth_min + (d / Math.max(1, meta.shape.depth - 1)) * (meta.depth_max - meta.depth_min)));
        if (val !== null) {
          tempArr.push(val);
          validCount++;
        } else {
          tempArr.push(null);
        }
      }

      if (validCount > 0) {
        setProfile({
          requested_latitude: probe.lat,
          requested_longitude: probe.lon,
          matched_latitude: probe.lat,
          matched_longitude: probe.lon,
          lat_index: latIdx,
          lon_index: lonIdx,
          depth: depthArr,
          temperature: tempArr,
          variable: selectedVariable,
        });
      }
    }

    // 2. Universal Click-to-Inspect: Fetch remote point probe & 3D subsurface vertical column
    try {
      const [pointRes, colData] = await Promise.allSettled([
        fetchPointProbe(probe.lat, probe.lon, probe.depth, selectedDate, selectedVariable),
        fetchVerticalColumn(probe.lat, probe.lon, 1000),
      ]);

      const pt = pointRes.status === "fulfilled" ? pointRes.value : null;
      const col = colData.status === "fulfilled" ? colData.value : null;

      // Authentic land classification: only true if verified by land mask
      const isLand = Boolean(pt?.is_land || col?.is_land);

      if (isLand) {
        setProbePoint((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            is_land: true,
            temperature: null,
            salinity: null,
            chlorophyll: null,
            voxelValue: null,
            message: pt?.message || col?.message || "⚠️ Terrestrial Landmass: Oceanographic data unavailable",
          };
        });
        setVerticalColumn({
          lat: probe.lat,
          lon: probe.lon,
          timestamp: "",
          source: col?.source || "GLORYS Land Mask",
          max_depth_m: 1000,
          profile: [],
          is_land: true,
          message: pt?.message || col?.message || "⚠️ Terrestrial Landmass: Oceanographic data unavailable",
        });
        setProfile(null);
      } else {
        if (col) {
          setVerticalColumn(col);
          if (col.profile && col.profile.length > 0) {
            let closestPt = col.profile[0];
            let minDiff = Infinity;
            for (const p of col.profile) {
              const diff = Math.abs(p.depth_m - probe.depth);
              if (diff < minDiff) {
                minDiff = diff;
                closestPt = p;
              }
            }

            setProbePoint((prev) => {
              if (!prev) return null;
              return {
                ...prev,
                is_land: false,
                temperature: pt?.temperature ?? closestPt.temperature ?? prev.temperature,
                salinity: pt?.salinity ?? closestPt.salinity ?? prev.salinity,
                chlorophyll: pt?.chlorophyll ?? closestPt.chlorophyll ?? prev.chlorophyll,
              };
            });
          }
        }
      }
    } catch (e) {
      console.warn("Probe multi-variable query fallback:", e);
    } finally {
      setProfileLoading(false);
    }
  }, [selectedVariable, selectedDate, volumeData]);

  const handleRenderModeSelect = (newMode: VolumeRenderMode) => {
    setVolumeRenderMode(newMode);
    const targetVar: OceanVariable =
      newMode === "composite" ? "composite" :
      newMode === "salinity" ? "so" :
      newMode === "chlorophyll" ? "chl" : "thetao";

    if (selectedVariable !== targetVar) {
      handleVariableChange(targetVar);
    }
  };

  const handleSelectVariable = (varId: string) => {
    if (varId === "composite") {
      handleRenderModeSelect("composite");
    } else if (varId === "so") {
      handleRenderModeSelect("salinity");
    } else if (varId === "chl") {
      handleRenderModeSelect("chlorophyll");
    } else {
      handleRenderModeSelect("temperature");
    }
  };

  const activeOceanVariable =
    volumeRenderMode === "composite" ? "composite" : selectedVariable;

  // Active slicing depth calculation
  const effectiveDepthMin = volumeData?.meta.depth_min ?? depthMin;
  const effectiveDepthMax = volumeData?.meta.depth_max ?? depthMax;
  const totalDepthSpan = Math.max(1, effectiveDepthMax - effectiveDepthMin);
  const maxSlices = Math.max(1, Math.floor(totalDepthSpan / Math.max(1, sliceStep)));
  const clampedSlice = Math.max(1, Math.min(activeSlice, maxSlices));
  const sliceStartM = effectiveDepthMin + (clampedSlice - 1) * sliceStep;
  const sliceEndM = Math.min(effectiveDepthMax, effectiveDepthMin + clampedSlice * sliceStep);
  const sliceCenterDepthM = Number(((sliceStartM + sliceEndM) / 2).toFixed(1));
  const sliceDepthNormalized = sliceMode === "layer"
    ? Math.max(0.0, Math.min(1.0, (sliceCenterDepthM - effectiveDepthMin) / totalDepthSpan))
    : 0.0;

  // Slicing synchronization callback
  const handleSliceChange = useCallback((newSlice: number) => {
    setActiveSlice(newSlice);

    // If probePoint is currently active, update its layerSummary synchronously
    if (volumeData && volumeData.float32) {
      const dMin = volumeData.meta.depth_min ?? depthMin;
      const dMax = volumeData.meta.depth_max ?? depthMax;
      const totalDepth = Math.max(1, dMax - dMin);
      const totalSlices = Math.max(1, Math.floor(totalDepth / Math.max(1, sliceStep)));
      const clamped = Math.max(1, Math.min(newSlice, totalSlices));
      const dStartM = dMin + (clamped - 1) * sliceStep;
      const dEndM = Math.min(dMax, dMin + clamped * sliceStep);
      const sDepthM = Number(((dStartM + dEndM) / 2).toFixed(1));
      const depthFrac = Math.max(0.0, Math.min(1.0, (sDepthM - dMin) / totalDepth));
      const dIdx = Math.max(0, Math.min(volumeData.meta.shape.depth - 1, Math.round(depthFrac * (volumeData.meta.shape.depth - 1))));

      const updatedSummary = calculateLayerSliceStats(
        volumeData,
        dIdx,
        clamped,
        totalSlices,
        dStartM,
        dEndM,
        sDepthM
      );

      setProbePoint((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          depth: sDepthM,
          layerSummary: updatedSummary,
        };
      });
    }
  }, [volumeData, depthMin, depthMax, sliceStep]);

  // Generate dynamic numerical layers and telemetry for LayerSliceHUD
  const numericLayers = useMemo<NumericLayerData[]>(() => {
    const dMin = effectiveDepthMin;
    const dMax = effectiveDepthMax;
    const bounds = {
      latMin: volumeData?.meta.latitude_min ?? latMin,
      latMax: volumeData?.meta.latitude_max ?? latMax,
      lonMin: volumeData?.meta.longitude_min ?? lonMin,
      lonMax: volumeData?.meta.longitude_max ?? lonMax,
      depthMin: dMin,
      depthMax: dMax,
    };

    if (volumeData && volumeData.float32 && volumeData.meta) {
      const dims = {
        width: volumeData.meta.shape.lon,
        height: volumeData.meta.shape.lat,
        depth: volumeData.meta.shape.depth,
      };
      const channels = volumeData.meta.channel_count ?? (volumeData.meta.is_multi_channel ? 4 : 1);
      return computeNumericLayers(volumeData.float32, dims, bounds, sliceStep, channels);
    }

    const safeThickness = Math.max(10, sliceStep);
    const totalDepth = Math.max(1, dMax - dMin);
    const count = Math.max(1, Math.ceil(totalDepth / safeThickness));
    const result: NumericLayerData[] = [];
    for (let i = 0; i < count; i++) {
      const start = Math.round(dMin + i * safeThickness);
      const end = Math.round(Math.min(dMax, dMin + (i + 1) * safeThickness));
      const depthRatio = (start + end) / (2 * Math.max(1, dMax));
      const avgT = Number((28.0 * Math.exp(-depthRatio * 2.0) + 4.0).toFixed(2));
      result.push({
        layerNumber: i + 1,
        depthMin: start,
        depthMax: end,
        latMin: bounds.latMin,
        latMax: bounds.latMax,
        lonMin: bounds.lonMin,
        lonMax: bounds.lonMax,
        avgTemp: avgT,
        minTemp: Number((avgT - 2.0).toFixed(2)),
        maxTemp: Number((avgT + 2.0).toFixed(2)),
        avgSalinity: Number((34.6 + depthRatio * 0.8).toFixed(2)),
        avgChlorophyll: Number(Math.max(0.01, 1.85 * Math.exp(-depthRatio * 4.5)).toFixed(3)),
        validVoxelCount: 0,
      });
    }
    return result;
  }, [effectiveDepthMin, effectiveDepthMax, latMin, latMax, lonMin, lonMax, sliceStep, volumeData]);

  const handleSelectDepthLayer = useCallback((layerNum: number) => {
    if (sliceMode !== "layer") {
      setSliceMode("layer");
    }
    handleSliceChange(layerNum);
  }, [sliceMode, handleSliceChange]);

  // Resolved value range from loaded data
  const displayMin = volumeData?.meta.value_min ?? volumeData?.meta.temperature_min ?? tempMin;
  const displayMax = volumeData?.meta.value_max ?? volumeData?.meta.temperature_max ?? tempMax;
  const displayUnit = volumeData?.meta.units ?? varInfo?.unit ?? "°C";
  const displayLabel = volumeData?.meta.label ?? varInfo?.label ?? "Potential Temperature";

  return (
    <div style={{ display: "flex", width: "100%", height: "100%", position: "relative" }}>
      <div style={{ position: "relative", flex: 1 }}>
        <VolumeViewer
          volumeData={enabled ? volumeData : null}
          regionBounds={{
            minLat: volumeData?.meta.latitude_min ?? latMin,
            maxLat: volumeData?.meta.latitude_max ?? latMax,
            minLon: volumeData?.meta.longitude_min ?? lonMin,
            maxLon: volumeData?.meta.longitude_max ?? lonMax,
            minDepth: volumeData?.meta.depth_min ?? depthMin,
            maxDepth: volumeData?.meta.depth_max ?? depthMax,
          }}
          tempMin={tempMin}
          tempMax={tempMax}
          opacity={opacity}
          steps={steps}
          verticalExaggeration={verticalExaggeration}
          mode={mode}
          sliceDepthNormalized={sliceDepthNormalized}
          sliceDepthM={sliceCenterDepthM}
          uIsLayerMode={sliceMode === "layer"}
          sliceStep={sliceStep}
          activeSlice={clampedSlice}
          is2d={is2d}
          probePoint={probePoint}
          onPick={handlePick}
          onSliceSelect={handleSliceChange}
          renderMode={volumeRenderMode}
          chlIntensity={chlIntensity}
          salinityWeight={salinityWeight}
          showVolumeMarkers={showVolumeMarkers}
        />

        {/* 1. Unified Top Navigation & Controls Bar */}
        <div
          className="absolute top-4 left-4 right-4 z-30 flex flex-wrap items-center justify-between gap-3 pointer-events-none"
          style={{
            position: "absolute",
            top: 16,
            left: 16,
            right: 16,
            zIndex: 30,
            display: "flex",
            flexWrap: "nowrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            pointerEvents: "none",
          }}
        >
          {/* Left: Dataset Metadata Badge */}
          <div
            className="pointer-events-auto flex flex-col gap-1 bg-slate-950/85 backdrop-blur-md border border-cyan-500/30 rounded-xl px-4 py-2 shadow-xl"
            style={{
              pointerEvents: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "rgba(2, 6, 23, 0.85)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(6, 182, 212, 0.3)",
              borderRadius: 12,
              padding: "8px 16px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
              flexShrink: 0,
            }}
          >
            <div
              className="flex items-center gap-2 text-xs"
              style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}
            >
              <span
                className="font-bold tracking-wider text-cyan-400"
                style={{ fontWeight: 700, letterSpacing: "0.05em", color: "#22d3ee" }}
              >
                GLORYS12V1
              </span>
              <span
                className="bg-cyan-950/80 border border-cyan-600/40 text-cyan-300 px-2 py-0.5 rounded text-[11px] font-mono"
                style={{
                  background: "rgba(8, 47, 73, 0.8)",
                  border: "1px solid rgba(8, 145, 178, 0.4)",
                  color: "#67e8f9",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontFamily: "IBM Plex Mono, monospace",
                }}
              >
                {volumeData?.meta.date || selectedDate || "2026-06-23"}
              </span>
              <span
                className="text-slate-300 font-medium"
                style={{ color: "#cbd5e1", fontWeight: 500 }}
              >
                {activeOceanVariable === "composite"
                  ? "Multi-Variable Composite"
                  : displayLabel}
              </span>
              {is2d && (
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    background: "rgba(245, 158, 11, 0.15)",
                    color: "#f59e0b",
                    padding: "1px 5px",
                    borderRadius: 3,
                    border: "1px solid rgba(245, 158, 11, 0.4)",
                  }}
                >
                  2D
                </span>
              )}
            </div>
            <div
              className="text-[11px] text-slate-400 flex items-center gap-2 font-mono"
              style={{
                fontSize: 11,
                color: "#94a3b8",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontFamily: "IBM Plex Mono, monospace",
              }}
            >
              <span>
                Range:{" "}
                <strong className="text-slate-200" style={{ color: "#e2e8f0" }}>
                  {displayMin.toFixed(1)} – {displayMax.toFixed(1)} {displayUnit}
                </strong>
              </span>
              <span className="text-slate-600" style={{ color: "#475569" }}>•</span>
              {!is2d && (
                <>
                  <span>
                    Depth:{" "}
                    {volumeData
                      ? `${volumeData.meta.depth_min.toFixed(1)}–${volumeData.meta.depth_max.toFixed(1)} m`
                      : "0.5–453.9 m"}
                  </span>
                  <span className="text-slate-600" style={{ color: "#475569" }}>•</span>
                </>
              )}
              <span>
                {volumeData
                  ? (is2d
                      ? `${volumeData.meta.shape.lon}×${volumeData.meta.shape.lat} px`
                      : `${volumeData.meta.shape.lon}×${volumeData.meta.shape.lat}×${volumeData.meta.shape.depth} voxels`)
                  : "61×61×31 voxels"}
              </span>
            </div>
          </div>

          {/* Right: Opacity & 3D Feature Pin Controls */}
          <div
            className="pointer-events-auto flex items-center gap-3.5 bg-slate-950/85 backdrop-blur-md border border-slate-800 rounded-xl px-3.5 py-2 shadow-xl"
            style={{
              pointerEvents: "auto",
              display: "flex",
              alignItems: "center",
              gap: 14,
              background: "rgba(2, 6, 23, 0.85)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(30, 41, 59, 0.8)",
              borderRadius: 12,
              padding: "8px 14px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
              flexShrink: 0,
            }}
          >
            <div
              className="flex items-center gap-2"
              style={{ display: "flex", alignItems: "center", gap: 8 }}
            >
              <span
                className="text-[11px] text-slate-400 font-medium"
                style={{ fontSize: 11, color: "#94a3b8", fontWeight: 500 }}
              >
                Opacity
              </span>
              <input
                type="range"
                min="0.1"
                max="3.0"
                step="0.05"
                value={opacity}
                onChange={(e) => setOpacity(parseFloat(e.target.value))}
                className="w-20 accent-cyan-400 h-1 bg-slate-700 rounded-lg cursor-pointer"
                style={{ width: 80, height: 4, accentColor: "#22d3ee", cursor: "pointer" }}
              />
              <span
                className="text-[11px] font-mono text-cyan-300 w-9"
                style={{
                  fontSize: 11,
                  fontFamily: "IBM Plex Mono, monospace",
                  color: "#67e8f9",
                  width: 36,
                }}
              >
                {opacity.toFixed(2)}×
              </span>
            </div>

            <div
              className="h-4 w-px bg-slate-800"
              style={{ height: 16, width: 1, background: "rgba(51, 65, 85, 0.8)" }}
            />

            <label
              className="flex items-center gap-2 text-[11px] text-slate-300 font-medium cursor-pointer"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 11,
                color: "#cbd5e1",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={showVolumeMarkers}
                onChange={(e) => setShowVolumeMarkers(e.target.checked)}
                className="rounded border-slate-700 text-cyan-500 focus:ring-0 bg-slate-800"
                style={{ accentColor: "#22d3ee", cursor: "pointer" }}
              />
              <span>3D Pins</span>
            </label>
          </div>
        </div>

        {/* 2. Colormap Legend Docked Below Metadata */}
        <ColorBar
          min={displayMin}
          max={displayMax}
          units={displayUnit}
          label={displayLabel}
          renderMode={volumeRenderMode}
          salinityWeight={salinityWeight}
          onSalinityWeightChange={setSalinityWeight}
          chlIntensity={chlIntensity}
          onChlIntensityChange={setChlIntensity}
        />

        {/* Local Fixture Warning banner (if applicable) */}
        {volumeData?.meta.mode === "local" && !varInfo?.climate_only && (
          <div
            style={{
              position: "absolute",
              top: volumeRenderMode === "composite" ? 250 : 185,
              left: 16,
              zIndex: 20,
              pointerEvents: "auto",
              maxWidth: 300,
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid rgba(239, 68, 68, 0.6)",
              borderRadius: 8,
              padding: "6px 12px",
              color: "#fca5a5",
              fontSize: 10.5,
              fontWeight: 600,
              letterSpacing: "0.02em",
              boxShadow: "0 4px 15px rgba(0,0,0,0.5)",
            }}
          >
            ⚠ LOCAL FIXTURE — Copernicus credentials not configured.<br />
            <span style={{ fontWeight: 400, opacity: 0.85 }}>
              Changing date/region has NO effect. Set credentials in <code>.env</code> for live data.
            </span>
          </div>
        )}

        {/* Terrestrial Landmass Warning Modal Overlay */}
        {error && error.includes("Terrestrial Landmass") && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 40,
              background: "rgba(15, 23, 42, 0.94)",
              backdropFilter: "blur(16px)",
              border: "1px solid rgba(245, 158, 11, 0.6)",
              borderRadius: 14,
              padding: "24px 30px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 12,
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.8)",
              textAlign: "center",
              maxWidth: 440,
              pointerEvents: "auto",
              animation: "fadeIn 0.25s ease-out",
            }}
          >
            <div style={{ fontSize: 36, filter: "drop-shadow(0 2px 8px rgba(245, 158, 11, 0.4))" }}>⚠️</div>
            <div style={{ color: "#fbbf24", fontWeight: 700, fontSize: 16, letterSpacing: "0.02em" }}>
              Terrestrial Landmass Selected
            </div>
            <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5 }}>
              The selected region is situated on continental land. Oceanographic parameters (salinity, temperature, chlorophyll) are unavailable for terrestrial coordinates.
            </div>
            <div style={{ color: "#94a3b8", fontSize: 11, background: "rgba(255,255,255,0.05)", padding: "6px 12px", borderRadius: 6 }}>
              💡 Select coastal waters or open ocean on the mini-globe to resume 3D volumetric analysis.
            </div>
          </div>
        )}

        {/* Global Loading Overlay */}
        {loadingVolume && (
          <div
            style={{
              position: "absolute",
              bottom: 24,
              left: 16,
              background: "rgba(6, 16, 25, 0.9)",
              border: "1px solid var(--accent)",
              padding: "10px 16px",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--accent)",
              display: "flex",
              alignItems: "center",
              gap: 10,
              boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
            }}
          >
            <div
              style={{
                width: 14,
                height: 14,
                border: "2px solid var(--accent)",
                borderTopColor: "transparent",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }}
            />
            <span>{loadingMessage}</span>
          </div>
        )}

        <PointInspectionCard
          probe={probePoint}
          profile={profile}
          verticalColumn={verticalColumn}
          loading={profileLoading}
          variable={selectedVariable}
          volumeData={volumeData}
          activeSlice={clampedSlice}
          totalSlices={maxSlices}
          sliceStep={sliceStep}
          onSliceChange={handleSliceChange}
          onClose={() => {
            setProbePoint(null);
            setProfile(null);
            setVerticalColumn(null);
          }}
        />
      </div>

      <Controls
        timeRange={timeRange}
        health={health}
        meta={volumeData?.meta ?? null}
        volumeData={volumeData}
        selectedDate={selectedDate}
        onDateChange={setSelectedDate}
        selectedVariable={selectedVariable}
        onVariableChange={handleVariableChange}
        lonMin={lonMin}
        onLonMinChange={setLonMin}
        lonMax={lonMax}
        onLonMaxChange={setLonMax}
        latMin={latMin}
        onLatMinChange={setLatMin}
        latMax={latMax}
        onLatMaxChange={setLatMax}
        depthMin={depthMin}
        onDepthMinChange={setDepthMin}
        depthMax={depthMax}
        onDepthMaxChange={setDepthMax}
        lod={lod}
        onLodChange={setLod}
        onSelectRegion={handleRegionSelect}
        onPickPoint={handlePick}
        onLoadVolume={() => handleLoadVolume()}
        loading={loadingVolume}
        loadingMessage={loadingMessage}
        error={error}
        sliceMode={sliceMode}
        onSliceModeChange={setSliceMode}
        sliceStep={sliceStep}
        onSliceStepChange={(step) => {
          setSliceStep(step);
          setActiveSlice(1); // Reset slice when step changes
        }}
        activeSlice={activeSlice}
        onActiveSliceChange={setActiveSlice}
      />

      {/* Top-Right Dynamic Numerical Layer Slicing Dropdown & Telemetry HUD Card */}
      {!is2d && numericLayers.length > 0 && (
        <LayerSliceHUD
          layers={numericLayers}
          selectedLayerNumber={clampedSlice}
          onSelectLayer={handleSelectDepthLayer}
          datasetName={volumeData?.meta?.dataset || "GLORYS12V1"}
          dateStr={selectedDate}
        />
      )}
    </div>
  );
}
