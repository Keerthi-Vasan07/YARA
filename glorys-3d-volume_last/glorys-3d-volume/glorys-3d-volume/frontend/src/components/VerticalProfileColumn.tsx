import * as THREE from "three";
import type { ProbeVariable, VerticalColumnPoint } from "../types";
import {
  latLonDepthToVector3,
  getProbeVariableColor,
  GLOBE_RADIUS,
  DEFAULT_SHELL_THICKNESS,
} from "../utils/geoCoordinates";

export interface Column3DObject {
  group: THREE.Group;
  updateColors: (variable: ProbeVariable) => void;
  dispose: () => void;
}

/**
 * Builds a Three.js 3D Subsurface Column Probe anchored at (lat, lon).
 * Contains:
 *   - Luminous surface landing collar (ring)
 *   - Semi-transparent vertical guide filament connecting surface to deep abyss
 *   - Volumetric node spheres at each sampled depth step colored by active variable
 */
export function createVerticalColumnMesh(
  lat: number,
  lon: number,
  profile: VerticalColumnPoint[],
  activeVariable: ProbeVariable,
  maxDepth: number = 1000.0,
  globeRadius: number = GLOBE_RADIUS,
  shellThickness: number = DEFAULT_SHELL_THICKNESS
): Column3DObject {
  const group = new THREE.Group();
  group.name = `SubsurfaceColumn_${lat.toFixed(2)}_${lon.toFixed(2)}`;

  const nodeMeshes: { mesh: THREE.Mesh; point: VerticalColumnPoint }[] = [];
  const disposables: (THREE.BufferGeometry | THREE.Material)[] = [];

  // 1. Surface Landing Collar Marker (Torus/Ring)
  const surfacePos = latLonDepthToVector3(lat, lon, 0, maxDepth, globeRadius * 1.003, shellThickness);
  const ringGeo = new THREE.RingGeometry(0.016, 0.024, 24);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x38bdf8, // light cyan beacon
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.9,
    depthWrite: false,
  });
  const ringMesh = new THREE.Mesh(ringGeo, ringMat);
  ringMesh.position.copy(surfacePos);
  ringMesh.lookAt(new THREE.Vector3(0, 0, 0)); // Align perpendicular to globe surface normal
  group.add(ringMesh);
  disposables.push(ringGeo, ringMat);

  // 2. Guide Filament Line connecting surface to deep layers
  const filamentPoints: THREE.Vector3[] = [];
  for (const pt of profile) {
    const pos = latLonDepthToVector3(lat, lon, pt.depth_m, maxDepth, globeRadius, shellThickness);
    filamentPoints.push(pos);
  }

  if (filamentPoints.length >= 2) {
    const lineGeo = new THREE.BufferGeometry().setFromPoints(filamentPoints);
    const lineMat = new THREE.LineBasicMaterial({
      color: 0x7dd3fc,
      transparent: true,
      opacity: 0.65,
      linewidth: 2,
    });
    const lineMesh = new THREE.Line(lineGeo, lineMat);
    group.add(lineMesh);
    disposables.push(lineGeo, lineMat);
  }

  // 3. Volumetric Node Spheres at each depth step
  const sphereGeo = new THREE.SphereGeometry(0.012, 16, 16);
  disposables.push(sphereGeo);

  for (const pt of profile) {
    const pos = latLonDepthToVector3(lat, lon, pt.depth_m, maxDepth, globeRadius, shellThickness);
    const val = pt[activeVariable];
    const col = getProbeVariableColor(activeVariable, val);

    const sphereMat = new THREE.MeshBasicMaterial({
      color: col,
      transparent: true,
      opacity: 0.95,
    });
    const sphereMesh = new THREE.Mesh(sphereGeo, sphereMat);
    sphereMesh.position.copy(pos);
    group.add(sphereMesh);

    disposables.push(sphereMat);
    nodeMeshes.push({ mesh: sphereMesh, point: pt });
  }

  // Color update method for dynamic switching without rebuilding
  const updateColors = (variable: ProbeVariable) => {
    for (const item of nodeMeshes) {
      const val = item.point[variable];
      const newColor = getProbeVariableColor(variable, val);
      (item.mesh.material as THREE.MeshBasicMaterial).color.copy(newColor);
    }
  };

  const dispose = () => {
    while (group.children.length > 0) {
      group.remove(group.children[0]);
    }
    for (const res of disposables) {
      res.dispose();
    }
  };

  return { group, updateColors, dispose };
}
