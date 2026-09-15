import * as THREE from "three";
import { latLonToVector3, GLOBE_RADIUS } from "../utils/geoCoordinates";

export interface DatasetBounds {
  latMin: number;
  latMax: number;
  lonMin: number;
  lonMax: number;
}

// Local NetCDF primary dataset coverage (GLORYS / Indian Ocean reanalysis fixture)
export const DEFAULT_DATASET_BOUNDS: DatasetBounds = {
  latMin: -2.83,
  latMax: 22.83,
  lonMin: 42.00,
  lonMax: 107.42,
};

export interface DatasetBoundingBoxObject {
  group: THREE.Group;
  setVisible: (visible: boolean) => void;
  dispose: () => void;
}

/**
 * Creates a geodesic bounding box mesh on the sphere surface representing
 * the NetCDF dataset coverage boundary.
 *
 * Uses dense geodesic interpolation and a slight radial offset (r = R_globe * 1.002)
 * to prevent Z-fighting against the Earth surface texture.
 */
export function createDatasetBoundingBox(
  bounds: DatasetBounds = DEFAULT_DATASET_BOUNDS,
  radius: number = GLOBE_RADIUS,
  color: number = 0x00e5ff
): DatasetBoundingBoxObject {
  const group = new THREE.Group();
  group.name = "DatasetCoverageFootprint";

  const r = radius * 1.002;
  const samples = 32; // smooth geodesic arc resolution
  const linePoints: THREE.Vector3[] = [];
  const disposables: (THREE.BufferGeometry | THREE.Material)[] = [];

  const { latMin, latMax, lonMin, lonMax } = bounds;

  // 1. Bottom edge: (latMin, lonMin -> lonMax)
  for (let i = 0; i <= samples; i++) {
    const lon = lonMin + (lonMax - lonMin) * (i / samples);
    linePoints.push(latLonToVector3(latMin, lon, r));
  }
  // 2. Right edge: (lonMax, latMin -> latMax)
  for (let i = 0; i <= samples; i++) {
    const lat = latMin + (latMax - latMin) * (i / samples);
    linePoints.push(latLonToVector3(lat, lonMax, r));
  }
  // 3. Top edge: (latMax, lonMax -> lonMin)
  for (let i = 0; i <= samples; i++) {
    const lon = lonMax - (lonMax - lonMin) * (i / samples);
    linePoints.push(latLonToVector3(latMax, lon, r));
  }
  // 4. Left edge: (lonMin, latMax -> latMin)
  for (let i = 0; i <= samples; i++) {
    const lat = latMax - (latMax - latMin) * (i / samples);
    linePoints.push(latLonToVector3(lat, lonMin, r));
  }

  // Geodesic boundary loop line
  const lineGeo = new THREE.BufferGeometry().setFromPoints(linePoints);
  const lineMat = new THREE.LineBasicMaterial({
    color,
    linewidth: 2,
    transparent: true,
    opacity: 0.8,
  });
  const lineMesh = new THREE.Line(lineGeo, lineMat);
  group.add(lineMesh);
  disposables.push(lineGeo, lineMat);

  // 5. Corner Accent Pins
  const corners = [
    { lat: latMin, lon: lonMin },
    { lat: latMin, lon: lonMax },
    { lat: latMax, lon: lonMax },
    { lat: latMax, lon: lonMin },
  ];

  const cornerGeo = new THREE.SphereGeometry(0.008, 12, 12);
  const cornerMat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.9,
  });
  disposables.push(cornerGeo, cornerMat);

  for (const c of corners) {
    const pos = latLonToVector3(c.lat, c.lon, r * 1.001);
    const m = new THREE.Mesh(cornerGeo, cornerMat);
    m.position.copy(pos);
    group.add(m);
  }

  // 6. Subtle Translucent Surface Footprint Wash
  const gridN = 12;
  const fillPoints: number[] = [];
  const indices: number[] = [];

  for (let j = 0; j <= gridN; j++) {
    const lat = latMin + (latMax - latMin) * (j / gridN);
    for (let i = 0; i <= gridN; i++) {
      const lon = lonMin + (lonMax - lonMin) * (i / gridN);
      const v = latLonToVector3(lat, lon, r * 0.9995);
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
    color,
    transparent: true,
    opacity: 0.08,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const fillMesh = new THREE.Mesh(fillGeo, fillMat);
  group.add(fillMesh);
  disposables.push(fillGeo, fillMat);

  const setVisible = (visible: boolean) => {
    group.visible = visible;
  };

  const dispose = () => {
    while (group.children.length > 0) {
      group.remove(group.children[0]);
    }
    for (const res of disposables) {
      res.dispose();
    }
  };

  return { group, setVisible, dispose };
}
