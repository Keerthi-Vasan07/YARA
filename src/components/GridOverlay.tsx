import { useEffect, useState } from 'react';
import * as Cesium from 'cesium';
import { Alert, Box } from '@mui/material';
import { fetchLocalGrid } from '../services/localDatasetApi';

export function GridOverlay({ viewer, datasetId, variable }: { viewer: Cesium.Viewer; datasetId: string; variable: string }) {
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const entities: Cesium.Entity[] = [];
    setMessage('Loading dataset grid…'); setError(false);
    fetchLocalGrid(datasetId, variable, controller.signal).then(grid => {
      if (controller.signal.aborted || viewer.isDestroyed()) return;
      const { west, east, south, north } = grid.extent;
      const addLine = (points: number[]) => entities.push(viewer.entities.add({ polyline: {
        positions: Cesium.Cartesian3.fromDegreesArray(points), width: 1,
        material: Cesium.Color.WHITE.withAlpha(0.45), arcType: Cesium.ArcType.NONE,
      } }));
      // Densify geographic lines. Endpoints alone would draw chords through Earth.
      for (const lat of grid.latitudes) {
        const points: number[] = [];
        const count = Math.max(1, Math.ceil(east - west));
        for (let i = 0; i <= count; i++) points.push(west + (east - west) * i / count, lat);
        addLine(points);
      }
      for (const lon of grid.longitudes) {
        const points: number[] = [];
        const count = Math.max(1, Math.ceil(north - south));
        for (let i = 0; i <= count; i++) points.push(lon, south + (north - south) * i / count);
        addLine(points);
      }
      setMessage(`${grid.kind === 'native' ? 'Native cell grid' : '1° reference grid'} · dataset resolution ${grid.latitude_resolution ?? 'unknown'}° × ${grid.longitude_resolution ?? 'unknown'}°`);
      viewer.scene.requestRender();
    }).catch(err => { if (!controller.signal.aborted) { setError(true); setMessage(String(err)); } });
    return () => {
      controller.abort();
      if (!viewer.isDestroyed()) {
        entities.forEach(entity => viewer.entities.remove(entity));
        viewer.scene.requestRender();
      }
    };
  }, [viewer, datasetId, variable]);
  return <Box sx={{ position: 'absolute', top: 210, right: 12, maxWidth: 350, zIndex: 1000 }}>
    <Alert severity={error ? 'error' : 'info'}>{message}</Alert>
  </Box>;
}
