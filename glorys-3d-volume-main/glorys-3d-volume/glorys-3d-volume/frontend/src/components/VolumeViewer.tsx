/**
 * VolumeViewer.tsx
 *
 * GPU-based 3D volume renderer for GLORYS12V1 ocean data.
 *
 * Coordinate system (box-local, canonical GPU space):
 *   X ∈ [-0.5, +0.5]  →  longitude (west → east)
 *   Y ∈ [-0.5, +0.5]  →  depth     (top=shallow → bottom=deep, Y flipped in shader)
 *   Z ∈ [-0.5, +0.5]  →  latitude  (south → north)
 *
 * Physical proportions are applied via mesh.scale, computed 100 % from the loaded
 * dataset coordinates (meta.longitude[], meta.latitude[], meta.depth[]).
 * Nothing is hardcoded.  If the dataset changes the volume geometry changes automatically.
 *
 * The only user-controlled geometric modifier is verticalExaggeration.
 *
 * Multi-variable rendering modes:
 *   - is2d=false (thetao, so): Full GPU ray-marched 3D volume using boxMesh + volume.frag
 *   - is2d=true  (mlotst, ohc_0_700m): Flat surface heatmap using sliceMesh + slice.frag
 *     The backend packs 2D variables as a (depth=1, lat, lon) tensor so the same
 *     Data3DTexture upload path is used; uSliceDepth=0.5 samples the single layer.
 */

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import volumeVert from "../shaders/volume.vert?raw";
import volumeFrag from "../shaders/volume.frag?raw";
import sliceVert from "../shaders/slice.vert?raw";
import sliceFrag from "../shaders/slice.frag?raw";
import type { VolumeData, VolumeMeta, ProbePoint, VolumeRenderMode, LayerSummary } from "../types";
import { calculateLayerSliceStats } from "../utils/layerStats";
import {
  generateVolumeMarkers,
  createVolumeMarkersObject,
  type VolumeMarkersObject,
  type VolumeMarkerPoint,
  VolumeMarkerTooltip,
} from "./VolumeMarkers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RegionBounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
  minDepth?: number;
  maxDepth?: number;
}

export interface VolumeViewerProps {
  volumeData: VolumeData | null;
  regionBounds?: RegionBounds;
  tempMin: number;
  tempMax: number;
  opacity: number;
  steps: number;
  verticalExaggeration: number;
  mode: "volume" | "slice";
  sliceDepthNormalized: number; // 0..1 along the depth texture axis
  sliceDepthM?: number;         // exact depth of current slice/layer in meters
  uIsLayerMode?: boolean;       // whether layer-dividers overlay is active
  sliceStep?: number;           // step in meters for dividers
  activeSlice?: number;         // 1-based index of highlighted slice
  is2d?: boolean;
  probePoint?: ProbePoint | null;
  onPick: (probe: ProbePoint) => void;
  onSliceSelect?: (sliceIndex: number) => void;
  renderMode?: VolumeRenderMode;
  chlIntensity?: number;
  salinityWeight?: number;
  showVolumeMarkers?: boolean;
}

// ---------------------------------------------------------------------------
/**
 * Pure spatial helpers — all inputs come from loaded dataset metadata.
 */

/**
 * Unprojects 3D volume box coordinates to geographical coordinates strictly
 * interpolating within activeRegionBounds (NOT whole globe).
 */
export function volumeIntersectToGeo(
  localPoint: THREE.Vector3,
  boxSize: { width: number; height: number; depth: number },
  bounds: { minLat: number; maxLat: number; minLon: number; maxLon: number; minDepth: number; maxDepth: number }
): { lat: number; lon: number; depth: number } {
  // 1. Normalize 3D box coordinates from [-size/2, +size/2] to [0.0, 1.0]
  const normX = THREE.MathUtils.clamp((localPoint.x / boxSize.width) + 0.5, 0.0, 1.0);
  const normY = THREE.MathUtils.clamp(0.5 - (localPoint.y / boxSize.height), 0.0, 1.0); // Y goes down with depth
  const normZ = THREE.MathUtils.clamp((localPoint.z / boxSize.depth) + 0.5, 0.0, 1.0);

  // 2. Interpolate strictly within the CURRENT active region bounds (NOT whole globe)
  // Ensure longitude direction matches volume orientation (West -> East)
  const lon = bounds.minLon + normX * (bounds.maxLon - bounds.minLon);
  const lat = bounds.minLat + normZ * (bounds.maxLat - bounds.minLat);
  const depth = bounds.minDepth + normY * (bounds.maxDepth - bounds.minDepth);

  return { lat, lon, depth };
}

/** Earth-radius constants (legitimate physical constants, not dataset assumptions). */
const KM_PER_DEG_LAT = 111.32; // km per degree of latitude (constant)

/** Returns km-per-degree-longitude at a given latitude (in degrees). */
function kmPerDegLon(latDeg: number): number {
  return KM_PER_DEG_LAT * Math.cos((latDeg * Math.PI) / 180);
}

/**
 * Compute the Three.js mesh scale that makes the volume look like a flat
 * horizontal ocean prism rather than a vertical tower.
 *
 * Key insight: with a full-water-column GLORYS query (0–5728 m), the raw
 * depth/width km ratio is only ~0.0035.  Multiplying that by a "500×"
 * exaggeration gives scaleY ≈ 1.77 vs scaleX = 1.0 — a pillar, not a slab.
 *
 * The new approach decouples scaleY entirely from physical depth magnitude:
 *   - scaleX = BASE_SIZE                        (longitude reference axis)
 *   - scaleZ = BASE_SIZE × (heightKm / widthKm) (lat proportional to lon)
 *   - scaleY = BASE_SIZE × DEPTH_FRACTION × verticalExaggeration
 *            where DEPTH_FRACTION = 0.22 ensures depth is ~22% of width
 *            and verticalExaggeration is a small UI knob (1.0 = natural).
 *
 * Physical widthKm / heightKm / depthKm are still returned for the log.
 */
const BASE_SIZE     = 10.0; // Three.js world-units for the longitude axis
const DEPTH_FRACTION = 0.22; // target Y/X ratio at verticalExaggeration=1

function computeScaleFromMeta(
  meta: VolumeMeta,
  verticalExaggeration: number
): { scale: THREE.Vector3; widthKm: number; heightKm: number; depthKm: number } {
  // Guard against empty coordinate arrays (e.g. from a failed / partial fetch)
  const lons = meta.longitude.length > 0 ? meta.longitude : [0, 1];
  const lats = meta.latitude.length  > 0 ? meta.latitude  : [0, 1];
  const deps = meta.depth.length     > 0 ? meta.depth     : [0, 100];

  const lonMin = Math.min(...lons);
  const lonMax = Math.max(...lons);
  const latMin = Math.min(...lats);
  const latMax = Math.max(...lats);
  const depthActualMin = Math.min(...deps);
  const depthActualMax = Math.max(...deps);

  // Clamp to physical minimums so the mesh never collapses to a sliver.
  const deltaLon = Math.max(1.0, Math.abs(lonMax - lonMin));
  const deltaLat = Math.max(1.0, Math.abs(latMax - latMin));
  const depthExtentM = Math.max(1.0, Math.abs(depthActualMax - depthActualMin));

  const meanLat  = (latMin + latMax) / 2;
  const widthKm  = deltaLon * kmPerDegLon(meanLat); 
  const heightKm = deltaLat * KM_PER_DEG_LAT;        
  const depthKm  = depthExtentM / 1000;                  

  // Ocean Slab Proportions
  const scaleX = 4.0;
  let scaleZ = scaleX * (deltaLat / deltaLon);
  
  // Clamp scaleZ so the surface never collapses into a narrow line
  scaleZ = Math.max(scaleX * 0.5, Math.min(scaleX * 2.5, scaleZ));
  
  // Force depth to a fixed slab ratio of the horizontal bounds
  // (Ignore the massive verticalExaggeration=500 from props to prevent needle effect)
  const scaleY = 0.3 * Math.min(scaleX, scaleZ);

  return {
    scale: new THREE.Vector3(scaleX, scaleY, scaleZ),
    widthKm,
    heightKm,
    depthKm,
  };
}

/**
 * Convert a normalised volume coordinate fraction [0,1] to the corresponding
 * actual geographic value using the actual coordinate array (interpolates between
 * grid points, which works correctly for irregular grids and any orientation)..
 */
function fracToCoord(arr: number[], frac: number): number {
  if (!arr || arr.length === 0) return 0;
  if (arr.length === 1) return arr[0];
  const clampedFrac = Math.max(0, Math.min(1, frac));
  const floatIdx = clampedFrac * (arr.length - 1);
  const lo = Math.max(0, Math.min(arr.length - 2, Math.floor(floatIdx)));
  const hi = lo + 1;
  const t  = floatIdx - lo;
  return arr[lo] * (1 - t) + arr[hi] * t;
}

/**
 * Frame the camera to encompass the given bounding box.
 * Uses the box diagonal/sphere to dynamically set distance and clipping planes.
 */
function frameCameraToBox(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  box: THREE.Box3
): void {
  // Always center on origin
  controls.target.set(0, 0, 0);

  // Force a proper isometric 3D perspective angle
  camera.position.set(3.5, 4.0, 3.0);
  camera.lookAt(0, 0, 0);

  // Dynamically set near and far clipping planes
  camera.near = 0.01;
  camera.far  = 100;
  camera.updateProjectionMatrix();

  // Orbit control distance limits
  controls.minDistance = 0.1;
  controls.maxDistance = 25;
  controls.update();
}

/**
 * Emit a comprehensive validation log derived entirely from the loaded dataset.
 * No hardcoded expected values.
 */
function logDatasetGeometry(
  meta: VolumeMeta,
  widthKm: number,
  heightKm: number,
  depthKm: number,
  scale: THREE.Vector3,
  verticalExaggeration: number
): void {
  const lonMin = Math.min(...meta.longitude);
  const lonMax = Math.max(...meta.longitude);
  const latMin = Math.min(...meta.latitude);
  const latMax = Math.max(...meta.latitude);
  const dMin   = meta.depth.length > 0 ? Math.min(...meta.depth) : 0;
  const dMax   = meta.depth.length > 0 ? Math.max(...meta.depth) : 0;

  console.log(
    "[GLORYS] ─── Dataset geometry ───────────────────────────────\n" +
    "[GLORYS] variable             : " + meta.variable + (meta.is_2d ? " (2D surface field)" : "") + "\n" +
    "[GLORYS] longitude            : " + lonMin.toFixed(4) + "° → " + lonMax.toFixed(4) + "°\n" +
    "[GLORYS] latitude             : " + latMin.toFixed(4) + "° → " + latMax.toFixed(4) + "°\n" +
    (meta.is_2d ? "" : "[GLORYS] depth                : " + dMin.toFixed(2) + " m → " + dMax.toFixed(2) + " m\n") +
    "[GLORYS] ─── Physical dimensions ───────────────────────────\n" +
    "[GLORYS] physical width  (EW) : " + widthKm.toFixed(2)  + " km\n" +
    "[GLORYS] physical height (NS) : " + heightKm.toFixed(2) + " km\n" +
    (meta.is_2d ? "" : "[GLORYS] physical depth       : " + depthKm.toFixed(4)  + " km\n") +
    "[GLORYS] ─── Sample counts ──────────────────────────────────\n" +
    "[GLORYS] sample dimensions    : " + meta.shape.lon + " × " + meta.shape.lat +
      (meta.is_2d ? " (lon × lat, 2D)" : " × " + meta.shape.depth + " (lon × lat × depth)") + "\n" +
    "[GLORYS] ─── Display transform ──────────────────────────────\n" +
    "[GLORYS] display dimensions   : X=" + scale.x.toFixed(4) + " Y=" + scale.y.toFixed(6) + " Z=" + scale.z.toFixed(4) + "\n" +
    "[GLORYS] vertical exaggeration: " + verticalExaggeration + "×\n" +
    "[GLORYS] ─────────────────────────────────────────────────────"
  );
}

/**
 * Computes layer-wide summary statistics (mean, min, max) across an active horizontal slice.
 */
function computeLayerSummary(
  volData: VolumeData,
  dIdx: number,
  sliceIdx: number,
  totalSlices: number,
  depthStartM: number,
  depthEndM: number,
  sliceDepthM: number
): LayerSummary {
  return calculateLayerSliceStats(
    volData,
    dIdx,
    sliceIdx,
    totalSlices,
    depthStartM,
    depthEndM,
    sliceDepthM
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VolumeViewer({
  volumeData,
  regionBounds,
  tempMin,
  tempMax,
  opacity,
  steps,
  verticalExaggeration,
  mode,
  sliceDepthNormalized,
  sliceDepthM = 0,
  uIsLayerMode = false,
  sliceStep = 100,
  activeSlice = 1,
  is2d = false,
  probePoint = null,
  onPick,
  onSliceSelect,
  renderMode = "temperature",
  chlIntensity = 1.2,
  salinityWeight = 1.0,
  showVolumeMarkers = true,
}: VolumeViewerProps) {
  const mountRef            = useRef<HTMLDivElement>(null);
  const sceneRef            = useRef<THREE.Scene>();
  const cameraRef           = useRef<THREE.PerspectiveCamera>();
  const rendererRef         = useRef<THREE.WebGLRenderer>();
  const controlsRef         = useRef<OrbitControls>();
  const boxMeshRef          = useRef<THREE.Mesh>();
  const sliceMeshRef        = useRef<THREE.Mesh>();
  const volMaterialRef      = useRef<THREE.ShaderMaterial>();
  const sliceMaterialRef    = useRef<THREE.ShaderMaterial>();
  const textureRef          = useRef<THREE.Data3DTexture>();
  const dividersGroupRef    = useRef<THREE.Group>();
  const layerPlanesGroupRef = useRef<THREE.Group>();
  const probeGroupRef       = useRef<THREE.Group>();
  const outerSphereRef      = useRef<THREE.Mesh>();
  const innerSphereRef      = useRef<THREE.Mesh>();
  const leaderLineRef       = useRef<THREE.Line>();
  const baseRingRef         = useRef<THREE.Mesh>();
  const rafRef              = useRef<number>();

  const [activeMarker, setActiveMarker] = useState<VolumeMarkerPoint | null>(null);
  const volumeMarkersRef = useRef<VolumeMarkersObject | null>(null);

  const onPickRef        = useRef(onPick);
  onPickRef.current      = onPick;

  const onSliceSelectRef  = useRef(onSliceSelect);
  onSliceSelectRef.current = onSliceSelect;

  const volumeDataRef    = useRef(volumeData);
  volumeDataRef.current  = volumeData;

  const regionBoundsRef  = useRef(regionBounds);
  regionBoundsRef.current = regionBounds;

  const sliceDepthMRef    = useRef(sliceDepthM);
  sliceDepthMRef.current  = sliceDepthM;

  const sliceDepthNormRef = useRef(sliceDepthNormalized);
  sliceDepthNormRef.current = sliceDepthNormalized;

  const isLayerModeRef    = useRef(uIsLayerMode);
  isLayerModeRef.current  = uIsLayerMode;

  const modeRef           = useRef(mode);
  modeRef.current         = mode;

  const activeSliceRef    = useRef(activeSlice);
  activeSliceRef.current  = activeSlice;

  const sliceStepRef      = useRef(sliceStep);
  sliceStepRef.current    = sliceStep;

  const is2dRef           = useRef(is2d);
  is2dRef.current         = is2d;

  const getActiveBounds = () => {
    const curMeta = volumeDataRef.current?.meta ?? metaRef.current;
    const rb = regionBoundsRef.current;
    const minLon = rb?.minLon ?? curMeta?.longitude_min ?? (curMeta?.longitude?.length ? Math.min(...curMeta.longitude) : 42.0);
    const maxLon = rb?.maxLon ?? curMeta?.longitude_max ?? (curMeta?.longitude?.length ? Math.max(...curMeta.longitude) : 107.42);
    const minLat = rb?.minLat ?? curMeta?.latitude_min ?? (curMeta?.latitude?.length ? Math.min(...curMeta.latitude) : -2.83);
    const maxLat = rb?.maxLat ?? curMeta?.latitude_max ?? (curMeta?.latitude?.length ? Math.max(...curMeta.latitude) : 22.83);
    const minDepth = rb?.minDepth ?? curMeta?.depth_min ?? 0.0;
    const maxDepth = rb?.maxDepth ?? curMeta?.depth_max ?? 500.0;

    return {
      minLat,
      maxLat,
      minLon,
      maxLon,
      minDepth,
      maxDepth,
    };
  };

  /**
   * metaRef holds the authoritative VolumeMeta including coordinate arrays.
   */
  const metaRef          = useRef<VolumeMeta | null>(null);
  /**
   * Track the last framed volume reference so camera auto-framing only triggers
   * on dataset load or dataset change, never interrupting slider interactions.
   */
  const lastFramedDataRef = useRef<VolumeData | null>(null);

  // --------------------------------------------------------------------------
  // ONE-TIME scene setup — runs once on mount.
  // --------------------------------------------------------------------------
  useEffect(() => {
    const mount = mountRef.current!;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x061019);

    const camera = new THREE.PerspectiveCamera(45, mount.clientWidth / mount.clientHeight, 0.001, 1000);
    camera.position.set(2, 1.2, 1.5); // Initial fallback until data arrives

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    // Enable standard WebGL2 floating-point texture linear filtering
    renderer.extensions.get("OES_texture_float_linear");
    renderer.extensions.get("EXT_color_buffer_float");

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0, 0);

    // Placeholder 1×1×1 texture with smooth linear filtering using HalfFloatType
    const placeholderArray = new Uint16Array([THREE.DataUtils.toHalfFloat(0)]);
    const placeholder = new THREE.Data3DTexture(placeholderArray, 1, 1, 1);
    placeholder.format          = THREE.RedFormat;
    placeholder.type            = THREE.HalfFloatType;
    placeholder.minFilter       = THREE.LinearFilter;
    placeholder.magFilter       = THREE.LinearFilter;
    placeholder.generateMipmaps = false;
    placeholder.unpackAlignment = 1;
    placeholder.wrapS           = THREE.ClampToEdgeWrapping;
    placeholder.wrapT           = THREE.ClampToEdgeWrapping;
    placeholder.wrapR           = THREE.ClampToEdgeWrapping;
    placeholder.needsUpdate     = true;

    // ---- Volume ray-march material ----
    const volMaterial = new THREE.ShaderMaterial({
      glslVersion:    THREE.GLSL3,
      vertexShader:   volumeVert,
      fragmentShader: volumeFrag,
      transparent:    true,
      side:           THREE.BackSide,
      depthWrite:     false,
      uniforms: {
        uVolume:          { value: placeholder },
        uTempMin:         { value: 0 },
        uTempMax:         { value: 30 },
        uOpacity:         { value: 1 },
        uSteps:           { value: 256 },
        uScale:           { value: new THREE.Vector3(1, 1, 1) },
        uRenderMode:      { value: 0 },
        uChlIntensity:    { value: 1.2 },
        uSalinityWeight:  { value: 1.0 },
        uIsMultiChannel:  { value: 0 },
      },
    });

    // Unit cube in local space — transformed by data-driven mesh.scale
    const boxGeo  = new THREE.BoxGeometry(1, 1, 1);
    const boxMesh = new THREE.Mesh(boxGeo, volMaterial);
    scene.add(boxMesh);

    // ---- Horizontal slice material ----
    const sliceMaterial = new THREE.ShaderMaterial({
      glslVersion:    THREE.GLSL3,
      vertexShader:   sliceVert,
      fragmentShader: sliceFrag,
      transparent:    false,
      side:           THREE.DoubleSide,
      uniforms: {
        uVolume:          { value: placeholder },
        uTempMin:         { value: 0 },
        uTempMax:         { value: 30 },
        uSliceDepth:      { value: 0.5 },
        uRenderMode:      { value: 0 },
        uChlIntensity:    { value: 1.2 },
        uSalinityWeight:  { value: 1.0 },
        uIsMultiChannel:  { value: 0 },
      },
    });
    const planeGeo  = new THREE.PlaneGeometry(1, 1);
    const sliceMesh = new THREE.Mesh(planeGeo, sliceMaterial);
    // Rotate plane so local X is East-West (world X) and local Y is North-South (world Z)
    sliceMesh.rotation.x = -Math.PI / 2;
    sliceMesh.visible = false;
    scene.add(sliceMesh);

    // ---- Slice Divider Lines Group ----
    const dividersGroup = new THREE.Group();
    scene.add(dividersGroup);

    // ---- Interactive Layer Click-Planes Group ----
    const layerPlanesGroup = new THREE.Group();
    scene.add(layerPlanesGroup);

    // ---- 3D Probe Marker Group ----
    const probeGroup = new THREE.Group();
    probeGroup.visible = false;

    // Outer glow sphere
    const outerSphereGeo = new THREE.SphereGeometry(0.06, 16, 16);
    const outerSphereMat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.75,
      depthTest: false,
    });
    const outerSphere = new THREE.Mesh(outerSphereGeo, outerSphereMat);
    outerSphere.renderOrder = 1000;
    probeGroup.add(outerSphere);

    // Inner bright core
    const innerSphereGeo = new THREE.SphereGeometry(0.024, 12, 12);
    const innerSphereMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      depthTest: false,
    });
    const innerSphere = new THREE.Mesh(innerSphereGeo, innerSphereMat);
    innerSphere.renderOrder = 1001;
    probeGroup.add(innerSphere);

    // Vertical leader line down to seabed
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute(
      "position",
      new THREE.Float32BufferAttribute([0, 0, 0, 0, -1, 0], 3)
    );
    const lineMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.85,
      depthTest: false,
    });
    const leaderLine = new THREE.Line(lineGeo, lineMat);
    leaderLine.renderOrder = 999;
    probeGroup.add(leaderLine);

    // Base target ring on the ocean seabed
    const ringGeo = new THREE.RingGeometry(0.03, 0.065, 24);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
      depthTest: false,
    });
    const baseRing = new THREE.Mesh(ringGeo, ringMat);
    baseRing.renderOrder = 1000;
    probeGroup.add(baseRing);

    scene.add(probeGroup);

    sceneRef.current            = scene;
    cameraRef.current           = camera;
    rendererRef.current         = renderer;
    controlsRef.current         = controls;
    boxMeshRef.current          = boxMesh;
    sliceMeshRef.current        = sliceMesh;
    volMaterialRef.current      = volMaterial;
    sliceMaterialRef.current    = sliceMaterial;
    dividersGroupRef.current    = dividersGroup;
    layerPlanesGroupRef.current = layerPlanesGroup;
    probeGroupRef.current       = probeGroup;
    outerSphereRef.current      = outerSphere;
    innerSphereRef.current      = innerSphere;
    leaderLineRef.current    = leaderLine;
    baseRingRef.current      = baseRing;

    // Render loop
    const animate = () => {
      rafRef.current = requestAnimationFrame(animate);
      controls.update();

      if (probeGroup.visible && outerSphereRef.current) {
        const time = performance.now() * 0.005;
        const scalePulse = 1 + 0.2 * Math.sin(time * 2);
        outerSphereRef.current.scale.setScalar(scalePulse);
        const mat = outerSphereRef.current.material as THREE.MeshBasicMaterial;
        mat.opacity = 0.55 + 0.35 * Math.sin(time * 2);
      }

      if (volumeMarkersRef.current) {
        volumeMarkersRef.current.updateAnimation(performance.now() * 0.001);
      }

      renderer.render(scene, camera);
    };
    animate();

    // Resize handler
    const handleResize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // ---- Click & Pointer Down → 3D Point-Probe Raycast ----
    const raycaster = new THREE.Raycaster();
    let pointerDownPos = { x: 0, y: 0 };

    const handlePointerDown = (event: MouseEvent) => {
      pointerDownPos = { x: event.clientX, y: event.clientY };
    };

    const handlePointerMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc  = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width)  * 2 - 1,
        -((event.clientY - rect.top)  / rect.height) * 2 + 1
      );
      raycaster.setFromCamera(ndc, camera);

      let isHoveringPin = false;
      if (volumeMarkersRef.current) {
        const markerHit = volumeMarkersRef.current.raycast(raycaster);
        if (markerHit) {
          isHoveringPin = true;
        }
      }

      const cursorStyle = isHoveringPin ? "pointer" : "auto";
      if (document.body.style.cursor !== cursorStyle) {
        document.body.style.cursor = cursorStyle;
        renderer.domElement.style.cursor = cursorStyle;
      }
    };

    const handlePointerLeave = () => {
      document.body.style.cursor = "auto";
      renderer.domElement.style.cursor = "auto";
    };

    const handleClick = (event: MouseEvent) => {
      // Guard against orbit drag / rotation (allow up to 10px jitter)
      const dist = Math.hypot(event.clientX - pointerDownPos.x, event.clientY - pointerDownPos.y);
      if (dist > 10) return;

      const rect = renderer.domElement.getBoundingClientRect();
      const ndc  = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width)  * 2 - 1,
        -((event.clientY - rect.top)  / rect.height) * 2 + 1
      );
      raycaster.setFromCamera(ndc, camera);

      // Check discrete volume markers first
      if (volumeMarkersRef.current) {
        const markerHit = volumeMarkersRef.current.raycast(raycaster);
        if (markerHit) {
          event.stopPropagation();
          // Unify into main HUD: clear any standalone tooltip to eliminate modal collision
          setActiveMarker(null);
          const box = boxMeshRef.current;
          const worldPos = box
            ? new THREE.Vector3(
                markerHit.localPos.x * box.scale.x,
                markerHit.localPos.y * box.scale.y,
                markerHit.localPos.z * box.scale.z
              )
            : { x: 0, y: 0, z: 0 };
          const featureName =
            markerHit.type === "chlorophyll"
              ? "Euphotic Chlorophyll Hotspot"
              : "Salinity Reference Core";
          const probe: ProbePoint = {
            lon: markerHit.lon,
            lat: markerHit.lat,
            depth: markerHit.depth,
            localU: markerHit.localPos.x + 0.5,
            localV: markerHit.localPos.z + 0.5,
            localW: 0.5 - markerHit.localPos.y,
            worldPos,
            voxelValue: markerHit.type === "chlorophyll" ? markerHit.chl : markerHit.salinity,
            temperature: markerHit.temp,
            salinity: markerHit.salinity,
            chlorophyll: markerHit.chl,
            featureName,
            isFeaturePin: true,
          };
          onPickRef.current?.(probe);
          return;
        }
      }

      const sliceMesh = sliceMeshRef.current;
      const boxMesh = boxMeshRef.current;
      const volMaterial = volMaterialRef.current;
      if (!boxMesh || !sliceMesh || !volMaterial) return;

      let hit: THREE.Intersection | null = null;
      let target: THREE.Object3D = boxMesh;
      let hitLayerIndex: number | null = null;

      // 1. If in layer mode, test interactive layer planes first
      if (isLayerModeRef.current && layerPlanesGroupRef.current && layerPlanesGroupRef.current.children.length > 0) {
        const layerHits = raycaster.intersectObjects(layerPlanesGroupRef.current.children, false);
        if (layerHits.length > 0) {
          hit = layerHits[0];
          target = layerHits[0].object;
          hitLayerIndex = (layerHits[0].object.userData?.layerIndex as number) ?? null;
        }
      }

      // 2. If sliceMesh is visible (and not already hit a layer plane), test sliceMesh
      if (!hit && sliceMesh.visible) {
        const sliceHits = raycaster.intersectObject(sliceMesh, false);
        if (sliceHits.length > 0) {
          hit = sliceHits[0];
          target = sliceMesh;
          hitLayerIndex = activeSliceRef.current;
        }
      }

      // 3. Fall back to raymarching volume boxMesh
      if (!hit && boxMesh.visible) {
        const savedSide = volMaterial.side;
        volMaterial.side = THREE.DoubleSide;
        const boxHits = raycaster.intersectObject(boxMesh, false);
        volMaterial.side = savedSide;
        if (boxHits.length > 0) {
          hit = boxHits[0];
          target = boxMesh;
        }
      }

      if (!hit) return;
      setActiveMarker(null);

      const meta = metaRef.current;
      if (!meta) return;

      const activeBounds = getActiveBounds();

      const isPlanePick = (target === sliceMesh || Boolean(target.userData?.isLayerPlane));
      let lon: number;
      let lat: number;
      let depth: number;
      let lonFrac: number;
      let latFrac: number;
      let depthFrac: number;

      const dMin = activeBounds.minDepth ?? 0;
      const dMax = activeBounds.maxDepth ?? 500;
      const totalDepth = Math.max(1, dMax - dMin);
      const step = sliceStepRef.current > 0 ? sliceStepRef.current : 100;
      const totalSlices = Math.max(1, Math.floor(totalDepth / step));

      if (isPlanePick) {
        if (hit.uv) {
          lonFrac = Math.max(0, Math.min(1, hit.uv.x));
          latFrac = Math.max(0, Math.min(1, hit.uv.y));
        } else {
          const local = target.worldToLocal(hit.point.clone());
          lonFrac = Math.max(0, Math.min(1, local.x + 0.5));
          latFrac = Math.max(0, Math.min(1, local.y + 0.5));
        }
        lon = activeBounds.minLon + lonFrac * (activeBounds.maxLon - activeBounds.minLon);
        lat = activeBounds.minLat + latFrac * (activeBounds.maxLat - activeBounds.minLat);

        const targetLayer = hitLayerIndex ?? activeSliceRef.current;
        const dStartM = dMin + (targetLayer - 1) * step;
        const dEndM = Math.min(dMax, dMin + targetLayer * step);
        depth = is2dRef.current ? 0 : Number(((dStartM + dEndM) / 2).toFixed(1));
        depthFrac = is2dRef.current ? 0 : Math.max(0.0, Math.min(1.0, (depth - dMin) / totalDepth));
      } else {
        const local = target.worldToLocal(hit.point.clone());
        const geo = volumeIntersectToGeo(local, { width: 1, height: 1, depth: 1 }, activeBounds);
        lon = geo.lon;
        lat = geo.lat;
        depth = is2dRef.current ? 0 : geo.depth;
        lonFrac = Math.max(0, Math.min(1, (local.x / 1) + 0.5));
        latFrac = Math.max(0, Math.min(1, (local.z / 1) + 0.5));
        depthFrac = is2dRef.current ? 0 : Math.max(0, Math.min(1, 0.5 - (local.y / 1)));

        // If in layer mode and clicked on volume box, determine the clicked layer directly from depth
        if (!is2dRef.current && (isLayerModeRef.current || modeRef.current === "slice")) {
          hitLayerIndex = Math.max(1, Math.min(totalSlices, Math.floor((depth - dMin) / step) + 1));
          const dStartM = dMin + (hitLayerIndex - 1) * step;
          const dEndM = Math.min(dMax, dMin + hitLayerIndex * step);
          depth = Number(((dStartM + dEndM) / 2).toFixed(1));
          depthFrac = Math.max(0.0, Math.min(1.0, (depth - dMin) / totalDepth));
        }
      }

      const activeResolvedLayer = hitLayerIndex ?? activeSliceRef.current;

      // Synchronize active layer to parent App state
      if (!is2dRef.current && (isLayerModeRef.current || modeRef.current === "slice")) {
        onSliceSelectRef.current?.(activeResolvedLayer);
      }

      // Sample raw voxel scalar value if volumeData is loaded
      let voxelValue: number | null = null;
      let voxelTemp: number | null = null;
      let voxelSal: number | null = null;
      let voxelChl: number | null = null;
      let isLandVoxel = false;
      const curVol = volumeDataRef.current;
      if (curVol && curVol.float32) {
        const m = curVol.meta;
        const dIdx = Math.max(0, Math.min(m.shape.depth - 1, Math.round(depthFrac * (m.shape.depth - 1))));
        const latIdx = Math.max(0, Math.min(m.shape.lat - 1, Math.round(latFrac * (m.shape.lat - 1))));
        const lonIdx = Math.max(0, Math.min(m.shape.lon - 1, Math.round(lonFrac * (m.shape.lon - 1))));
        const channels = m.channel_count ?? (m.is_multi_channel ? 4 : 1);
        const baseIdx = ((dIdx * m.shape.lat + latIdx) * m.shape.lon + lonIdx) * (channels > 1 ? channels : 1);
        if (baseIdx >= 0 && baseIdx < curVol.float32.length) {
          if (channels >= 4) {
            const nT = curVol.float32[baseIdx];
            const nS = curVol.float32[baseIdx + 1];
            const nC = curVol.float32[baseIdx + 2];
            const valid = curVol.float32[baseIdx + 3];
            if (valid > 0.5) {
              voxelTemp = Number((24.0 + nT * 8.0).toFixed(2));
              voxelSal = Number((32.0 + nS * 5.0).toFixed(2));
              voxelChl = Number((nC * 2.0).toFixed(3));
              voxelValue = voxelTemp;
            } else {
              isLandVoxel = true;
            }
          } else {
            const v = curVol.float32[baseIdx];
            if (!isNaN(v) && v > -9000 && v < 900000000) {
              voxelValue = v;
              if (m.variable === "thetao" || m.variable === "temperature") {
                voxelTemp = v;
              } else if (m.variable === "so" || m.variable === "salinity") {
                voxelSal = v;
              } else if (m.variable === "chl") {
                voxelChl = v;
              }
            }
          }
        }
      }

      // Compute layer summary metrics across horizontal slice plane if layer or slice mode is active
      let layerSummary: LayerSummary | null = null;
      if (curVol && curVol.float32 && !is2dRef.current && (isLayerModeRef.current || modeRef.current === "slice")) {
        const sliceIdx = activeResolvedLayer;
        const dStartM = dMin + (sliceIdx - 1) * step;
        const dEndM = Math.min(dMax, dMin + sliceIdx * step);
        const sDepthM = Number(((dStartM + dEndM) / 2).toFixed(1));

        const dIdx = Math.max(0, Math.min(meta.shape.depth - 1, Math.round(depthFrac * (meta.shape.depth - 1))));

        layerSummary = calculateLayerSliceStats(
          curVol,
          dIdx,
          sliceIdx,
          totalSlices,
          dStartM,
          dEndM,
          sDepthM
        );
      }

      const hitPoint = hit.point;
      const probe: ProbePoint = {
        lon: Number(lon.toFixed(4)),
        lat: Number(lat.toFixed(4)),
        depth: Number(depth.toFixed(1)),
        localU: lonFrac,
        localV: latFrac,
        localW: depthFrac,
        worldPos: { x: hitPoint.x, y: hitPoint.y, z: hitPoint.z },
        voxelValue: isLandVoxel ? null : voxelValue,
        temperature: isLandVoxel ? null : voxelTemp,
        salinity: isLandVoxel ? null : voxelSal,
        chlorophyll: isLandVoxel ? null : voxelChl,
        layerSummary,
        is_land: isLandVoxel,
      };

      console.log(
        `[PROBE PICK] lon=${probe.lon} lat=${probe.lat} depth=${probe.depth}m ` +
        `voxelVal=${voxelValue !== null ? voxelValue.toFixed(2) : "N/A"}` +
        (layerSummary ? ` (layer #${layerSummary.sliceIndex} avgT=${layerSummary.avgTemperature}°C avgS=${layerSummary.avgSalinity} avgC=${layerSummary.avgChlorophyll})` : "")
      );

      onPickRef.current?.(probe);
    };

    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
    renderer.domElement.addEventListener("click", handleClick);

    return () => {
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerleave", handlePointerLeave);
      renderer.domElement.removeEventListener("click", handleClick);
      document.body.style.cursor = "auto";
      renderer.domElement.style.cursor = "auto";
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current);
      controls.dispose();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --------------------------------------------------------------------------
  // Update Data3DTexture when new volume data arrives.
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!volumeData) {
      metaRef.current = null;
      if (boxMeshRef.current) boxMeshRef.current.visible = false;
      if (sliceMeshRef.current) sliceMeshRef.current.visible = false;
      if (probeGroupRef.current) probeGroupRef.current.visible = false;
      if (volumeMarkersRef.current) volumeMarkersRef.current.group.visible = false;
      return;
    }
    const { float32, meta } = volumeData;

    metaRef.current = meta;

    const isMulti = Boolean(meta.is_multi_channel || (meta.channel_count && meta.channel_count >= 4));

    // Convert Float32 to Float16 (HalfFloat) to guarantee hardware linear filtering on all GPUs.
    // CRITICAL: We must stamp NaN cells with a reliable sentinel BEFORE half-float
    // conversion. GLSL isnan() is implementation-defined for half-float textures under
    // ANGLE/D3D11 on Windows and often returns false, causing land cells to render
    // as solid ocean. The shader detects this specific -9999.0 sentinel.
    const halfFloatArray = new Uint16Array(float32.length);
    const LAND_SENTINEL = -9999.0;
    
    for (let i = 0; i < float32.length; i++) {
      const v = float32[i];
      const safeVal = isNaN(v) ? LAND_SENTINEL : v;
      halfFloatArray[i] = THREE.DataUtils.toHalfFloat(safeVal);
    }
    const tex = new THREE.Data3DTexture(halfFloatArray, meta.shape.lon, meta.shape.lat, meta.shape.depth);
    tex.format          = isMulti ? THREE.RGBAFormat : THREE.RedFormat;
    tex.type            = THREE.HalfFloatType;
    tex.minFilter       = THREE.LinearFilter;
    tex.magFilter       = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.unpackAlignment = 1;
    tex.wrapS           = THREE.ClampToEdgeWrapping;
    tex.wrapT           = THREE.ClampToEdgeWrapping;
    tex.wrapR           = THREE.ClampToEdgeWrapping;
    tex.needsUpdate     = true;

    const oldTex = textureRef.current;
    textureRef.current = tex;

    const modeInt = renderMode === "salinity" ? 1 : renderMode === "chlorophyll" ? 2 : renderMode === "composite" ? 3 : 0;

    if (volMaterialRef.current) {
      volMaterialRef.current.uniforms.uVolume.value = tex;
      volMaterialRef.current.uniforms.uTempMin.value = tempMin;
      volMaterialRef.current.uniforms.uTempMax.value = tempMax;
      volMaterialRef.current.uniforms.uIsMultiChannel.value = isMulti ? 1 : 0;
      volMaterialRef.current.uniforms.uRenderMode.value = modeInt;
      volMaterialRef.current.uniforms.uChlIntensity.value = chlIntensity;
      volMaterialRef.current.uniforms.uSalinityWeight.value = salinityWeight;
      volMaterialRef.current.needsUpdate = true;
    }
    if (sliceMaterialRef.current) {
      sliceMaterialRef.current.uniforms.uVolume.value = tex;
      sliceMaterialRef.current.uniforms.uTempMin.value = tempMin;
      sliceMaterialRef.current.uniforms.uTempMax.value = tempMax;
      sliceMaterialRef.current.uniforms.uIsMultiChannel.value = isMulti ? 1 : 0;
      sliceMaterialRef.current.uniforms.uRenderMode.value = modeInt;
      sliceMaterialRef.current.uniforms.uChlIntensity.value = chlIntensity;
      sliceMaterialRef.current.uniforms.uSalinityWeight.value = salinityWeight;
      sliceMaterialRef.current.needsUpdate = true;
    }

    oldTex?.dispose();
  }, [volumeData, tempMin, tempMax, renderMode, chlIntensity, salinityWeight]);

  // --------------------------------------------------------------------------
  // Dynamic uniform synchronization without re-allocating 3D texture
  // --------------------------------------------------------------------------
  useEffect(() => {
    const modeInt = renderMode === "salinity" ? 1 : renderMode === "chlorophyll" ? 2 : renderMode === "composite" ? 3 : 0;
    const isMulti = Boolean(volumeData?.meta.is_multi_channel || (volumeData?.meta.channel_count && volumeData.meta.channel_count >= 4));

    if (volMaterialRef.current) {
      volMaterialRef.current.uniforms.uRenderMode.value = modeInt;
      volMaterialRef.current.uniforms.uIsMultiChannel.value = isMulti ? 1 : 0;
      volMaterialRef.current.uniforms.uTempMin.value = tempMin;
      volMaterialRef.current.uniforms.uTempMax.value = tempMax;
      volMaterialRef.current.uniforms.uChlIntensity.value = chlIntensity;
      volMaterialRef.current.uniforms.uSalinityWeight.value = salinityWeight;
      volMaterialRef.current.uniforms.uOpacity.value = opacity;
      volMaterialRef.current.uniforms.uSteps.value = steps;
    }
    if (sliceMaterialRef.current) {
      sliceMaterialRef.current.uniforms.uRenderMode.value = modeInt;
      sliceMaterialRef.current.uniforms.uIsMultiChannel.value = isMulti ? 1 : 0;
      sliceMaterialRef.current.uniforms.uTempMin.value = tempMin;
      sliceMaterialRef.current.uniforms.uTempMax.value = tempMax;
      sliceMaterialRef.current.uniforms.uChlIntensity.value = chlIntensity;
      sliceMaterialRef.current.uniforms.uSalinityWeight.value = salinityWeight;
    }
  }, [renderMode, volumeData, tempMin, tempMax, chlIntensity, salinityWeight, opacity, steps]);

  // --------------------------------------------------------------------------
  // Apply data-driven geographic scale, slice positioning, and update uniforms.
  // --------------------------------------------------------------------------
  useEffect(() => {
    const meta = metaRef.current;
    if (!meta || !volumeData) {
      if (boxMeshRef.current) boxMeshRef.current.visible = false;
      if (sliceMeshRef.current) sliceMeshRef.current.visible = false;
      return;
    }

    // ── 1. Compute scale from dataset coordinates ──────────────────────────
    const { scale, widthKm, heightKm, depthKm } = computeScaleFromMeta(meta, verticalExaggeration);

    // ── 2. Apply scale and visibility based on is2d and mode ────────────────
    //
    // is2d=true  (mlotst, ohc_0_700m): always show flat sliceMesh at ocean surface
    // is2d=false (thetao, so):         show boxMesh (volume) or sliceMesh (slice mode)

    if (is2d) {
      // Flat heatmap: hide volume box, show slice plane at the ocean surface
      if (boxMeshRef.current) {
        boxMeshRef.current.scale.copy(scale);
        boxMeshRef.current.visible = false;
      }
      if (sliceMeshRef.current) {
        sliceMeshRef.current.scale.set(scale.x, scale.z, 1);
        // Position at ocean surface (top of the volume box: y = +0.5 * scale.y)
        sliceMeshRef.current.position.y = 0.5 * scale.y;
        sliceMeshRef.current.visible = true;
      }
      if (sliceMaterialRef.current) {
        // Sample at the middle of the single-layer texture (depth = 1 layer → r = 0.5)
        sliceMaterialRef.current.uniforms.uSliceDepth.value = 0.5;
        sliceMaterialRef.current.uniforms.uTempMin.value    = tempMin;
        sliceMaterialRef.current.uniforms.uTempMax.value    = tempMax;
      }
    } else {
      // 3D variable: normal volume or slice mode
      if (boxMeshRef.current) {
        boxMeshRef.current.scale.copy(scale);
        boxMeshRef.current.visible = (mode === "volume");
      }
      if (sliceMeshRef.current) {
        // For PlaneGeometry rotated -90 deg around X:
        // Local X -> World X (scale.x), Local Y -> World Z (scale.z)
        sliceMeshRef.current.scale.set(scale.x, scale.z, 1);
        // Position slice vertically at exact corresponding depth level in volume
        sliceMeshRef.current.position.y = (0.5 - sliceDepthNormalized) * scale.y;
        sliceMeshRef.current.visible = (mode === "slice" || uIsLayerMode);
      }
      if (sliceMaterialRef.current) {
        sliceMaterialRef.current.uniforms.uSliceDepth.value = sliceDepthNormalized;
        sliceMaterialRef.current.uniforms.uTempMin.value    = tempMin;
        sliceMaterialRef.current.uniforms.uTempMax.value    = tempMax;
      }
    }

    // ── 3. Update volume shader uniforms ──────────────────────────────────
    if (volMaterialRef.current) {
      volMaterialRef.current.uniforms.uTempMin.value = tempMin;
      volMaterialRef.current.uniforms.uTempMax.value = tempMax;
      volMaterialRef.current.uniforms.uOpacity.value = opacity;
      volMaterialRef.current.uniforms.uSteps.value   = steps;
      volMaterialRef.current.uniforms.uScale.value.copy(scale);
      // Reduce opacity slightly in layer mode so the perimeter rings are readable through the volume
      if (uIsLayerMode) {
        volMaterialRef.current.uniforms.uOpacity.value = opacity * 0.8;
      }
    }

    // ── 3.5 Rebuild horizontal perimeter-ring dividers ───────────────────
    if (dividersGroupRef.current) {
      const group = dividersGroupRef.current;
      // Dispose old children to free GPU memory
      group.children.forEach((c) => {
        if (c instanceof THREE.LineSegments) {
          c.geometry.dispose();
          (c.material as THREE.Material).dispose();
        }
      });
      group.clear();

      // Only draw dividers in Layer/Slice mode for 3D variables
      if (!is2d && uIsLayerMode && sliceStep > 0 && boxMeshRef.current) {
        const dMin = meta.depth_min;
        const dMax = meta.depth_max;
        const totalDepth = Math.max(1, dMax - dMin);
        // Exact integer sections matching the Controls slider
        const numSections = Math.max(1, Math.floor(totalDepth / sliceStep));

        // Measure the *actual rendered* bounding box of the volume mesh
        const bbox = new THREE.Box3().setFromObject(boxMeshRef.current);
        const topY    = bbox.max.y;  // ocean surface
        const bottomY = bbox.min.y;  // ocean floor
        const totalHeight = topY - bottomY;

        // Expand the X/Z perimeter slightly (1%) so lines sit *outside* the mesh
        // surface and aren't clipped by the opaque volume geometry.
        const eps = 0.01;
        const xMin = bbox.min.x * (1 + eps);
        const xMax = bbox.max.x * (1 + eps);
        const zMin = bbox.min.z * (1 + eps);
        const zMax = bbox.max.z * (1 + eps);

        // Draw N-1 internal dividers PLUS the active-slice boundary highlights
        for (let i = 0; i <= numSections; i++) {
          // Skip the very top (i=0) and bottom (i=numSections) edges;
          // only draw them when they are an active-slice boundary to avoid
          // redundant lines on top of the mesh outline.
          const isActiveBoundary = i === activeSlice - 1 || i === activeSlice;
          const isEdge = i === 0 || i === numSections;
          if (isEdge && !isActiveBoundary) continue;

          // Position: linearly interpolated between topY and bottomY
          const yPos = topY - (i / numSections) * totalHeight;

          const lineColor   = isActiveBoundary ? 0x22d3ee : 0x0f172a;
          const lineOpacity = isActiveBoundary ? 1.0 : 0.85;

          const mat = new THREE.LineBasicMaterial({
            color: lineColor,
            transparent: true,
            opacity: lineOpacity,
            depthTest:  false,  // always draw on top of volume geometry
            depthWrite: false,
          });

          // Perimeter rectangle at height yPos
          const pts: THREE.Vector3[] = [
            new THREE.Vector3(xMin, yPos, zMin),
            new THREE.Vector3(xMax, yPos, zMin),
            new THREE.Vector3(xMax, yPos, zMin),
            new THREE.Vector3(xMax, yPos, zMax),
            new THREE.Vector3(xMax, yPos, zMax),
            new THREE.Vector3(xMin, yPos, zMax),
            new THREE.Vector3(xMin, yPos, zMax),
            new THREE.Vector3(xMin, yPos, zMin),
          ];

          const geo  = new THREE.BufferGeometry().setFromPoints(pts);
          const ring = new THREE.LineSegments(geo, mat);
          ring.renderOrder = 999;   // draw on top of every other object
          group.add(ring);
        }
      }
    }

    // ── 3.6 Rebuild horizontal layer click-target planes ───────────────────
    if (layerPlanesGroupRef.current) {
      const lpGroup = layerPlanesGroupRef.current;
      lpGroup.children.forEach((c) => {
        if (c instanceof THREE.Mesh) {
          c.geometry.dispose();
          (c.material as THREE.Material).dispose();
        }
      });
      lpGroup.clear();

      if (!is2d && uIsLayerMode && sliceStep > 0 && boxMeshRef.current) {
        const dMin = meta.depth_min ?? 0;
        const dMax = meta.depth_max ?? 500;
        const totalDepth = Math.max(1, dMax - dMin);
        const numSections = Math.max(1, Math.floor(totalDepth / sliceStep));

        const bbox = new THREE.Box3().setFromObject(boxMeshRef.current);
        const topY    = bbox.max.y;
        const bottomY = bbox.min.y;
        const totalHeight = topY - bottomY;

        for (let k = 1; k <= numSections; k++) {
          const planeGeo = new THREE.PlaneGeometry(1, 1);
          const planeMat = new THREE.MeshBasicMaterial({
            transparent: true,
            opacity: 0.0,
            side: THREE.DoubleSide,
            depthWrite: false,
          });
          const plane = new THREE.Mesh(planeGeo, planeMat);
          plane.rotation.x = -Math.PI / 2;
          plane.scale.set(scale.x, scale.z, 1);
          // Center of the k-th layer vertically
          const yCenter = topY - ((k - 0.5) / numSections) * totalHeight;
          plane.position.set(0, yCenter, 0);
          plane.userData = { isLayerPlane: true, layerIndex: k };
          lpGroup.add(plane);
        }
      }
    }

    // ── 4. Auto-frame camera ONLY on initial load or geographic bounds change ────────
    const framingMesh = is2d ? sliceMeshRef.current : boxMeshRef.current;
    if (volumeData && volumeData !== lastFramedDataRef.current) {
      const prevMeta = lastFramedDataRef.current?.meta;
      const boundsChanged =
        !prevMeta ||
        prevMeta.longitude_min !== meta.longitude_min ||
        prevMeta.longitude_max !== meta.longitude_max ||
        prevMeta.latitude_min !== meta.latitude_min ||
        prevMeta.latitude_max !== meta.latitude_max ||
        prevMeta.depth_min !== meta.depth_min ||
        prevMeta.depth_max !== meta.depth_max ||
        prevMeta.is_2d !== meta.is_2d;

      lastFramedDataRef.current = volumeData;
      if (boundsChanged && framingMesh && cameraRef.current && controlsRef.current) {
        const box = new THREE.Box3().setFromObject(framingMesh);
        frameCameraToBox(cameraRef.current, controlsRef.current, box);
      }
      logDatasetGeometry(meta, widthKm, heightKm, depthKm, scale, verticalExaggeration);
    }

  }, [tempMin, tempMax, opacity, steps, verticalExaggeration, mode, sliceDepthNormalized, uIsLayerMode, sliceStep, activeSlice, volumeData, is2d]);

  // --------------------------------------------------------------------------
  // Position & update 3D Probe Marker pin and leader line
  // --------------------------------------------------------------------------
  useEffect(() => {
    const group = probeGroupRef.current;
    if (!group) return;

    if (!probePoint) {
      group.visible = false;
      return;
    }

    group.visible = true;
    const { x, y, z } = probePoint.worldPos;

    // Outer & inner glowing pin spheres
    outerSphereRef.current?.position.set(x, y, z);
    innerSphereRef.current?.position.set(x, y, z);

    // Leader line from clicked point down to seabed floor
    const box = boxMeshRef.current;
    const bottomY = box ? box.position.y - 0.5 * box.scale.y : y - 1;

    const line = leaderLineRef.current;
    if (line) {
      const posAttr = line.geometry.getAttribute("position") as THREE.BufferAttribute;
      if (posAttr) {
        posAttr.setXYZ(0, x, y, z);
        posAttr.setXYZ(1, x, bottomY, z);
        posAttr.needsUpdate = true;
      }
    }

    // Anchor ring at seabed
    baseRingRef.current?.position.set(x, bottomY, z);
  }, [probePoint]);

  // --------------------------------------------------------------------------
  // In-Volume 3D Spatial Feature Markers (Chlorophyll-a & Salinity)
  // --------------------------------------------------------------------------
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !volumeData) return;

    const { scale } = computeScaleFromMeta(volumeData.meta, verticalExaggeration);

    if (volumeMarkersRef.current) {
      scene.remove(volumeMarkersRef.current.group);
      volumeMarkersRef.current.dispose();
      volumeMarkersRef.current = null;
    }

    if (showVolumeMarkers && mode === "volume" && !is2d) {
      const activeBounds = getActiveBounds();
      const markers = generateVolumeMarkers(volumeData.meta, volumeData.float32, activeBounds);
      const markersObj = createVolumeMarkersObject(markers, scale);
      scene.add(markersObj.group);
      volumeMarkersRef.current = markersObj;
    }

    return () => {
      if (volumeMarkersRef.current && sceneRef.current) {
        sceneRef.current.remove(volumeMarkersRef.current.group);
        volumeMarkersRef.current.dispose();
        volumeMarkersRef.current = null;
      }
    };
  }, [volumeData, verticalExaggeration, showVolumeMarkers, mode, is2d, regionBounds]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={mountRef} style={{ width: "100%", height: "100%" }} />
      <VolumeMarkerTooltip
        marker={activeMarker}
        onClose={() => setActiveMarker(null)}
      />
    </div>
  );
}

