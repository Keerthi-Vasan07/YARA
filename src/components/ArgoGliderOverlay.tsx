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

      source.entities.add({
        id: `argo-${float.id}-trajectory`,
        polyline: {
          positions,
          width: 2,
          material: Cesium.Color.YELLOW.withAlpha(0.72),
          clampToGround: true,
        },
      });

      const last = valid[valid.length - 1];
      source.entities.add({
        id: `argo-${float.id}`,
        position: Cesium.Cartesian3.fromDegrees(last.lon, last.lat, 0),
        point: {
          pixelSize: 8,
          color: Cesium.Color.YELLOW,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        properties: {
          kind: 'argo',
          platform: float.id,
          latitude: last.lat,
          longitude: last.lon,
          time: last.time ?? null,
          depth: last.depth ?? null,
          temperature: last.temperature ?? null,
          salinity: last.salinity ?? null,
          pressure: last.pressure ?? null,
          cycle: last.cycle ?? null,
          source: (float as { source?: unknown }).source ?? null,
        },
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

      source.entities.add({
        id: `glider-${glider.id}-trajectory`,
        polyline: {
          positions,
          width: 3,
          material: Cesium.Color.CYAN.withAlpha(0.8),
          clampToGround: true,
        },
      });

      const first = valid[0];
      const last = valid[valid.length - 1];

      source.entities.add({
        id: `glider-${glider.id}-start`,
        position: Cesium.Cartesian3.fromDegrees(first.lon, first.lat, 0),
        point: {
          pixelSize: 6,
          color: Cesium.Color.CYAN,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
      });

      source.entities.add({
        id: `glider-${glider.id}-end`,
        position: Cesium.Cartesian3.fromDegrees(last.lon, last.lat, 0),
        point: {
          pixelSize: 9,
          color: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.CYAN,
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        properties: {
          kind: 'glider',
          platform: glider.id,
          latitude: last.lat,
          longitude: last.lon,
          time: last.time ?? null,
          depth: last.depth ?? null,
          temperature: last.temperature ?? null,
          salinity: last.salinity ?? null,
          pressure: (last as { pressure?: unknown }).pressure ?? null,
          source: (glider as { source?: unknown }).source ?? (last as { source?: unknown }).source ?? null,
        },
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
