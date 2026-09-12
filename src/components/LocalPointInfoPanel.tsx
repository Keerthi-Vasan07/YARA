/**
 * Generic click-to-identify panel for LOCAL dataset point queries.
 * Modeled on VariableInfoPanel's draggable/connector-line structure, but generic
 * (variable name, units, value, requested vs matched lat/lon, 1-degree grid cell
 * bounds, timestamp) instead of a hardcoded VARIABLE_CONFIG — local datasets can be
 * any variable (SST, chlorophyll, salinity, ...), not just SST.
 */
import { useRef, useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Box, Typography, IconButton, Stack, Divider, Tooltip } from '@mui/material';
import { Close, Place, GridOn, DragIndicator, CalendarMonth } from '@mui/icons-material';
import type { LocalPointQueryResponse } from '../types/dataset';

interface LocalPointInfoPanelProps {
  data: LocalPointQueryResponse | null;
  loading: boolean;
  onClose: () => void;
  screenPosition?: { x: number; y: number } | null;
}

export function LocalPointInfoPanel({ data, loading, onClose, screenPosition }: LocalPointInfoPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const initialTop = 20;
  const initialRight = 80;
  const panelWidth = 300;

  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX, y: e.clientY, posX: position.x, posY: position.y };
  }, [position]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      setPosition({ x: dragStartRef.current.posX + dx, y: dragStartRef.current.posY + dy });
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  const panelTop = initialTop + position.y;
  const panelRight = initialRight - position.x;

  if (!data && !loading) return null;

  const panelLeftEdge = typeof window !== 'undefined' ? window.innerWidth - panelRight - panelWidth : 0;
  const panelConnectionY = panelTop + 40;

  const connectionLine = screenPosition && (data || loading) ? createPortal(
    <svg style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', pointerEvents: 'none', zIndex: 9999, overflow: 'visible' }}>
      <line
        x1={screenPosition.x} y1={screenPosition.y}
        x2={panelLeftEdge} y2={panelConnectionY}
        stroke="rgba(110, 242, 252, 0.6)" strokeWidth="1.5" strokeDasharray="5,3" strokeLinecap="round"
      />
      <circle cx={screenPosition.x} cy={screenPosition.y} r="5" fill="rgba(110, 242, 252, 0.9)" stroke="rgba(0,0,0,0.5)" strokeWidth="1" />
      <circle cx={panelLeftEdge} cy={panelConnectionY} r="3" fill="rgba(110, 242, 252, 0.9)" />
    </svg>,
    document.body
  ) : null;

  return (
    <>
      {connectionLine}
      <Box
        ref={panelRef}
        sx={{
          position: 'absolute',
          top: panelTop,
          right: panelRight,
          width: panelWidth,
          bgcolor: 'rgba(8, 12, 18, 0.90)',
          backdropFilter: 'blur(16px)',
          borderRadius: 0,
          border: '1px solid rgba(110, 242, 252, 0.25)',
          overflow: 'hidden',
          zIndex: 1100,
          boxShadow: '0 0 0 1px rgba(0,0,0,0.3)',
        }}
      >
        <Box
          sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', cursor: isDragging ? 'grabbing' : 'grab' }}
          onMouseDown={handleMouseDown}
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <DragIndicator sx={{ fontSize: 16, color: 'rgba(255,255,255,0.4)' }} />
            <Typography variant="subtitle2" fontWeight={600} sx={{ color: 'rgba(255,255,255,0.9)' }}>
              {(data?.variable || 'Value').toUpperCase()}
            </Typography>
          </Stack>
          <IconButton size="small" onClick={onClose}>
            <Close fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ p: 2 }}>
          {loading ? (
            <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
              Querying dataset...
            </Typography>
          ) : data ? (
            <Stack spacing={2}>
              {data.is_valid && data.value != null ? (
                <Box sx={{ p: 2, borderRadius: 0, bgcolor: 'rgba(110, 242, 252, 0.1)', border: '1px solid rgba(110, 242, 252, 0.2)' }}>
                  <Typography variant="h4" fontWeight={700} sx={{ color: '#6EF2FC', lineHeight: 1 }}>
                    {data.value.toFixed(2)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{data.units || ''}</Typography>
                </Box>
              ) : (
                <Box sx={{ py: 2, px: 2, bgcolor: 'action.disabledBackground', textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">No data / Land cell</Typography>
                </Box>
              )}

              <Divider />

              <Box>
                <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                  <Place sx={{ fontSize: 18, color: 'text.secondary' }} />
                  <Typography variant="body2" fontWeight={600}>Clicked Location</Typography>
                </Stack>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                  <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">Latitude</Typography>
                    <Typography variant="body2" fontFamily="monospace">
                      {Math.abs(data.requested_lat).toFixed(4)}° {data.requested_lat >= 0 ? 'N' : 'S'}
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">Longitude</Typography>
                    <Typography variant="body2" fontFamily="monospace">
                      {Math.abs(data.requested_lon).toFixed(4)}° {data.requested_lon >= 0 ? 'E' : 'W'}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {data.cell_bounds && (
                <Box>
                  <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                    <GridOn sx={{ fontSize: 18, color: 'text.secondary' }} />
                    <Typography variant="body2" fontWeight={600}>Grid Cell</Typography>
                  </Stack>
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                    <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary">Lat range</Typography>
                      <Typography variant="body2" fontFamily="monospace">
                        {data.cell_bounds.south.toFixed(3)}° – {data.cell_bounds.north.toFixed(3)}°
                      </Typography>
                    </Box>
                    <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary">Lon range</Typography>
                      <Typography variant="body2" fontFamily="monospace">
                        {data.cell_bounds.west.toFixed(3)}° – {data.cell_bounds.east.toFixed(3)}°
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              )}

              {data.timestamp && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CalendarMonth sx={{ fontSize: 18, color: 'text.secondary' }} />
                  <Tooltip title={data.timestamp} arrow>
                    <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                      {data.timestamp}
                    </Typography>
                  </Tooltip>
                </Stack>
              )}
            </Stack>
          ) : null}
        </Box>
      </Box>
    </>
  );
}

export default LocalPointInfoPanel;
