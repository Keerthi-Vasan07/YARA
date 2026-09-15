/**
 * Globe.tsx
 *
 * Interactive 3D Earth Globe for GLORYS ocean region selection.
 * - Features raycasting click/touch handler to extract (lat, lon).
 * - Snaps coordinates to uniform grid bounding box (5° or 10° step size).
 * - Highlights clicked bounding box on the globe surface.
 * - Automatically triggers region updates and GLORYS volume loading.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ProbeVariable, VerticalColumnResponse, ProbePoint } from "../types";
import { fetchVerticalColumn } from "../api";
import { createVerticalColumnMesh, Column3DObject } from "./VerticalProfileColumn";
import SubsurfaceColumnHUD from "./SubsurfaceColumnHUD";
import {
  createDatasetBoundingBox,
  DatasetBoundingBoxObject,
  DEFAULT_DATASET_BOUNDS,
} from "./DatasetBoundingBox";
import {
  createLocationSurfaceMarker,
  LocationMarkerObject,
} from "./LocationSurfaceMarker";

export interface GlobeProps {
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
  onSelectRegion: (coords: {
    lonMin: number;
    lonMax: number;
    latMin: number;
    latMax: number;
  }) => void;
  onPickPoint?: (probe: ProbePoint) => void;
  disabled?: boolean;
}

const GLOBE_RADIUS = 1.0;

/**
 * Convert (lat, lon) in degrees to a 3D point on a sphere of radius R.
 *   lat ∈ [-90, +90], lon ∈ [-180, +180]
 *   y = north-south
 *   x = east-west (sin lon)
 *   z = prime meridian (cos lon)
 */
function latLonToVector3(latDeg: number, lonDeg: number, radius: number): THREE.Vector3 {
  const phi = (90 - latDeg) * (Math.PI / 180);
  const theta = (lonDeg + 180) * (Math.PI / 180);

  // x points East, y points North, z points Prime Meridian / Antimeridian
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);

  return new THREE.Vector3(x, y, z);
}

/**
 * Convert a 3D point in globe local space back to (lat, lon) in degrees.
 */
function vector3ToLatLon(v: THREE.Vector3): { lat: number; lon: number } {
  const norm = v.clone().normalize();
  // y = cos(phi) => phi = acos(y)
  const phi = Math.acos(Math.max(-1, Math.min(1, norm.y)));
  const lat = 90 - phi * (180 / Math.PI);

  // x = -sin(phi)*cos(theta), z = sin(phi)*sin(theta)
  // theta = atan2(z, -x)
  let theta = Math.atan2(norm.z, -norm.x);
  let lon = theta * (180 / Math.PI) - 180;

  // Normalize lon to [-180, 180]
  while (lon < -180) lon += 360;
  while (lon > 180) lon -= 360;

  return { lat, lon };
}

// Earth texture URLs — Blue Marble equirectangular + specular map.
// Local copies in public/textures/ ensure instant offline rendering with zero network latency.
// jsDelivr GitHub CDN is provided as transparent fallback.
const EARTH_TEXTURE_LOCAL = "/textures/earth_atmos_2048.jpg";
const EARTH_TEXTURE_CDN =
  "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r169/examples/textures/planets/earth_atmos_2048.jpg";
const EARTH_SPECULAR_LOCAL = "/textures/earth_specular_2048.jpg";
const EARTH_SPECULAR_CDN =
  "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r169/examples/textures/planets/earth_specular_2048.jpg";

/**
 * Build 3D lines and surface mesh for a geographic bounding box on a sphere.
 */
function createBoundingBoxMesh(
  lonMin: number,
  lonMax: number,
  latMin: number,
  latMax: number,
  radius: number
): { lines: THREE.Line; fill: THREE.Mesh } {
  const r = radius * 1.003;
  const samples = 16;
  const linePoints: THREE.Vector3[] = [];

  // Bottom edge: latMin, lonMin -> lonMax
  for (let i = 0; i <= samples; i++) {
    const lon = lonMin + (lonMax - lonMin) * (i / samples);
    linePoints.push(latLonToVector3(latMin, lon, r));
  }
  // Right edge: latMin -> latMax, lonMax
  for (let i = 0; i <= samples; i++) {
    const lat = latMin + (latMax - latMin) * (i / samples);
    linePoints.push(latLonToVector3(lat, lonMax, r));
  }
  // Top edge: latMax, lonMax -> lonMin
  for (let i = 0; i <= samples; i++) {
    const lon = lonMax - (lonMax - lonMin) * (i / samples);
    linePoints.push(latLonToVector3(latMax, lon, r));
  }
  // Left edge: latMax -> latMin, lonMin
  for (let i = 0; i <= samples; i++) {
    const lat = latMax - (latMax - latMin) * (i / samples);
    linePoints.push(latLonToVector3(lat, lonMin, r));
  }

  const lineGeo = new THREE.BufferGeometry().setFromPoints(linePoints);
  const lineMat = new THREE.LineBasicMaterial({
    color: 0x22d3ee, // cyan highlight
    linewidth: 2,
    transparent: true,
    opacity: 0.95,
  });
  const lines = new THREE.Line(lineGeo, lineMat);

  // Translucent filled patch
  const gridN = 8;
  const fillPoints: number[] = [];
  const indices: number[] = [];

  for (let j = 0; j <= gridN; j++) {
    const lat = latMin + (latMax - latMin) * (j / gridN);
    for (let i = 0; i <= gridN; i++) {
      const lon = lonMin + (lonMax - lonMin) * (i / gridN);
      const v = latLonToVector3(lat, lon, r * 0.999);
      fillPoints.push(v.x, v.y, v.z);
    }
  }

  for (let j = 0; j < gridN; j++) {
    for (let i = 0; i < gridN; i++) {
      const a = j * (gridN + 1) + i;
      const b = a + 1;
      const c = (j + 1) * (gridN + 1) + i;
      const d = c + 1;
      indices.push(a, b, c);
      indices.push(b, d, c);
    }
  }

  const fillGeo = new THREE.BufferGeometry();
  fillGeo.setAttribute("position", new THREE.Float32BufferAttribute(fillPoints, 3));
  fillGeo.setIndex(indices);
  fillGeo.computeVertexNormals();

  const fillMat = new THREE.MeshBasicMaterial({
    color: 0x06b6d4,
    transparent: true,
    opacity: 0.28,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const fill = new THREE.Mesh(fillGeo, fillMat);

  return { lines, fill };
}

export default function Globe({
  lonMin,
  lonMax,
  latMin,
  latMax,
  onSelectRegion,
  onPickPoint,
  disabled = false,
}: GlobeProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const globeMeshRef = useRef<THREE.Mesh | null>(null);
  const boxGroupRef = useRef<THREE.Group | null>(null);
  const rafRef = useRef<number>();

  const [stepSize, setStepSize] = useState<10 | 5>(10);
  const [clickedCoord, setClickedCoord] = useState<{ lat: number; lon: number } | null>(null);

  // 3D Subsurface Column Profiling state
  const [globeMode, setGlobeMode] = useState<"box" | "probe">("box");
  const [probeData, setProbeData] = useState<VerticalColumnResponse | null>(null);
  const [probeLoading, setProbeLoading] = useState<boolean>(false);
  const [activeProbeVar, setActiveProbeVar] = useState<ProbeVariable>("temperature");
  const column3DRef = useRef<Column3DObject | null>(null);

  // Dataset boundary footprint & surface beacon marker state
  const [showDatasetBounds, setShowDatasetBounds] = useState<boolean>(true);
  const datasetBoxRef = useRef<DatasetBoundingBoxObject | null>(null);
  const locationMarkerRef = useRef<LocationMarkerObject | null>(null);

  // Track pointer interaction to differentiate click from orbit drag
  const pointerDownPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Update or render the highlighted bounding box
  const updateBoundingBoxVisual = useCallback(
    (bLonMin: number, bLonMax: number, bLatMin: number, bLatMax: number) => {
      const scene = sceneRef.current;
      const boxGroup = boxGroupRef.current;
      if (!scene || !boxGroup) return;

      // Clear previous box meshes
      while (boxGroup.children.length > 0) {
        const obj = boxGroup.children[0] as THREE.Mesh | THREE.Line;
        boxGroup.remove(obj);
        if (obj.geometry) obj.geometry.dispose();
        if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
        else if (obj.material) obj.material.dispose();
      }

      const { lines, fill } = createBoundingBoxMesh(
        bLonMin,
        bLonMax,
        bLatMin,
        bLatMax,
        GLOBE_RADIUS
      );
      boxGroup.add(lines);
      boxGroup.add(fill);
    },
    []
  );

  // Initialize Three.js scene
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 284;
    const height = 210;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    camera.position.set(0, 0.8, 2.3);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearColor(0x000000, 0); // transparent background
    mount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.6;
    controls.minDistance = 1.3;
    controls.maxDistance = 4.0;
    controls.enablePan = false;
    controlsRef.current = controls;

    // Ambient and directional lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);

    // Warm-white directional light for natural sunlight & ocean glint
    const dirLight = new THREE.DirectionalLight(0xfff8f0, 1.25);
    dirLight.position.set(3, 2, 2.5);
    scene.add(dirLight);

    // Load textures (local public folder with transparent CDN fallback)
    const textureLoader = new THREE.TextureLoader();

    const globeMat = new THREE.MeshPhongMaterial({
      roughness: undefined,
      shininess: 18,
      specular: new THREE.Color(0x333333),
    } as THREE.MeshPhongMaterialParameters);

    const configureTextureOrientation = (tex: THREE.Texture) => {
      tex.wrapS = THREE.ClampToEdgeWrapping;
      tex.repeat.x = 1;
      tex.offset.x = 0;
    };

    const globeTexture = textureLoader.load(
      EARTH_TEXTURE_LOCAL,
      (tex) => {
        configureTextureOrientation(tex);
        globeMat.map = tex;
        globeMat.needsUpdate = true;
      },
      undefined,
      () => {
        textureLoader.load(EARTH_TEXTURE_CDN, (cdnTex) => {
          configureTextureOrientation(cdnTex);
          globeMat.map = cdnTex;
          globeMat.needsUpdate = true;
        });
      }
    );
    configureTextureOrientation(globeTexture);

    const specularTexture = textureLoader.load(
      EARTH_SPECULAR_LOCAL,
      (spec) => {
        configureTextureOrientation(spec);
        globeMat.specularMap = spec;
        globeMat.needsUpdate = true;
      },
      undefined,
      () => {
        textureLoader.load(EARTH_SPECULAR_CDN, (cdnSpec) => {
          configureTextureOrientation(cdnSpec);
          globeMat.specularMap = cdnSpec;
          globeMat.needsUpdate = true;
        });
      }
    );
    configureTextureOrientation(specularTexture);

    const globeGeo = new THREE.SphereGeometry(GLOBE_RADIUS, 64, 64);
    const globeMesh = new THREE.Mesh(globeGeo, globeMat);
    scene.add(globeMesh);
    globeMeshRef.current = globeMesh;

    // Group for selected bounding box outline
    const boxGroup = new THREE.Group();
    scene.add(boxGroup);
    boxGroupRef.current = boxGroup;

    // 1. Dataset Coverage Boundary Footprint (Geodesic box matching local NetCDF dataset)
    const datasetBox = createDatasetBoundingBox(DEFAULT_DATASET_BOUNDS, GLOBE_RADIUS);
    scene.add(datasetBox.group);
    datasetBoxRef.current = datasetBox;

    // 2. Active Location Surface Marker Beacon (Crosshairs + pulsating radar ring)
    const initLat = (latMin + latMax) / 2;
    const initLon = (lonMin + lonMax) / 2;
    const locationMarker = createLocationSurfaceMarker(initLat, initLon, GLOBE_RADIUS);
    scene.add(locationMarker.group);
    locationMarkerRef.current = locationMarker;

    // Render loop with animated surface beacon pulse
    const animate = (time: number) => {
      rafRef.current = requestAnimationFrame(animate);
      controls.update();
      if (locationMarkerRef.current) {
        locationMarkerRef.current.updateAnimation(time * 0.001);
      }
      renderer.render(scene, camera);
    };
    animate(0);

    // Resize handling
    const handleResize = () => {
      if (!mountRef.current || !cameraRef.current || !rendererRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = 210;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      controls.dispose();
      renderer.dispose();
      globeTexture.dispose();
      specularTexture.dispose();
      globeGeo.dispose();
      globeMat.dispose();
      if (datasetBoxRef.current) {
        datasetBoxRef.current.dispose();
        datasetBoxRef.current = null;
      }
      if (locationMarkerRef.current) {
        locationMarkerRef.current.dispose();
        locationMarkerRef.current = null;
      }
      if (column3DRef.current) {
        column3DRef.current.dispose();
        column3DRef.current = null;
      }
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Toggle dataset bounds visibility
  useEffect(() => {
    if (datasetBoxRef.current) {
      datasetBoxRef.current.setVisible(showDatasetBounds);
    }
  }, [showDatasetBounds]);

  // Update bounding box visual and surface beacon whenever current props change
  useEffect(() => {
    updateBoundingBoxVisual(lonMin, lonMax, latMin, latMax);
    if (locationMarkerRef.current && globeMode === "box") {
      locationMarkerRef.current.setPosition((latMin + latMax) / 2, (lonMin + lonMax) / 2);
    }
  }, [lonMin, lonMax, latMin, latMax, globeMode, updateBoundingBoxVisual]);

  // Core Probe planting logic
  const plantCoreProbe = useCallback(
    async (lat: number, lon: number) => {
      setProbeLoading(true);
      try {
        const data = await fetchVerticalColumn(lat, lon, 1000);
        setProbeData(data);

        // Remove old column from scene
        if (column3DRef.current) {
          if (sceneRef.current) {
            sceneRef.current.remove(column3DRef.current.group);
          }
          column3DRef.current.dispose();
          column3DRef.current = null;
        }

        if (sceneRef.current && !data.is_land && data.profile && data.profile.length > 0) {
          const colObj = createVerticalColumnMesh(
            lat,
            lon,
            data.profile,
            activeProbeVar,
            1000,
            GLOBE_RADIUS
          );
          sceneRef.current.add(colObj.group);
          column3DRef.current = colObj;
        }
      } catch (err) {
        console.error("Failed to plant core probe:", err);
      } finally {
        setProbeLoading(false);
      }
    },
    [activeProbeVar]
  );

  const handleVariableChange = (v: ProbeVariable) => {
    setActiveProbeVar(v);
    if (column3DRef.current) {
      column3DRef.current.updateColors(v);
    }
  };

  const handleCloseProbe = () => {
    setProbeData(null);
    if (column3DRef.current) {
      if (sceneRef.current) {
        sceneRef.current.remove(column3DRef.current.group);
      }
      column3DRef.current.dispose();
      column3DRef.current = null;
    }
  };

  // Pointer event handlers for raycasting click detection
  const handlePointerDown = (e: React.PointerEvent) => {
    pointerDownPosRef.current = { x: e.clientX, y: e.clientY };
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (disabled) return;
    const dx = e.clientX - pointerDownPosRef.current.x;
    const dy = e.clientY - pointerDownPosRef.current.y;
    // If pointer moved more than 5 pixels, it's an orbit rotation drag, not a click
    if (Math.hypot(dx, dy) > 5) return;

    const mount = mountRef.current;
    const renderer = rendererRef.current;
    const camera = cameraRef.current;
    const globeMesh = globeMeshRef.current;
    if (!mount || !renderer || !camera || !globeMesh) return;

    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, camera);
    const intersects = raycaster.intersectObject(globeMesh, false);

    if (intersects.length > 0) {
      const hitPoint = intersects[0].point;
      // Convert world hit point to globe local coordinates
      const localPoint = globeMesh.worldToLocal(hitPoint.clone());
      const { lat, lon } = vector3ToLatLon(localPoint);

      setClickedCoord({ lat, lon });

      // Always update active location surface beacon pin directly to clicked coordinates
      if (locationMarkerRef.current) {
        locationMarkerRef.current.setPosition(lat, lon);
        locationMarkerRef.current.group.visible = true;
      }

      // Universal Click-to-Inspect: emit probe point for instant multi-variable inspection
      const probe: ProbePoint = {
        lon: Number(lon.toFixed(4)),
        lat: Number(lat.toFixed(4)),
        depth: 0.0,
        localU: 0.5,
        localV: 0.5,
        localW: 0.0,
        worldPos: { x: hitPoint.x, y: hitPoint.y, z: hitPoint.z },
      };
      onPickPoint?.(probe);

      if (globeMode === "probe") {
        plantCoreProbe(lat, lon);
      } else {
        // Snap coordinate to uniform grid bounding box
        const step = stepSize;
        let snappedLonMin = Math.floor(lon / step) * step;
        let snappedLonMax = snappedLonMin + step;
        let snappedLatMin = Math.floor(lat / step) * step;
        let snappedLatMax = snappedLatMin + step;

        // Bound clamping
        snappedLatMin = Math.max(-80, Math.min(90 - step, snappedLatMin));
        snappedLatMax = Math.min(90, Math.max(snappedLatMin + step, snappedLatMax));
        snappedLonMin = Math.max(-180, Math.min(180 - step, snappedLonMin));
        snappedLonMax = Math.min(180, Math.max(snappedLonMin + step, snappedLonMax));

        // Round to 1 decimal place cleanly
        snappedLonMin = Number(snappedLonMin.toFixed(1));
        snappedLonMax = Number(snappedLonMax.toFixed(1));
        snappedLatMin = Number(snappedLatMin.toFixed(1));
        snappedLatMax = Number(snappedLatMax.toFixed(1));

        // Update bounding box visually immediately
        updateBoundingBoxVisual(snappedLonMin, snappedLonMax, snappedLatMin, snappedLatMax);

        // Trigger instant callback to update state and auto-load GLORYS volume
        onSelectRegion({
          lonMin: snappedLonMin,
          lonMax: snappedLonMax,
          latMin: snappedLatMin,
          latMax: snappedLatMax,
        });
      }
    }
  };

  return (
    <div
      style={{
        position: "relative",
        background: "rgba(3, 11, 18, 0.75)",
        border: "1px solid var(--line)",
        borderRadius: 6,
        padding: "8px 6px 6px 6px",
        marginBottom: 10,
      }}
    >
      {/* Globe Controls & Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 4px 6px 4px",
          gap: 4,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)" }}>
            3D Globe
          </span>
          {/* Mode Switcher */}
          <div
            style={{
              display: "flex",
              background: "rgba(255,255,255,0.06)",
              borderRadius: 4,
              padding: 1,
              border: "1px solid var(--line)",
            }}
          >
            <button
              type="button"
              onClick={() => setGlobeMode("box")}
              style={{
                fontSize: 9,
                padding: "2px 5px",
                borderRadius: 3,
                border: "none",
                background: globeMode === "box" ? "var(--accent)" : "transparent",
                color: globeMode === "box" ? "#03171f" : "var(--text-muted)",
                fontWeight: globeMode === "box" ? 700 : 500,
                cursor: "pointer",
              }}
              title="Select geographic volume bounding box"
            >
              Region Box
            </button>
            <button
              type="button"
              onClick={() => setGlobeMode("probe")}
              style={{
                fontSize: 9,
                padding: "2px 5px",
                borderRadius: 3,
                border: "none",
                background: globeMode === "probe" ? "var(--accent)" : "transparent",
                color: globeMode === "probe" ? "#03171f" : "var(--text-muted)",
                fontWeight: globeMode === "probe" ? 700 : 500,
                cursor: "pointer",
              }}
              title="Sample 3D subsurface column profile (T, S, Chlorophyll)"
            >
              📍 Core Probe
            </button>
          </div>

          {/* Dataset Boundary Footprint Scope Toggle */}
          <button
            type="button"
            onClick={() => setShowDatasetBounds((prev) => !prev)}
            style={{
              fontSize: 9,
              padding: "2px 5px",
              borderRadius: 4,
              border: `1px solid ${showDatasetBounds ? "rgba(0, 229, 255, 0.4)" : "var(--line)"}`,
              background: showDatasetBounds ? "rgba(0, 229, 255, 0.12)" : "transparent",
              color: showDatasetBounds ? "#00e5ff" : "var(--text-muted)",
              fontWeight: showDatasetBounds ? 700 : 500,
              cursor: "pointer",
            }}
            title="Toggle Local NetCDF Coverage Boundary (-2.8°..22.8°N, 42.0°..107.4°E)"
          >
            🌐 Scope
          </button>
        </div>

        {/* Right side controls based on active mode */}
        {globeMode === "box" ? (
          <div style={{ display: "flex", gap: 3 }}>
            {([10, 5] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStepSize(s)}
                style={{
                  fontSize: 9.5,
                  padding: "2px 6px",
                  borderRadius: 3,
                  border: "1px solid var(--line)",
                  background: stepSize === s ? "var(--accent)" : "transparent",
                  color: stepSize === s ? "#03171f" : "var(--text-muted)",
                  fontWeight: stepSize === s ? 700 : 400,
                  cursor: "pointer",
                }}
              >
                {s}° Box
              </button>
            ))}
          </div>
        ) : (
          <span
            style={{
              fontSize: 8.5,
              color: "#38bdf8",
              background: "rgba(56, 189, 248, 0.12)",
              padding: "2px 5px",
              borderRadius: 3,
              border: "1px solid rgba(56, 189, 248, 0.3)",
            }}
          >
            Click to Probe
          </span>
        )}
      </div>

      {/* 3D Canvas Mount */}
      <div
        ref={mountRef}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        style={{
          width: "100%",
          height: 210,
          cursor: disabled
            ? "not-allowed"
            : globeMode === "probe"
            ? "pointer"
            : "crosshair",
          borderRadius: 4,
          overflow: "hidden",
          background: "radial-gradient(circle, #091c2b 0%, #030a10 100%)",
        }}
      />

      {/* Active Coordinates / Status Badge */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 6,
          padding: "2px 4px",
          fontSize: 10,
          color: "var(--text-muted)",
        }}
      >
        {globeMode === "box" ? (
          <>
            <span>
              Selected:{" "}
              <strong style={{ color: "var(--accent)" }}>
                {lonMin}°..{lonMax}°E, {latMin}°..{latMax}°N
              </strong>
            </span>
            {clickedCoord && (
              <span style={{ fontSize: 9, opacity: 0.8 }}>
                Hit: {clickedCoord.lat.toFixed(1)}°N, {clickedCoord.lon.toFixed(1)}°E
              </span>
            )}
          </>
        ) : (
          <>
            <span>
              Mode:{" "}
              <strong style={{ color: "#38bdf8" }}>
                Subsurface Core Probe (0–1000m)
              </strong>
            </span>
            {clickedCoord && (
              <span style={{ fontSize: 9, opacity: 0.8 }}>
                Probe: {clickedCoord.lat.toFixed(1)}°N, {clickedCoord.lon.toFixed(1)}°E
              </span>
            )}
          </>
        )}
      </div>

      {/* Dataset Footprint Scope & Surface Beacon Legend */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 4,
          padding: "3px 4px 1px 4px",
          fontSize: 8.5,
          color: "var(--text-muted)",
          borderTop: "1px solid rgba(255, 255, 255, 0.05)",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span
            style={{
              display: "inline-block",
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: showDatasetBounds ? "#00e5ff" : "rgba(255,255,255,0.2)",
              boxShadow: showDatasetBounds ? "0 0 6px #00e5ff" : "none",
            }}
          />
          Scope:{" "}
          <span style={{ color: showDatasetBounds ? "#00e5ff" : "var(--text-muted)" }}>
            NetCDF IO (-2.8°–22.8°N)
          </span>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
          <span
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#ffb703",
              boxShadow: "0 0 6px #ffb703",
            }}
          />
          <span style={{ color: "#ffb703" }}>Surface Beacon</span>
        </span>
      </div>

      {/* 2D Depth Profile HUD Overlay */}
      <SubsurfaceColumnHUD
        data={probeData}
        loading={probeLoading}
        activeVariable={activeProbeVar}
        onVariableChange={handleVariableChange}
        onClose={handleCloseProbe}
      />
    </div>
  );
}
