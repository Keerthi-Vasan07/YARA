import { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Typography, IconButton, Tooltip, Paper } from '@mui/material';
import { Check, Close, Refresh } from '@mui/icons-material';
import * as Cesium from 'cesium';

export interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

interface BboxDrawingOverlayProps {
  active: boolean;
  onComplete: (bbox: BoundingBox) => void;
  onCancel: () => void;
  initialBbox?: BoundingBox | null;
  viewer: Cesium.Viewer | null;
}

type HandlePosition = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'move';

interface Point {
  x: number;
  y: number;
}

export function BboxDrawingOverlay({
  active,
  onComplete,
  onCancel,
  initialBbox,
  viewer,
}: BboxDrawingOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPoint, setStartPoint] = useState<Point | null>(null);
  const [currentPoint, setCurrentPoint] = useState<Point | null>(null);
  const [bbox, setBbox] = useState<BoundingBox | null>(null);
  const [activeHandle, setActiveHandle] = useState<HandlePosition | null>(null);
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [originalBbox, setOriginalBbox] = useState<BoundingBox | null>(null);
  
  // Cesium entity ref for the rectangle on the globe
  const bboxEntityRef = useRef<Cesium.Entity | null>(null);

  // Convert screen coords to geo coords using Cesium's globe picking
  const screenToGeo = useCallback((x: number, y: number): { lon: number; lat: number } | null => {
    if (!viewer || viewer.isDestroyed()) return null;
    
    const cartesian = viewer.camera.pickEllipsoid(
      new Cesium.Cartesian2(x, y),
      viewer.scene.globe.ellipsoid
    );
    
    if (!cartesian) return null;
    
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
    };
  }, [viewer]);

  // Convert geo coords to screen coords
  const geoToScreen = useCallback((lon: number, lat: number): Point | null => {
    if (!viewer || viewer.isDestroyed()) return null;
    
    const cartesian = Cesium.Cartesian3.fromDegrees(lon, lat);
    const screenPos = Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, cartesian);
    
    if (!screenPos) return null;
    return { x: screenPos.x, y: screenPos.y };
  }, [viewer]);

  // Update Cesium entity when bbox changes
  const updateCesiumEntity = useCallback((b: BoundingBox | null) => {
    if (!viewer || viewer.isDestroyed()) return;
    
    // Remove existing entity
    if (bboxEntityRef.current) {
      viewer.entities.remove(bboxEntityRef.current);
      bboxEntityRef.current = null;
    }
    
    if (!b) return;
    
    // Create new entity
    bboxEntityRef.current = viewer.entities.add({
      rectangle: {
        coordinates: Cesium.Rectangle.fromDegrees(b.west, b.south, b.east, b.north),
        material: Cesium.Color.fromCssColorString('#6EF2FC').withAlpha(0.2),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#6EF2FC'),
        outlineWidth: 2,
        height: 0,
        stRotation: 0,
      },
    });
    
    viewer.scene.requestRender();
  }, [viewer]);

  // Reset when deactivated
  useEffect(() => {
    if (!active) {
      setIsDrawing(false);
      setStartPoint(null);
      setCurrentPoint(null);
      setBbox(null);
      setActiveHandle(null);
      
      // Remove Cesium entity
      if (viewer && !viewer.isDestroyed() && bboxEntityRef.current) {
        viewer.entities.remove(bboxEntityRef.current);
        bboxEntityRef.current = null;
      }
    }
  }, [active, viewer]);

  // Initialize from existing bbox
  useEffect(() => {
    if (active && initialBbox) {
      setBbox(initialBbox);
      updateCesiumEntity(initialBbox);
    }
  }, [active, initialBbox, updateCesiumEntity]);

  // Get screen rect from current bbox for handle positioning
  const getScreenRect = useCallback((): { x: number; y: number; width: number; height: number } | null => {
    if (!bbox) return null;
    
    const nw = geoToScreen(bbox.west, bbox.north);
    const se = geoToScreen(bbox.east, bbox.south);
    
    if (!nw || !se) return null;
    
    return {
      x: Math.min(nw.x, se.x),
      y: Math.min(nw.y, se.y),
      width: Math.abs(se.x - nw.x),
      height: Math.abs(se.y - nw.y),
    };
  }, [bbox, geoToScreen]);

  // Get preview bbox during drawing
  const getPreviewBbox = useCallback((): BoundingBox | null => {
    if (!isDrawing || !startPoint || !currentPoint) return null;
    
    const startGeo = screenToGeo(startPoint.x, startPoint.y);
    const endGeo = screenToGeo(currentPoint.x, currentPoint.y);
    
    if (!startGeo || !endGeo) return null;
    
    return {
      north: Math.max(startGeo.lat, endGeo.lat),
      south: Math.min(startGeo.lat, endGeo.lat),
      east: Math.max(startGeo.lon, endGeo.lon),
      west: Math.min(startGeo.lon, endGeo.lon),
    };
  }, [isDrawing, startPoint, currentPoint, screenToGeo]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!active || !viewer) return;
    
    const x = e.clientX;
    const y = e.clientY;
    
    // If we have a bbox, check if clicking on a handle
    if (bbox) {
      const screenRect = getScreenRect();
      if (screenRect) {
        const handle = getHandleAtPosition(x, y, screenRect);
        if (handle) {
          setActiveHandle(handle);
          setDragStart({ x, y });
          setOriginalBbox({ ...bbox });
          e.preventDefault();
          e.stopPropagation();
          return;
        }
      }
    }
    
    // Check if click is on the globe
    const geo = screenToGeo(x, y);
    if (!geo) return; // Click not on globe
    
    // Start new drawing
    setIsDrawing(true);
    setStartPoint({ x, y });
    setCurrentPoint({ x, y });
    setBbox(null);
    updateCesiumEntity(null);
    e.preventDefault();
    e.stopPropagation();
  }, [active, viewer, bbox, getScreenRect, screenToGeo, updateCesiumEntity]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!active || !viewer) return;
    
    const x = e.clientX;
    const y = e.clientY;
    
    if (isDrawing && startPoint) {
      setCurrentPoint({ x, y });
      
      // Update Cesium entity preview
      const startGeo = screenToGeo(startPoint.x, startPoint.y);
      const endGeo = screenToGeo(x, y);
      
      if (startGeo && endGeo) {
        const previewBbox = {
          north: Math.max(startGeo.lat, endGeo.lat),
          south: Math.min(startGeo.lat, endGeo.lat),
          east: Math.max(startGeo.lon, endGeo.lon),
          west: Math.min(startGeo.lon, endGeo.lon),
        };
        updateCesiumEntity(previewBbox);
      }
    } else if (activeHandle && dragStart && originalBbox) {
      // Handle resize/move
      const dx = x - dragStart.x;
      const dy = y - dragStart.y;
      
      // Convert drag delta to geo delta (approximate)
      const origNW = geoToScreen(originalBbox.west, originalBbox.north);
      const origSE = geoToScreen(originalBbox.east, originalBbox.south);
      
      if (!origNW || !origSE) return;
      
      const newNW = { ...origNW };
      const newSE = { ...origSE };
      
      switch (activeHandle) {
        case 'nw':
          newNW.x += dx;
          newNW.y += dy;
          break;
        case 'n':
          newNW.y += dy;
          break;
        case 'ne':
          newSE.x += dx;
          newNW.y += dy;
          break;
        case 'e':
          newSE.x += dx;
          break;
        case 'se':
          newSE.x += dx;
          newSE.y += dy;
          break;
        case 's':
          newSE.y += dy;
          break;
        case 'sw':
          newNW.x += dx;
          newSE.y += dy;
          break;
        case 'w':
          newNW.x += dx;
          break;
        case 'move':
          newNW.x += dx;
          newNW.y += dy;
          newSE.x += dx;
          newSE.y += dy;
          break;
      }
      
      // Convert back to geo
      const nwGeo = screenToGeo(newNW.x, newNW.y);
      const seGeo = screenToGeo(newSE.x, newSE.y);
      
      if (nwGeo && seGeo) {
        const newBbox = {
          north: Math.max(nwGeo.lat, seGeo.lat),
          south: Math.min(nwGeo.lat, seGeo.lat),
          east: Math.max(nwGeo.lon, seGeo.lon),
          west: Math.min(nwGeo.lon, seGeo.lon),
        };
        
        // Ensure minimum size (about 1 degree)
        if (newBbox.north - newBbox.south > 0.5 && newBbox.east - newBbox.west > 0.5) {
          setBbox(newBbox);
          updateCesiumEntity(newBbox);
        }
      }
    }
  }, [active, viewer, isDrawing, startPoint, activeHandle, dragStart, originalBbox, screenToGeo, geoToScreen, updateCesiumEntity]);

  const handleMouseUp = useCallback(() => {
    if (isDrawing && startPoint && currentPoint) {
      const startGeo = screenToGeo(startPoint.x, startPoint.y);
      const endGeo = screenToGeo(currentPoint.x, currentPoint.y);
      
      if (startGeo && endGeo) {
        const latDiff = Math.abs(startGeo.lat - endGeo.lat);
        const lonDiff = Math.abs(startGeo.lon - endGeo.lon);
        
        // Only create bbox if it has meaningful size
        if (latDiff > 0.5 && lonDiff > 0.5) {
          const newBbox = {
            north: Math.max(startGeo.lat, endGeo.lat),
            south: Math.min(startGeo.lat, endGeo.lat),
            east: Math.max(startGeo.lon, endGeo.lon),
            west: Math.min(startGeo.lon, endGeo.lon),
          };
          setBbox(newBbox);
          updateCesiumEntity(newBbox);
        }
      }
    }
    
    setIsDrawing(false);
    setStartPoint(null);
    setCurrentPoint(null);
    setActiveHandle(null);
    setDragStart(null);
    setOriginalBbox(null);
  }, [isDrawing, startPoint, currentPoint, screenToGeo, updateCesiumEntity]);

  const handleConfirm = useCallback(() => {
    const finalBbox = bbox || getPreviewBbox();
    if (!finalBbox) return;
    
    onComplete(finalBbox);
  }, [bbox, getPreviewBbox, onComplete]);

  const handleReset = useCallback(() => {
    setBbox(null);
    setIsDrawing(false);
    setStartPoint(null);
    setCurrentPoint(null);
    updateCesiumEntity(null);
  }, [updateCesiumEntity]);

  const handleCancelClick = useCallback(() => {
    // Remove the entity before canceling
    if (viewer && !viewer.isDestroyed() && bboxEntityRef.current) {
      viewer.entities.remove(bboxEntityRef.current);
      bboxEntityRef.current = null;
    }
    onCancel();
  }, [viewer, onCancel]);

  // Handle wheel events to pass through to Cesium for zooming
  const handleWheel = useCallback((e: React.WheelEvent) => {
    // Don't prevent default - let the wheel event bubble to Cesium
    e.stopPropagation();
    
    // Forward the wheel event to Cesium's canvas
    if (viewer && !viewer.isDestroyed()) {
      const canvas = viewer.scene.canvas;
      const wheelEvent = new WheelEvent('wheel', {
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        deltaZ: e.deltaZ,
        deltaMode: e.deltaMode,
        clientX: e.clientX,
        clientY: e.clientY,
        screenX: e.screenX,
        screenY: e.screenY,
        bubbles: true,
        cancelable: true,
      });
      canvas.dispatchEvent(wheelEvent);
    }
  }, [viewer]);

  const getHandleAtPosition = (x: number, y: number, r: { x: number; y: number; width: number; height: number }): HandlePosition | null => {
    const handleSize = 12;
    const handles: { pos: HandlePosition; x: number; y: number }[] = [
      { pos: 'nw', x: r.x, y: r.y },
      { pos: 'n', x: r.x + r.width / 2, y: r.y },
      { pos: 'ne', x: r.x + r.width, y: r.y },
      { pos: 'e', x: r.x + r.width, y: r.y + r.height / 2 },
      { pos: 'se', x: r.x + r.width, y: r.y + r.height },
      { pos: 's', x: r.x + r.width / 2, y: r.y + r.height },
      { pos: 'sw', x: r.x, y: r.y + r.height },
      { pos: 'w', x: r.x, y: r.y + r.height / 2 },
    ];
    
    for (const h of handles) {
      if (Math.abs(x - h.x) < handleSize && Math.abs(y - h.y) < handleSize) {
        return h.pos;
      }
    }
    
    // Check if inside rect for move
    if (x > r.x && x < r.x + r.width && y > r.y && y < r.y + r.height) {
      return 'move';
    }
    
    return null;
  };

  const getCursor = (): string => {
    if (activeHandle) {
      switch (activeHandle) {
        case 'nw':
        case 'se':
          return 'nwse-resize';
        case 'ne':
        case 'sw':
          return 'nesw-resize';
        case 'n':
        case 's':
          return 'ns-resize';
        case 'e':
        case 'w':
          return 'ew-resize';
        case 'move':
          return 'move';
      }
    }
    if (isDrawing) return 'crosshair';
    if (bbox) return 'default';
    return 'crosshair';
  };

  if (!active) return null;

  // Get current display bbox
  const displayBbox = bbox || getPreviewBbox();
  
  // Get screen rect for handle rendering
  const screenRect = displayBbox ? (() => {
    const nw = geoToScreen(displayBbox.west, displayBbox.north);
    const se = geoToScreen(displayBbox.east, displayBbox.south);
    if (!nw || !se) return null;
    return {
      x: Math.min(nw.x, se.x),
      y: Math.min(nw.y, se.y),
      width: Math.abs(se.x - nw.x),
      height: Math.abs(se.y - nw.y),
    };
  })() : null;

  return (
    <Box
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1300,
        cursor: getCursor(),
        userSelect: 'none',
      }}
    >
      {/* Instructions */}
      <Paper
        onMouseDown={(e) => e.stopPropagation()}
        onMouseUp={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        sx={{
          position: 'absolute',
          top: 80,
          left: '50%',
          transform: 'translateX(-50%)',
          bgcolor: 'rgba(8, 12, 18, 0.95)',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 0,
          px: 2,
          py: 1,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          pointerEvents: 'auto',
        }}
      >
        <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
          {!displayBbox 
            ? 'Click and drag on the globe to draw bounding box'
            : 'Drag corners to resize, or click inside to move'}
        </Typography>
        
        {displayBbox && (
          <>
            <Tooltip title="Confirm selection">
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); handleConfirm(); }}
                sx={{
                  bgcolor: '#6EF2FC',
                  color: '#0A0E14',
                  '&:hover': { bgcolor: '#5DD8E8' },
                }}
              >
                <Check fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Reset">
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); handleReset(); }}
                sx={{
                  bgcolor: 'rgba(255,255,255,0.1)',
                  '&:hover': { bgcolor: 'rgba(255,255,255,0.2)' },
                }}
              >
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
          </>
        )}
        
        <Tooltip title="Cancel">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); handleCancelClick(); }}
            sx={{
              bgcolor: 'rgba(255,255,255,0.1)',
              '&:hover': { bgcolor: 'rgba(255,255,255,0.2)' },
            }}
          >
            <Close fontSize="small" />
          </IconButton>
        </Tooltip>
      </Paper>

      {/* Coordinate labels (rendered as HTML overlay) */}
      {displayBbox && screenRect && screenRect.width > 50 && screenRect.height > 50 && (
        <>
          {/* North label */}
          <Box
            sx={{
              position: 'absolute',
              left: screenRect.x + screenRect.width / 2,
              top: screenRect.y - 24,
              transform: 'translateX(-50%)',
              bgcolor: 'rgba(8, 12, 18, 0.9)',
              px: 1,
              py: 0.25,
              borderRadius: 0.5,
              pointerEvents: 'none',
            }}
          >
            <Typography variant="caption" sx={{ fontSize: '0.7rem', color: '#6EF2FC', fontFamily: 'monospace' }}>
              {displayBbox.north.toFixed(2)}°N
            </Typography>
          </Box>
          
          {/* South label */}
          <Box
            sx={{
              position: 'absolute',
              left: screenRect.x + screenRect.width / 2,
              top: screenRect.y + screenRect.height + 6,
              transform: 'translateX(-50%)',
              bgcolor: 'rgba(8, 12, 18, 0.9)',
              px: 1,
              py: 0.25,
              borderRadius: 0.5,
              pointerEvents: 'none',
            }}
          >
            <Typography variant="caption" sx={{ fontSize: '0.7rem', color: '#6EF2FC', fontFamily: 'monospace' }}>
              {displayBbox.south.toFixed(2)}°S
            </Typography>
          </Box>
          
          {/* West label */}
          <Box
            sx={{
              position: 'absolute',
              left: screenRect.x - 6,
              top: screenRect.y + screenRect.height / 2,
              transform: 'translate(-100%, -50%)',
              bgcolor: 'rgba(8, 12, 18, 0.9)',
              px: 1,
              py: 0.25,
              borderRadius: 0.5,
              pointerEvents: 'none',
            }}
          >
            <Typography variant="caption" sx={{ fontSize: '0.7rem', color: '#6EF2FC', fontFamily: 'monospace' }}>
              {displayBbox.west.toFixed(2)}°
            </Typography>
          </Box>
          
          {/* East label */}
          <Box
            sx={{
              position: 'absolute',
              left: screenRect.x + screenRect.width + 6,
              top: screenRect.y + screenRect.height / 2,
              transform: 'translateY(-50%)',
              bgcolor: 'rgba(8, 12, 18, 0.9)',
              px: 1,
              py: 0.25,
              borderRadius: 0.5,
              pointerEvents: 'none',
            }}
          >
            <Typography variant="caption" sx={{ fontSize: '0.7rem', color: '#6EF2FC', fontFamily: 'monospace' }}>
              {displayBbox.east.toFixed(2)}°
            </Typography>
          </Box>

          {/* Resize handles (only when finalized bbox, not during drawing) */}
          {!isDrawing && bbox && (
            <>
              {/* Corner handles */}
              {[
                { pos: 'nw', x: 0, y: 0 },
                { pos: 'ne', x: screenRect.width, y: 0 },
                { pos: 'se', x: screenRect.width, y: screenRect.height },
                { pos: 'sw', x: 0, y: screenRect.height },
              ].map(({ pos, x, y }) => (
                <Box
                  key={pos}
                  sx={{
                    position: 'absolute',
                    left: screenRect.x + x - 5,
                    top: screenRect.y + y - 5,
                    width: 10,
                    height: 10,
                    bgcolor: '#6EF2FC',
                    border: '2px solid #0A0E14',
                    borderRadius: 0,
                    cursor: pos === 'nw' || pos === 'se' ? 'nwse-resize' : 'nesw-resize',
                    pointerEvents: 'auto',
                    '&:hover': {
                      transform: 'scale(1.2)',
                    },
                  }}
                />
              ))}
              
              {/* Edge handles */}
              {[
                { pos: 'n', x: screenRect.width / 2, y: 0 },
                { pos: 'e', x: screenRect.width, y: screenRect.height / 2 },
                { pos: 's', x: screenRect.width / 2, y: screenRect.height },
                { pos: 'w', x: 0, y: screenRect.height / 2 },
              ].map(({ pos, x, y }) => (
                <Box
                  key={pos}
                  sx={{
                    position: 'absolute',
                    left: screenRect.x + x - 4,
                    top: screenRect.y + y - 4,
                    width: 8,
                    height: 8,
                    bgcolor: '#fff',
                    border: '2px solid #6EF2FC',
                    borderRadius: 0,
                    cursor: pos === 'n' || pos === 's' ? 'ns-resize' : 'ew-resize',
                    pointerEvents: 'auto',
                    '&:hover': {
                      transform: 'scale(1.2)',
                    },
                  }}
                />
              ))}
            </>
          )}
        </>
      )}

      {/* Crosshair guides when drawing */}
      {isDrawing && currentPoint && (
        <>
          <Box
            sx={{
              position: 'absolute',
              left: currentPoint.x,
              top: 0,
              width: 1,
              height: '100%',
              bgcolor: 'rgba(110, 242, 252, 0.3)',
              pointerEvents: 'none',
            }}
          />
          <Box
            sx={{
              position: 'absolute',
              left: 0,
              top: currentPoint.y,
              width: '100%',
              height: 1,
              bgcolor: 'rgba(110, 242, 252, 0.3)',
              pointerEvents: 'none',
            }}
          />
        </>
      )}
    </Box>
  );
}
