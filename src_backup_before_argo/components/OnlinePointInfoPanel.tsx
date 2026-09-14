import { useRef, useState, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  Box, Typography, Stack, IconButton, Chip, alpha, CircularProgress, Divider,
} from '@mui/material';
import { Close, Place, CalendarMonth, DragIndicator } from '@mui/icons-material';
import { OnlinePointQuery } from '../api/onlineApi';

interface OnlinePointInfoPanelProps {
  data: OnlinePointQuery | null;
  loading: boolean;
  onClose: () => void;
  screenPosition?: { x: number; y: number } | null;
}

function varAccent(variable: string): string {
  switch (variable) {
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

function safeFixed(value: unknown, digits = 2, fallback = '—'): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : fallback;
}

export function OnlinePointInfoPanel({
  data,
  loading,
  onClose,
  screenPosition,
}: OnlinePointInfoPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const initialRight = 80;
  const initialTop = 20;
  const panelWidth = 300;

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

  if (!data && !loading) return null;

  const variableKey = data?.variable_key ?? '';
  const accent = data ? varAccent(variableKey) : '#6EF2FC';
  const panelTop = initialTop + position.y;
  const panelRight = initialRight - position.x;
  const panelLeftEdge =
    typeof window !== 'undefined'
      ? window.innerWidth - panelRight - panelWidth
      : 0;
  const panelConnectionY = panelTop + 40;

  const requestedLat = data?.requested_lat ?? data?.latitude;
  const requestedLon = data?.requested_lon ?? data?.longitude;
  const matchedLat = data?.matched_lat ?? data?.latitude;
  const matchedLon = data?.matched_lon ?? data?.longitude;
  const dateMatched = data?.matched_date ?? data?.date_matched ?? '—';
  const dateRequested = data?.requested_date ?? data?.date_requested;
  const unitsDisplay = data?.units_display ?? data?.units ?? '';

  const connectionLine =
    screenPosition && (data || loading)
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

  const requestedLocation =
    Number.isFinite(Number(requestedLat)) &&
    Number.isFinite(Number(requestedLon))
      ? `${safeFixed(requestedLat, 4)}°N, ${safeFixed(requestedLon, 4)}°E`
      : '—';

  const matchedLocation =
    Number.isFinite(Number(matchedLat)) &&
    Number.isFinite(Number(matchedLon))
      ? `${safeFixed(matchedLat, 4)}°N, ${safeFixed(matchedLon, 4)}°E`
      : '—';

  const valueDigits = variableKey === 'chlorophyll' ? 4 : 2;

  const gridInfo = data?.grid;

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
          bgcolor: 'rgba(6, 10, 18, 0.92)',
          backdropFilter: 'blur(20px)',
          border: `1px solid ${alpha(accent, 0.35)}`,
          borderRadius: 0,
          overflow: 'hidden',
          zIndex: 1100,
          boxShadow:
            '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,0,0,0.2)',
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
              {data?.display_name ?? 'Ocean Data'}
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
            <Stack alignItems="center" spacing={2} py={3}>
              <CircularProgress size={32} sx={{ color: accent }} />
              <Typography variant="body2" color="text.secondary">
                Querying ocean data…
              </Typography>
            </Stack>
          ) : data ? (
            <Stack spacing={1.5}>
              {data.value !== null && Number.isFinite(Number(data.value)) ? (
                <Box
                  sx={{
                    p: 1.5,
                    borderRadius: 0,
                    bgcolor: alpha(accent, 0.09),
                    border: `1px solid ${alpha(accent, 0.25)}`,
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
                      {safeFixed(data.value, valueDigits)}
                    </Typography>

                    <Typography
                      variant="body1"
                      sx={{
                        color: alpha(accent, 0.75),
                        fontWeight: 500,
                      }}
                    >
                      {unitsDisplay}
                    </Typography>
                  </Stack>

                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.4)',
                      fontSize: '0.65rem',
                    }}
                  >
                    {data.display_name}
                  </Typography>
                </Box>
              ) : (
                <Box sx={{ py: 2, textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    {data.message ?? 'No data at this location'}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.disabled"
                    sx={{ display: 'block', mt: 0.5 }}
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
                  <Place sx={{ fontSize: 13, color: 'text.secondary' }} />
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
                  {[
                    ['Requested', requestedLocation],
                    ['Matched Grid Point', matchedLocation],
                  ].map(([label, val]) => (
                    <Box
                      key={label}
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
                        {label}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.65rem',
                          color: 'rgba(255,255,255,0.75)',
                        }}
                      >
                        {val}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>

              {/* 1° x 1° Grid Box Geometry */}
              {gridInfo ? (
                <Box
                  sx={{
                    p: 0.75,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    border: '1px dashed rgba(255,255,255,0.1)',
                    borderRadius: 0.5,
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'rgba(255,255,255,0.35)',
                      fontSize: '0.58rem',
                      display: 'block',
                      mb: 0.25,
                    }}
                  >
                    1° × 1° Display Grid Box
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.62rem',
                      color: 'rgba(255,255,255,0.7)',
                    }}
                  >
                    Lat: [{gridInfo.lat_min}°, {gridInfo.lat_max}°] | Lon: [{gridInfo.lon_min}°, {gridInfo.lon_max}°]
                  </Typography>
                </Box>
              ) : null}

              {/* Observation Date */}
              <Stack direction="row" spacing={0.75} alignItems="center">
                <CalendarMonth
                  sx={{ fontSize: 13, color: 'text.secondary' }}
                />
                <Typography
                  variant="caption"
                  sx={{
                    color: 'rgba(255,255,255,0.55)',
                    fontSize: '0.7rem',
                  }}
                >
                  {dateMatched}

                  {dateRequested && dateMatched && dateMatched !== dateRequested ? (
                    <Typography
                      component="span"
                      variant="caption"
                      sx={{
                        color: 'rgba(255,255,255,0.35)',
                        ml: 0.5,
                        fontSize: '0.6rem',
                      }}
                    >
                      (requested {dateRequested})
                    </Typography>
                  ) : null}
                </Typography>
              </Stack>

              {/* Source & Provider Badges */}
              <Stack
                direction="row"
                spacing={0.5}
                flexWrap="wrap"
                useFlexGap
              >
                {data.provider ? (
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
                ) : null}

                {data.source && data.source !== data.provider ? (
                  <Chip
                    label={data.source}
                    size="small"
                    variant="outlined"
                    sx={{
                      fontSize: '0.6rem',
                      borderColor: alpha(accent, 0.3),
                      color: 'rgba(255,255,255,0.5)',
                    }}
                  />
                ) : null}

                {data.dataset_id ? (
                  <Chip
                    label={data.dataset_id}
                    size="small"
                    variant="outlined"
                    sx={{
                      fontSize: '0.6rem',
                      borderColor: alpha(accent, 0.3),
                      color: 'rgba(255,255,255,0.5)',
                    }}
                  />
                ) : null}
              </Stack>
            </Stack>
          ) : null}
        </Box>
      </Box>
    </>
  );
}
