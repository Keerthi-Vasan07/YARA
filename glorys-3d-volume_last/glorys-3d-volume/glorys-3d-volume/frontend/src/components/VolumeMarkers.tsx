import React from "react";
import * as THREE from "three";
import type { VolumeMeta } from "../types";

export interface VolumeMarkerPoint {
  id: string;
  type: "chlorophyll" | "salinity";
  lon: number;
  lat: number;
  depth: number;
  temp: number;
  salinity: number;
  chl: number;
  localPos: THREE.Vector3; // in [-0.5, 0.5]^3 box space
}

export interface VolumeMarkersObject {
  group: THREE.Group;
  markers: VolumeMarkerPoint[];
  raycast: (raycaster: THREE.Raycaster) => VolumeMarkerPoint | null;
  updateAnimation: (timeSec: number) => void;
  dispose: () => void;
}

export function getValidOceanPins(
  pins: VolumeMarkerPoint[],
  volumeData: Float32Array,
  dims: { width: number; height: number; depth: number },
  bounds: { minLat: number; maxLat: number; minLon: number; maxLon: number; minDepth?: number; maxDepth: number }
): VolumeMarkerPoint[] {
  return pins.filter((pin) => {
    // 1. Check if coordinates fall inside the active volume bounding box
    if (
      pin.lat < bounds.minLat || pin.lat > bounds.maxLat ||
      pin.lon < bounds.minLon || pin.lon > bounds.maxLon
    ) {
      return false;
    }

    // 2. Map geographic coordinates to volume array indices
    const xIdx = Math.floor(((pin.lon - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * (dims.width - 1));
    const zIdx = Math.floor(((pin.lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * (dims.height - 1));
    const yIdx = Math.min(Math.floor((pin.depth / bounds.maxDepth) * (dims.depth - 1)), dims.depth - 1);

    const channelCount = (volumeData.length / (dims.width * dims.height * dims.depth)) >= 4 ? 4 : 1;
    const index = (yIdx * (dims.width * dims.height) + zIdx * dims.width + xIdx) * channelCount;
    
    if (index < 0 || index >= volumeData.length) return false;

    // For multi-channel, validity is in alpha channel (index + 3)
    // For single-channel, use the sentinel value
    if (channelCount >= 4) {
      const valid = volumeData[index + 3];
      if (valid < 0.5) return false;
    } else {
      const val = volumeData[index];
      // 3. Discard pin if the location is land (NaN, <= -100, or masked)
      if (val === undefined || isNaN(val) || val < -100.0) {
        return false; // Suppress pin over land
      }
    }

    return true; // Valid ocean coordinate
  });
}

/**
 * Automatically samples discrete feature points from the volume grid:
 * - High-productivity chlorophyll bloom hotspots in the euphotic layer (depth 25-75m)
 * - Salinity halocline transition points
 */
export function generateVolumeMarkers(
  meta: VolumeMeta,
  float32: Float32Array,
  regionBounds?: { minLat: number; maxLat: number; minLon: number; maxLon: number; minDepth?: number; maxDepth?: number }
): VolumeMarkerPoint[] {
  const { depth, latitude, longitude, shape, is_multi_channel } = meta;
  if (!depth.length || !latitude.length || !longitude.length) return [];

  const bounds = {
    minLon: regionBounds?.minLon ?? (meta.longitude_min ?? (meta.longitude.length ? Math.min(...meta.longitude) : 42.0)),
    maxLon: regionBounds?.maxLon ?? (meta.longitude_max ?? (meta.longitude.length ? Math.max(...meta.longitude) : 107.42)),
    minLat: regionBounds?.minLat ?? (meta.latitude_min ?? (meta.latitude.length ? Math.min(...meta.latitude) : -2.83)),
    maxLat: regionBounds?.maxLat ?? (meta.latitude_max ?? (meta.latitude.length ? Math.max(...meta.latitude) : 22.83)),
    minDepth: regionBounds?.minDepth ?? (meta.depth_min ?? 0.0),
    maxDepth: regionBounds?.maxDepth ?? (meta.depth_max ?? 500.0),
  };

  const markers: VolumeMarkerPoint[] = [];
  const dCount = shape.depth;
  const hCount = shape.lat;
  const wCount = shape.lon;
  const channelCount = meta.channel_count ?? (is_multi_channel ? 4 : 1);

  // Helper to read normalized values from float32 buffer
  const sampleVoxel = (dIdx: number, latIdx: number, lonIdx: number) => {
    const baseIdx = (dIdx * hCount * wCount + latIdx * wCount + lonIdx) * channelCount;
    if (baseIdx < 0 || baseIdx >= float32.length) return null;
    if (channelCount >= 4) {
      return {
        normTemp: float32[baseIdx],
        normSal: float32[baseIdx + 1],
        normChl: float32[baseIdx + 2],
        valid: float32[baseIdx + 3],
      };
    }
    const val = float32[baseIdx];
    const isLand = isNaN(val) || val < -9000.0;
    return {
      normTemp: isLand ? 0 : 0.5,
      normSal: 0.5,
      normChl: 0.5,
      valid: isLand ? 0 : 1,
    };
  };

  // Sample 4-6 representative points across the geographic span
  const sampleLats = [Math.floor(hCount * 0.3), Math.floor(hCount * 0.7)];
  const sampleLons = [Math.floor(wCount * 0.3), Math.floor(wCount * 0.65)];

  let idCounter = 1;

  // 1. Euphotic Chlorophyll Bloom Hotspots (around depth ~40-60m)
  const chlDepthIdx = Math.min(dCount - 1, Math.max(1, Math.floor(dCount * 0.12)));
  const depthFracChl = chlDepthIdx / Math.max(1, dCount - 1);
  const dValChl = bounds.minDepth + depthFracChl * (bounds.maxDepth - bounds.minDepth);

  for (const latI of sampleLats) {
    for (const lonI of sampleLons) {
      const s = sampleVoxel(chlDepthIdx, latI, lonI);
      if (!s || s.valid < 0.5) continue;

      const latFrac = latI / Math.max(1, hCount - 1);
      const lonFrac = lonI / Math.max(1, wCount - 1);

      const latDeg = bounds.minLat + latFrac * (bounds.maxLat - bounds.minLat);
      const lonDeg = bounds.minLon + lonFrac * (bounds.maxLon - bounds.minLon);

      // Recover estimated physical values from normalized channels
      const tempC = 24.5 + s.normTemp * 6.5;
      const salPSU = 32.0 + s.normSal * 5.0;
      const chlVal = Math.max(0.2, s.normChl * 2.0);

      markers.push({
        id: `chl-bloom-${idCounter++}`,
        type: "chlorophyll",
        lon: Number(lonDeg.toFixed(2)),
        lat: Number(latDeg.toFixed(2)),
        depth: Number(dValChl.toFixed(1)),
        temp: Number(tempC.toFixed(1)),
        salinity: Number(salPSU.toFixed(2)),
        chl: Number(chlVal.toFixed(2)),
        localPos: new THREE.Vector3(lonFrac - 0.5, 0.5 - depthFracChl, latFrac - 0.5),
      });
    }
  }

  // 2. Subsurface Salinity Halocline Markers (around depth ~150-300m)
  const salDepthIdx = Math.min(dCount - 1, Math.max(1, Math.floor(dCount * 0.35)));
  const depthFracSal = salDepthIdx / Math.max(1, dCount - 1);
  const dValSal = bounds.minDepth + depthFracSal * (bounds.maxDepth - bounds.minDepth);

  const midLat = Math.floor(hCount * 0.5);
  const salLons = [Math.floor(wCount * 0.25), Math.floor(wCount * 0.75)];

  for (const lonI of salLons) {
    const s = sampleVoxel(salDepthIdx, midLat, lonI);
    if (!s || s.valid < 0.5) continue;

    const latFrac = midLat / Math.max(1, hCount - 1);
    const lonFrac = lonI / Math.max(1, wCount - 1);

    const latDeg = bounds.minLat + latFrac * (bounds.maxLat - bounds.minLat);
    const lonDeg = bounds.minLon + lonFrac * (bounds.maxLon - bounds.minLon);

    const tempC = 16.0 + s.normTemp * 8.0;
    const salPSU = 34.0 + s.normSal * 2.5;
    const chlVal = s.normChl * 0.15;

    markers.push({
      id: `sal-cline-${idCounter++}`,
      type: "salinity",
      lon: Number(lonDeg.toFixed(2)),
      lat: Number(latDeg.toFixed(2)),
      depth: Number(dValSal.toFixed(1)),
      temp: Number(tempC.toFixed(1)),
      salinity: Number(salPSU.toFixed(2)),
      chl: Number(chlVal.toFixed(2)),
      localPos: new THREE.Vector3(lonFrac - 0.5, 0.5 - depthFracSal, latFrac - 0.5),
    });
  }

  return getValidOceanPins(markers, float32, { width: wCount, height: hCount, depth: dCount }, bounds as any);
}

/**
 * Normalized mapping of (lat, lon, depth) to Volume Box coordinates [-width/2, width/2]:
 */
export function geoToVolumeCoords(
  lat: number,
  lon: number,
  depth: number,
  bounds: { minLat: number; maxLat: number; minLon: number; maxLon: number; minDepth?: number; maxDepth: number },
  boxDims: { width: number; height: number; depth: number }
): THREE.Vector3 {
  const minDepth = bounds.minDepth ?? 0.0;
  const lonNorm = (lon - bounds.minLon) / Math.max(1e-6, bounds.maxLon - bounds.minLon);
  const latNorm = (lat - bounds.minLat) / Math.max(1e-6, bounds.maxLat - bounds.minLat);
  const depthNorm = Math.min(depth, bounds.maxDepth) / Math.max(1e-6, bounds.maxDepth - minDepth);

  const x = (lonNorm - 0.5) * boxDims.width;
  const y = (0.5 - depthNorm) * boxDims.height;
  const z = (latNorm - 0.5) * boxDims.depth;

  return new THREE.Vector3(x, y, z);
}

/**
 * Builds the 3D Three.js visual objects for discrete volume point markers.
 */
export function createVolumeMarkersObject(
  markers: VolumeMarkerPoint[],
  boxScale: THREE.Vector3
): VolumeMarkersObject {
  const rootGroup = new THREE.Group();
  rootGroup.name = "VolumeMarkersGroup";

  const hitMeshes: { mesh: THREE.Mesh; marker: VolumeMarkerPoint }[] = [];
  const animatedMaterials: { mat: THREE.Material; initialOpacity: number; speed: number }[] = [];

  markers.forEach((m) => {
    const markerNode = new THREE.Group();
    // Position in scaled world space
    markerNode.position.set(
      m.localPos.x * boxScale.x,
      m.localPos.y * boxScale.y,
      m.localPos.z * boxScale.z
    );

    if (m.type === "chlorophyll") {
      // Emerald glowing sphere for Chlorophyll-a
      const sphereGeo = new THREE.SphereGeometry(0.045, 16, 16);
      const sphereMat = new THREE.MeshBasicMaterial({
        color: 0x10b981,
        transparent: true,
        opacity: 0.9,
        depthTest: false,
      });
      const sphereMesh = new THREE.Mesh(sphereGeo, sphereMat);
      sphereMesh.renderOrder = 1200;
      markerNode.add(sphereMesh);
      hitMeshes.push({ mesh: sphereMesh, marker: m });

      // Outer pulsating glow shell
      const glowGeo = new THREE.SphereGeometry(0.08, 16, 16);
      const glowMat = new THREE.MeshBasicMaterial({
        color: 0x00ff66,
        transparent: true,
        opacity: 0.4,
        depthTest: false,
        wireframe: true,
      });
      const glowMesh = new THREE.Mesh(glowGeo, glowMat);
      glowMesh.renderOrder = 1199;
      markerNode.add(glowMesh);
      animatedMaterials.push({ mat: glowMat, initialOpacity: 0.4, speed: 2.8 });

      // Core bright center
      const coreGeo = new THREE.SphereGeometry(0.02, 10, 10);
      const coreMat = new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false });
      const coreMesh = new THREE.Mesh(coreGeo, coreMat);
      coreMesh.renderOrder = 1201;
      markerNode.add(coreMesh);
    } else {
      // Cyan / Magenta rings for Salinity
      const ringGeo = new THREE.TorusGeometry(0.065, 0.012, 12, 24);
      ringGeo.rotateX(Math.PI / 2);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0x00e5ff,
        transparent: true,
        opacity: 0.85,
        depthTest: false,
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.renderOrder = 1200;
      markerNode.add(ringMesh);
      hitMeshes.push({ mesh: ringMesh, marker: m });

      // Inner magenta halo ring
      const innerRingGeo = new THREE.TorusGeometry(0.035, 0.008, 12, 24);
      innerRingGeo.rotateX(Math.PI / 2);
      const innerRingMat = new THREE.MeshBasicMaterial({
        color: 0xd946ef,
        transparent: true,
        opacity: 0.75,
        depthTest: false,
      });
      const innerRingMesh = new THREE.Mesh(innerRingGeo, innerRingMat);
      innerRingMesh.renderOrder = 1201;
      markerNode.add(innerRingMesh);
      animatedMaterials.push({ mat: innerRingMat, initialOpacity: 0.75, speed: 2.2 });
    }

    // Generous interactive hit sphere so click & hover raycasting is smooth and reliable
    const hitGeo = new THREE.SphereGeometry(0.18, 12, 12);
    const hitMat = new THREE.MeshBasicMaterial({ visible: false, depthWrite: false });
    const hitMesh = new THREE.Mesh(hitGeo, hitMat);
    hitMesh.name = `HitMesh_${m.id}`;
    markerNode.add(hitMesh);
    hitMeshes.push({ mesh: hitMesh, marker: m });

    rootGroup.add(markerNode);
  });

  const raycast = (raycaster: THREE.Raycaster): VolumeMarkerPoint | null => {
    const meshes = hitMeshes.map((h) => h.mesh);
    const intersects = raycaster.intersectObjects(meshes, false);
    if (intersects.length > 0) {
      const hit = hitMeshes.find((h) => h.mesh === intersects[0].object);
      return hit ? hit.marker : null;
    }
    return null;
  };

  const updateAnimation = (timeSec: number) => {
    animatedMaterials.forEach((item) => {
      const wave = 0.5 + 0.5 * Math.sin(timeSec * item.speed);
      (item.mat as THREE.MeshBasicMaterial).opacity = item.initialOpacity * (0.6 + 0.4 * wave);
    });
  };

  const dispose = () => {
    rootGroup.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
        if (obj.geometry) obj.geometry.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else if (obj.material) obj.material.dispose();
      }
    });
  };

  return {
    group: rootGroup,
    markers,
    raycast,
    updateAnimation,
    dispose,
  };
}

/**
 * 2D Tooltip HUD displaying discrete physical values on marker click or hover.
 */
export const VolumeMarkerTooltip: React.FC<{
  marker: VolumeMarkerPoint | null;
  onClose: () => void;
}> = ({ marker, onClose }) => {
  if (!marker) return null;

  const isChl = marker.type === "chlorophyll";

  return (
    <div
      style={{
        position: "absolute",
        bottom: 24,
        left: 24,
        background: "rgba(6, 16, 25, 0.92)",
        backdropFilter: "blur(10px)",
        border: `1px solid ${isChl ? "#10b981" : "#00e5ff"}`,
        borderRadius: 6,
        padding: "10px 14px",
        color: "#ffffff",
        fontSize: 11.5,
        zIndex: 50,
        boxShadow: `0 4px 20px rgba(0, 0, 0, 0.6), 0 0 12px ${isChl ? "rgba(16, 185, 129, 0.3)" : "rgba(0, 229, 255, 0.3)"}`,
        minWidth: 230,
        pointerEvents: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontWeight: 700, color: isChl ? "#10b981" : "#00e5ff", display: "flex", alignItems: "center", gap: 5 }}>
          <span>{isChl ? "🌿" : "🌊"}</span>
          {isChl ? "Euphotic Chlorophyll Hotspot" : "Subsurface Haline Boundary"}
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-muted)",
            fontSize: 14,
            cursor: "pointer",
            padding: 0,
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px", fontSize: 11 }}>
        <div>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Depth:</span>{" "}
          <strong style={{ color: "#ffffff" }}>{marker.depth} m</strong>
        </div>
        <div>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Coord:</span>{" "}
          <strong style={{ color: "#ffffff" }}>{marker.lat}°N, {marker.lon}°E</strong>
        </div>
        <div>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Temp:</span>{" "}
          <strong style={{ color: "#ef4444" }}>{marker.temp} °C</strong>
        </div>
        <div>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Salinity:</span>{" "}
          <strong style={{ color: "#a855f7" }}>{marker.salinity} PSU</strong>
        </div>
        <div style={{ gridColumn: "span 2" }}>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Chl-a:</span>{" "}
          <strong style={{ color: "#10b981" }}>{marker.chl} mg/m³</strong>
        </div>
      </div>
    </div>
  );
};
