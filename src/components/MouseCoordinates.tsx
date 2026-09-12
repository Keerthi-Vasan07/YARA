/**
 * MouseCoordinates - Real-time lat/lon display under cursor
 * Positioned in the bottom-left corner of the map
 */

import { useState, useEffect, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import * as Cesium from 'cesium';

interface MouseCoordinatesProps {
  viewer: Cesium.Viewer | null;
  bottomOffset?: number;
  leftOffset?: number;
}

// Format coordinate with direction indicator
function formatCoord(value: number, isLat: boolean): string {
  const absValue = Math.abs(value);
  const deg = Math.floor(absValue);
  const min = ((absValue - deg) * 60).toFixed(3);
  const dir = isLat 
    ? (value >= 0 ? 'N' : 'S')
    : (value >= 0 ? 'E' : 'W');
  return `${deg}° ${min}' ${dir}`;
}

// Simple decimal format
function formatDecimal(value: number): string {
  return value.toFixed(4);
}

export function MouseCoordinates({ viewer, bottomOffset = 220, leftOffset = 72 }: MouseCoordinatesProps) {
  const [coords, setCoords] = useState<{ lon: number; lat: number; height?: number } | null>(null);
  const [showDMS, setShowDMS] = useState(false);

  const handleMouseMove = useCallback((movement: Cesium.ScreenSpaceEventHandler.MotionEvent) => {
    if (!viewer || viewer.isDestroyed()) return;

    const cartesian = viewer.camera.pickEllipsoid(
      movement.endPosition, 
      viewer.scene.globe.ellipsoid
    );

    if (cartesian) {
      const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
      const lon = Cesium.Math.toDegrees(cartographic.longitude);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);
      setCoords({ lon, lat });
    } else {
      setCoords(null);
    }
  }, [viewer]);

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(handleMouseMove, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    return () => {
      if (!handler.isDestroyed()) {
        handler.destroy();
      }
    };
  }, [viewer, handleMouseMove]);

  if (!coords) return null;

  return (
    <Box
      onClick={() => setShowDMS(!showDMS)}
      sx={{
        position: 'absolute',
        bottom: bottomOffset + 8,
        left: leftOffset,
        bgcolor: 'rgba(8, 12, 18, 0.85)',
        backdropFilter: 'blur(8px)',
        borderRadius: 0,
        border: '1px solid rgba(255,255,255,0.08)',
        px: 1.5,
        py: 0.5,
        display: 'flex',
        gap: 2,
        cursor: 'pointer',
        userSelect: 'none',
        zIndex: 100,
        '&:hover': {
          bgcolor: 'rgba(8, 12, 18, 0.92)',
          borderColor: 'rgba(255,255,255,0.12)',
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <Typography 
          variant="caption" 
          sx={{ 
            color: 'rgba(255,255,255,0.4)', 
            fontSize: '0.65rem',
            fontWeight: 500,
          }}
        >
          LAT
        </Typography>
        <Typography 
          sx={{ 
            fontFamily: '"JetBrains Mono", "SF Mono", Monaco, monospace',
            fontSize: '0.75rem',
            color: 'rgba(255,255,255,0.9)',
            minWidth: showDMS ? 100 : 70,
          }}
        >
          {showDMS ? formatCoord(coords.lat, true) : formatDecimal(coords.lat)}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <Typography 
          variant="caption" 
          sx={{ 
            color: 'rgba(255,255,255,0.4)', 
            fontSize: '0.65rem',
            fontWeight: 500,
          }}
        >
          LON
        </Typography>
        <Typography 
          sx={{ 
            fontFamily: '"JetBrains Mono", "SF Mono", Monaco, monospace',
            fontSize: '0.75rem',
            color: 'rgba(255,255,255,0.9)',
            minWidth: showDMS ? 110 : 80,
          }}
        >
          {showDMS ? formatCoord(coords.lon, false) : formatDecimal(coords.lon)}
        </Typography>
      </Box>
    </Box>
  );
}

export default MouseCoordinates;
