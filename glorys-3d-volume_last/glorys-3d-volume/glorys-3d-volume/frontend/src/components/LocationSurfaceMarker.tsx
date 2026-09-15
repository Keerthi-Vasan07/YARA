import * as THREE from "three";
import { latLonToVector3, GLOBE_RADIUS } from "../utils/geoCoordinates";

export interface LocationMarkerObject {
  group: THREE.Group;
  setPosition: (lat: number, lon: number) => void;
  updateAnimation: (timeSec: number) => void;
  dispose: () => void;
}

/**
 * Creates an interactive surface location marker pin with crosshairs,
 * luminous beacon core, and an animated pulsating radar ring.
 *
 * Automatically orients perpendicular to the globe surface normal:
 *   normal = surfacePos.clone().normalize()
 *   q = Quaternion.setFromUnitVectors((0, 1, 0), normal)
 */
export function createLocationSurfaceMarker(
  lat: number,
  lon: number,
  radius: number = GLOBE_RADIUS,
  color: number = 0x38bdf8
): LocationMarkerObject {
  const group = new THREE.Group();
  group.name = "ActiveLocationSurfaceMarker";

  const disposables: (THREE.BufferGeometry | THREE.Material)[] = [];

  // Local child container oriented to the surface normal
  const markerContainer = new THREE.Group();
  group.add(markerContainer);

  // 1. Crosshairs (+ reticle)
  const crosshairLen = 0.035;
  const crosshairPoints = [
    new THREE.Vector3(-crosshairLen, 0, 0),
    new THREE.Vector3(crosshairLen, 0, 0),
    new THREE.Vector3(0, 0, -crosshairLen),
    new THREE.Vector3(0, 0, crosshairLen),
  ];
  const crosshairGeo = new THREE.BufferGeometry().setFromPoints(crosshairPoints);
  const crosshairMat = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.85,
  });
  const crosshairLines = new THREE.LineSegments(crosshairGeo, crosshairMat);
  markerContainer.add(crosshairLines);
  disposables.push(crosshairGeo, crosshairMat);

  // 2. Central Core Beacon Dot
  const coreGeo = new THREE.SphereGeometry(0.012, 16, 16);
  const coreMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.95,
  });
  const coreMesh = new THREE.Mesh(coreGeo, coreMat);
  markerContainer.add(coreMesh);
  disposables.push(coreGeo, coreMat);

  // 3. Anchor Stem Pin Needle (points into the ocean surface toward subsurface pillar)
  const stemGeo = new THREE.CylinderGeometry(0.002, 0.002, 0.025, 8);
  const stemMat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.9,
  });
  const stemMesh = new THREE.Mesh(stemGeo, stemMat);
  stemMesh.position.y = -0.0125;
  markerContainer.add(stemMesh);
  disposables.push(stemGeo, stemMat);

  // 4. Pulsating Radar Beacon Ring
  const pulseRingGeo = new THREE.RingGeometry(0.015, 0.022, 32);
  const pulseRingMat = new THREE.MeshBasicMaterial({
    color,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.8,
    depthWrite: false,
  });
  const pulseRing = new THREE.Mesh(pulseRingGeo, pulseRingMat);
  pulseRing.rotation.x = Math.PI / 2; // Flat on local horizontal plane
  markerContainer.add(pulseRing);
  disposables.push(pulseRingGeo, pulseRingMat);

  // Function to set / update coordinates
  const setPosition = (newLat: number, newLon: number) => {
    const surfacePos = latLonToVector3(newLat, newLon, radius * 1.004);
    group.position.copy(surfacePos);

    // Compute surface normal & orient container perpendicular to sphere
    const normal = surfacePos.clone().normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal);
    markerContainer.quaternion.copy(q);
  };

  // Initial positioning
  setPosition(lat, lon);

  // Pulsing animation in render loop
  const updateAnimation = (timeSec: number) => {
    // Pulse cycle every 1.4 seconds
    const cycle = (timeSec % 1.4) / 1.4;
    const scale = 1.0 + cycle * 1.2; // expand 1.0x -> 2.2x
    pulseRing.scale.set(scale, scale, 1);
    pulseRingMat.opacity = (1.0 - cycle) * 0.85; // fade out as it expands
  };

  const dispose = () => {
    while (group.children.length > 0) {
      group.remove(group.children[0]);
    }
    for (const res of disposables) {
      res.dispose();
    }
  };

  return { group, setPosition, updateAnimation, dispose };
}
