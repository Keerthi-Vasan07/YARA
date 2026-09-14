import { useRef, useState, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  Box, Typography, Stack, IconButton, Chip, alpha, CircularProgress, Divider,
} from '@mui/material';
import { Close, Place, CalendarMonth, DragIndicator, Layers, Height } from '@mui/icons-material';
import { OnlinePointQuery } from '../api/onlineApi';

interface OnlinePointInfoPanelProps {
  data: OnlinePointQuery | null;
  loading: boolean;
  error?: string | null;
  onClose: () => void;
  screenPosition?: { x: number; y: number } | null;
  clickedPosition?: { lat: number; lon: number } | null;
}

function varAccent(variable: string): string {
  switch (variable.toLowerCase()) {
    case 'sst': return '#ff7043';
    case 'sss': return '#29b6f6';
    case 'chlorophyll': return '#66bb6a';
    case 'thetao': return '#ffb74d';
    case 'so': return '#29b6f6';
    case 'uo': return '#ef5350';
    case 'vo': return '#ab47bc';
    default: return '#6EF2FC';
  }
}

function formatLat(lat: number): string {
  const abs = Math.abs(lat).toFixed(2);
  return lat >= 0 ? `${abs}°N` : `${abs}°S`;
}

function formatLon(lon: number): string {
  const abs = Math.abs(lon).toFixed(2);
  return lon >= 0 ? `${abs}°E` : `${abs}°W`;
}

function formatLocationPair(lat: number, lon: number): string {
  return `${formatLat(lat)}, ${formatLon(lon)}`;
}

function formatValueByVariable(val: number, variableKey: string, units: string): string {
  const vk = (variableKey || '').toLowerCase();
  const u = (units || '').toLowerCase();
  if (vk === 'chlorophyll' || u.includes('mg/m') || (Math.abs(val) < 0.01 && val !== 0)) {
    return val.toFixed(3);
  }
  if (vk === 'uo' || vk === 'vo' || vk === 'usi' || vk === 'vsi') {
    return val.toFixed(3);
  }
  return val.toFixed(2);
}

function formatDateDisplay(rawDate?: string | null): string {
  if (!rawDate) return '—';
  try {
    const d = new Date(rawDate);
    if (!isNaN(d.getTime())) {
      const day = String(d.getUTCDate()).padStart(2, '0');
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const month = months[d.getUTCMonth()];
      const year = d.getUTCFullYear();
      const hours = String(d.getUTCHours()).padStart(2, '0');
      const mins = String(d.getUTCMinutes()).padStart(2, '0');
      return `${day} ${month} ${year} ${hours}:${mins} UTC`;
    }
  } catch {}
  return String(rawDate).slice(0, 19).replace('T', ' ') + ' UTC';
}

export function OnlinePointInfoPanel({
  data,
  loading,
  error,
  onClose,
  screenPosition,
  clickedPosition,
}: OnlinePointInfoPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const initialRight = 80;
  const initialTop = 20;
  const panelWidth = 320;

  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return;

    e.preventDefault();
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      posX: position.x,
      posY: position.y,
    };
  }, [position]);

  useEffect(() => {
    if (!isDragging) return;

    const onMove = (e: MouseEvent) => {
      setPosition({
        x: dragStartRef.current.posX + (e.clientX - dragStartRef.current.x),
        y: dragStartRef.current.posY + (e.clientY - dragStartRef.current.y),
      });
    };

    const onUp = () => setIsDragging(false);

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);

    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [isDragging]);

  if (!data && !loading && !error && !clickedPosition) return null;

  const variableKey = data?.variable || data?.variable_key || '';
  const accent = varAccent(variableKey);
  const panelTop = initialTop + position.y;
  const panelRight = initialRight - position.x;
  const panelLeftEdge =
    typeof window !== 'undefined'
      ? window.innerWidth - panelRight - panelWidth
      : 0;
  const panelConnectionY = panelTop + 40;

  const rawValue =
    data?.value !== undefined && data?.value !== null
      ? data.value
      : Array.isArray(data?.values) && data.values.length > 0
      ? data.values[0]
      : null;

  const hasValidValue = rawValue !== null && rawValue !== undefined && Number.isFinite(Number(rawValue));
  const numericValue = hasValidValue ? Number(rawValue) : null;

  const requestedLat = data?.requested_lat ?? data?.latitude ?? clickedPosition?.lat;
  const requestedLon = data?.requested_lon ?? data?.longitude ?? clickedPosition?.lon;
  const matchedLat = data?.matched_lat ?? data?.latitude;
  const matchedLon = data?.matched_lon ?? data?.longitude;

  const dateMatched = data?.date_matched ?? data?.matched_date;
  const dateRequested = data?.date_requested ?? data?.requested_date;
  const dateDisplay = formatDateDisplay(dateMatched || dateRequested);

  const displayName = data?.variable_name || data?.display_name || (variableKey ? variableKey.toUpperCase() : 'Ocean Scientific Data');
  const unitsDisplay = data?.units || data?.units_display || '';

  const connectionLine =
    screenPosition && (data || loading || error || clickedPosition)
      ? createPortal(
          <svg
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              width: '100vw',
              height: '100vh',
              pointerEvents: 'none',
              zIndex: 9999,
              overflow: 'visible',
            }}
          >
            <line
              x1={screenPosition.x}
              y1={screenPosition.y}
              x2={panelLeftEdge}
              y2={panelConnectionY}
              stroke={alpha(accent, 0.6)}
              strokeWidth="1.5"
              strokeDasharray="5,3"
              strokeLinecap="round"
            />
            <circle
              cx={screenPosition.x}
              cy={screenPosition.y}
              r="5"
              fill={accent}
              stroke="rgba(0,0,0,0.5)"
              strokeWidth="1"
            />
            <circle
              cx={panelLeftEdge}
              cy={panelConnectionY}
              r="3"
              fill={accent}
            />
          </svg>,
          document.body,
        )
      : null;

  const hasReqLoc = Number.isFinite(Number(requestedLat)) && Number.isFinite(Number(requestedLon));
  const hasMatchLoc = Number.isFinite(Number(matchedLat)) && Number.isFinite(Number(matchedLon));

  const depthVal = Array.isArray(data?.depth_values) && data.depth_values.length > 0 ? data.depth_values[0] : null;
  const depthDisplay = depthVal !== null ? (depthVal < 2.0 ? 'Surface' : `${depthVal.toFixed(1)} m`) : 'Surface';

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
          bgcolor: 'rgba(6, 10, 18, 0.94)',
          backdropFilter: 'blur(20px)',
          border: `1px solid ${alpha(accent, 0.35)}`,
          borderRadius: 0,
          overflow: 'hidden',
          zIndex: 1100,
          boxShadow:
            '0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(0,0,0,0.3)',
        }}
      >
        <Box
          sx={{
            height: 2,
            background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
            opacity: 0.8,
          }}
        />

        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 2,
            py: 1.25,
            borderBottom: `1px solid ${alpha(accent, 0.15)}`,
            cursor: isDragging ? 'grabbing' : 'grab',
          }}
          onMouseDown={handleMouseDown}
        >
          <Stack direction="row" spacing={0.75} alignItems="center">
            <DragIndicator
              sx={{ fontSize: 15, color: 'rgba(255,255,255,0.3)' }}
            />
            <Typography
              variant="subtitle2"
              fontWeight={700}
              sx={{ color: accent, fontSize: '0.78rem' }}
            >
              Ocean Data
            </Typography>
          </Stack>

          <IconButton
            size="small"
            onClick={onClose}
            sx={{
              color: 'rgba(255,255,255,0.4)',
              '&:hover': { color: 'white' },
            }}
          >
            <Close fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ p: 2 }}>
          {loading ? (
            <Stack alignItems="center" spacing={2} py={2}>
              <CircularProgress size={32} sx={{ color: accent }} />
              <Typography variant="body2" color="text.secondary" fontWeight={500}>
                Querying ocean data…
              </Typography>
              {hasReqLoc && (
                <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.5)', fontSize: '0.7rem' }}>
                  {formatLocationPair(Number(requestedLat), Number(requestedLon))}
                </Typography>
              )}
            </Stack>
          ) : error ? (
            <Box sx={{ py: 2, textAlign: 'center' }}>
              <Typography variant="body2" sx={{ color: '#ef5350', fontWeight: 600 }}>
                Unable to retrieve ocean data.
              </Typography>
              <Typography
                variant="caption"
                color="text.disabled"
                sx={{ display: 'block', mt: 0.5 }}
              >
                {error}
              </Typography>
            </Box>
          ) : data ? (
            <Stack spacing={1.5}>

              {/* Variable Title */}
              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'rgba(255,255,255,0.4)',
                    fontSize: '0.62rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    display: 'block',
                  }}
                >
                  Variable
                </Typography>
                <Typography variant="body2" fontWeight={700} sx={{ color: '#fff', fontSize: '0.85rem' }}>
                  {displayName}
                </Typography>
              </Box>

              {/* Value display block */}
              {hasValidValue && numericValue !== null ? (
                <Box
                  sx={{
                    p: 1.5,
                    borderRadius: 0,
                    bgcolor: alpha(accent, 0.1),
                    border: `1px solid ${alpha(accent, 0.3)}`,
                  }}
                >
                  <Stack direction="row" alignItems="baseline" spacing={1}>
                    <Typography
                      variant="h3"
                      fontWeight={900}
                      sx={{
                        color: accent,
                        lineHeight: 1,
                        letterSpacing: '-0.02em',
                        textShadow: `0 0 16px ${alpha(accent, 0.6)}`,
                        filter: 'brightness(1.2)',
                      }}
                    >
                      {formatValueByVariable(numericValue, variableKey, unitsDisplay)}
                    </Typography>

                    <Typography
                      variant="body1"
                      sx={{
                        color: alpha(accent, 0.85),
                        fontWeight: 600,
                      }}
                    >
                      {unitsDisplay}
                    </Typography>
                  </Stack>
                </Box>
              ) : (
                <Box sx={{ py: 1.5, px: 1, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.03)', border: '1px dashed rgba(255,255,255,0.1)' }}>
                  <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>
                    No ocean data available at this location.
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.disabled"
                    sx={{ display: 'block', mt: 0.5, fontSize: '0.65rem' }}
                  >
                    Land, cloud mask, or outside coverage
                  </Typography>
                </Box>
              )}

              <Divider sx={{ borderColor: alpha(accent, 0.1) }} />

              {/* Location Coordinates */}
              <Box>
                <Stack
                  direction="row"
                  spacing={0.5}
                  alignItems="center"
                  mb={0.75}
                >
                  <Place sx={{ fontSize: 13, color: accent }} />
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.4)',
                      fontSize: '0.62rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    Location
                  </Typography>
                </Stack>

                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 0.75,
                  }}
                >
                  {hasReqLoc && (
                    <Box
                      sx={{
                        p: 0.75,
                        bgcolor: 'rgba(255,255,255,0.04)',
                        borderRadius: 0.5,
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{
                          color: 'rgba(255,255,255,0.35)',
                          fontSize: '0.58rem',
                          display: 'block',
                        }}
                      >
                        Requested
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.68rem',
                          color: '#fff',
                          fontWeight: 600,
                        }}
                      >
                        {formatLocationPair(Number(requestedLat), Number(requestedLon))}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.58rem',
                          color: 'rgba(255,255,255,0.4)',
                          display: 'block',
                        }}
                      >
                        {Number(requestedLat).toFixed(4)}°, {Number(requestedLon).toFixed(4)}°
                      </Typography>
                    </Box>
                  )}

                  {hasMatchLoc && (
                    <Box
                      sx={{
                        p: 0.75,
                        bgcolor: 'rgba(255,255,255,0.04)',
                        borderRadius: 0.5,
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{
                          color: 'rgba(255,255,255,0.35)',
                          fontSize: '0.58rem',
                          display: 'block',
                        }}
                      >
                        Matched Grid Point
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.68rem',
                          color: alpha(accent, 0.9),
                          fontWeight: 600,
                        }}
                      >
                        {formatLocationPair(Number(matchedLat), Number(matchedLon))}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.58rem',
                          color: 'rgba(255,255,255,0.4)',
                          display: 'block',
                        }}
                      >
                        {Number(matchedLat).toFixed(4)}°, {Number(matchedLon).toFixed(4)}°
                      </Typography>
                    </Box>
                  )}
                </Box>
              </Box>

              {/* Observation Date */}
              <Box>
                <Stack direction="row" spacing={0.5} alignItems="center" mb={0.25}>
                  <CalendarMonth sx={{ fontSize: 13, color: 'text.secondary' }} />
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.4)',
                      fontSize: '0.62rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    Date
                  </Typography>
                </Stack>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'rgba(255,255,255,0.85)',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    pl: 2.25,
                    display: 'block',
                  }}
                >
                  {dateDisplay}
                </Typography>
              </Box>

              {/* Depth */}
              <Box>
                <Stack direction="row" spacing={0.5} alignItems="center" mb={0.25}>
                  <Height sx={{ fontSize: 13, color: 'text.secondary' }} />
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.4)',
                      fontSize: '0.62rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    Depth
                  </Typography>
                </Stack>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'rgba(255,255,255,0.85)',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    pl: 2.25,
                    display: 'block',
                  }}
                >
                  {depthDisplay}
                </Typography>
              </Box>

              {/* Source & Provider Badges */}
              <Box>
                <Stack direction="row" spacing={0.5} alignItems="center" mb={0.5}>
                  <Layers sx={{ fontSize: 13, color: 'text.secondary' }} />
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.4)',
                      fontSize: '0.62rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    Dataset
                  </Typography>
                </Stack>

                <Stack
                  direction="row"
                  spacing={0.5}
                  flexWrap="wrap"
                  useFlexGap
                  pl={2.25}
                >
                  {data.provider && (
                    <Chip
                      label={data.provider}
                      size="small"
                      variant="outlined"
                      sx={{
                        fontSize: '0.6rem',
                        borderColor: alpha(accent, 0.4),
                        color: accent,
                      }}
                    />
                  )}

                  {data.dataset_id && (
                    <Chip
                      label={data.dataset_id}
                      size="small"
                      variant="outlined"
                      sx={{
                        fontSize: '0.6rem',
                        borderColor: alpha(accent, 0.3),
                        color: 'rgba(255,255,255,0.7)',
                      }}
                    />
                  )}
                </Stack>
              </Box>

            </Stack>
          ) : null}
        </Box>
      </Box>
    </>
  );
}

