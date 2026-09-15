import { useEffect, useRef } from 'react';
import * as Cesium from 'cesium';
import type { ArgoFloat, GliderPlatform } from '../api/argoGliderApi';

interface Props {
  viewer: Cesium.Viewer | null;
  argoFloats: ArgoFloat[];
  gliders: GliderPlatform[];
  argoVisible: boolean;
  gliderVisible: boolean;
}

export function ArgoGliderOverlay({
  viewer,
  argoFloats,
  gliders,
  argoVisible,
  gliderVisible,
}: Props) {
  const argoSourceRef = useRef<Cesium.CustomDataSource | null>(null);
  const gliderSourceRef = useRef<Cesium.CustomDataSource | null>(null);

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const argo = new Cesium.CustomDataSource('yara-argo-overlay');
    const glider = new Cesium.CustomDataSource('yara-glider-overlay');
    argo.show = argoVisible;
    glider.show = gliderVisible;
    viewer.dataSources.add(argo);
    viewer.dataSources.add(glider);
    argoSourceRef.current = argo;
    gliderSourceRef.current = glider;

    return () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(argo, true);
        viewer.dataSources.remove(glider, true);
      }
      argoSourceRef.current = null;
      gliderSourceRef.current = null;
    };
  }, [viewer]);

  useEffect(() => {
    const source = argoSourceRef.current;
    if (!source) return;
    source.entities.removeAll();

    for (const float of argoFloats) {
      const valid = float.observations.filter(
        (p) => Number.isFinite(p.lon) && Number.isFinite(p.lat),
      );
      if (!valid.length) continue;

      const positions = valid.map((p) =>
        Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
      );

      if (positions.length > 1) {
        source.entities.add({
          id: `argo-${float.id}-trajectory`,
          polyline: {
            positions,
            width: 2,
            material: Cesium.Color.YELLOW.withAlpha(0.72),
            clampToGround: true,
          },
        });
      }

      // One entity per observation so every cycle's real measurements stay
      // inspectable (the source reports temperature/salinity/pressure/cycle
      // per observation, not just for the latest fix). The most recent
      // observation is drawn larger to mark the float's current position.
      const source_name = (float as { source?: unknown }).source ?? null;
      valid.forEach((p, i) => {
        const isLatest = i === valid.length - 1;
        source.entities.add({
          id: `argo-${float.id}-obs-${i}`,
          position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
          point: {
            pixelSize: isLatest ? 9 : 5,
            color: Cesium.Color.YELLOW,
            outlineColor: isLatest ? Cesium.Color.BLACK : Cesium.Color.YELLOW.darken(0.5, new Cesium.Color()),
            outlineWidth: 1,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            ...(isLatest ? { disableDepthTestDistance: Number.POSITIVE_INFINITY } : {}),
          },
          properties: {
            kind: 'argo',
            platform: float.id,
            latitude: p.lat,
            longitude: p.lon,
            time: p.time ?? null,
            depth: p.depth ?? null,
            temperature: p.temperature ?? null,
            salinity: p.salinity ?? null,
            pressure: p.pressure ?? null,
            cycle: p.cycle ?? null,
            source: source_name,
          },
        });
      });
    }
  }, [argoFloats]);

  useEffect(() => {
    const source = gliderSourceRef.current;
    if (!source) return;
    source.entities.removeAll();

    for (const glider of gliders) {
      const valid = glider.points.filter(
        (p) => Number.isFinite(p.lon) && Number.isFinite(p.lat),
      );
      if (!valid.length) continue;

      const positions = valid.map((p) =>
        Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
      );

      if (positions.length > 1) {
        source.entities.add({
          id: `glider-${glider.id}-trajectory`,
          polyline: {
            positions,
            width: 3,
            material: Cesium.Color.CYAN.withAlpha(0.8),
            clampToGround: true,
          },
        });
      }

      // One entity per glider fix, same rationale as Argo above. The final
      // fix is highlighted so the glider's latest position stays obvious.
      const gliderSource = (glider as { source?: unknown }).source ?? null;
      valid.forEach((p, i) => {
        const isLatest = i === valid.length - 1;
        source.entities.add({
          id: `glider-${glider.id}-obs-${i}`,
          position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
          point: {
            pixelSize: isLatest ? 9 : 4,
            color: isLatest ? Cesium.Color.WHITE : Cesium.Color.CYAN,
            outlineColor: Cesium.Color.CYAN,
            outlineWidth: isLatest ? 2 : 1,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            ...(isLatest ? { disableDepthTestDistance: Number.POSITIVE_INFINITY } : {}),
          },
          properties: {
            kind: 'glider',
            platform: glider.id,
            latitude: p.lat,
            longitude: p.lon,
            time: p.time ?? null,
            depth: p.depth ?? null,
            temperature: p.temperature ?? null,
            salinity: p.salinity ?? null,
            pressure: (p as { pressure?: unknown }).pressure ?? null,
            source: gliderSource ?? (p as { source?: unknown }).source ?? null,
          },
        });
      });
    }
  }, [gliders]);

  useEffect(() => {
    if (argoSourceRef.current) argoSourceRef.current.show = argoVisible;
    if (gliderSourceRef.current) gliderSourceRef.current.show = gliderVisible;
    viewer?.scene.requestRender();
  }, [argoVisible, gliderVisible, viewer]);

  return null;
}
