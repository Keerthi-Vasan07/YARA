import { useRef, useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { 
  Box, Typography, IconButton, Stack, Chip, alpha, CircularProgress,
  Divider, Tooltip
} from '@mui/material';
import { 
  Close, Place, CalendarMonth, TrendingUp, TrendingDown,
  Speed, Info, Timeline, Download, DragIndicator
} from '@mui/icons-material';
import { SSTPointQuery, fetchClimatology, fetchPercentiles, ClimatologyResponse, PercentilesResponse } from '../api/sstApi';

interface SSTInfoPanelProps {
  data: SSTPointQuery | null;
  loading: boolean;
  onClose: () => void;
  screenPosition?: { x: number; y: number } | null;
}

// SST color scale (thermal colormap)
const SST_COLORS = [
  { temp: -2, color: '#0a1929', label: 'Polar' },
  { temp: 2, color: '#1565c0', label: 'Arctic' },
  { temp: 8, color: '#0288d1', label: 'Cold' },
  { temp: 14, color: '#00acc1', label: 'Cool' },
  { temp: 18, color: '#26a69a', label: 'Temperate' },
  { temp: 22, color: '#66bb6a', label: 'Mild' },
  { temp: 26, color: '#cddc39', label: 'Warm' },
  { temp: 29, color: '#ffb300', label: 'Tropical' },
  { temp: 32, color: '#ff5722', label: 'Hot' },
  { temp: 35, color: '#d32f2f', label: 'Extreme' },
];

// Interpolate color for SST value
function getSSTColor(sst: number): string {
  if (sst <= SST_COLORS[0].temp) return SST_COLORS[0].color;
  if (sst >= SST_COLORS[SST_COLORS.length - 1].temp) return SST_COLORS[SST_COLORS.length - 1].color;
  
  for (let i = 0; i < SST_COLORS.length - 1; i++) {
    if (sst >= SST_COLORS[i].temp && sst < SST_COLORS[i + 1].temp) {
      return SST_COLORS[i].color;
    }
  }
  return SST_COLORS[5].color;
}

// Get temperature classification
function getSSTClassification(sst: number): { label: string; color: string; description: string } {
  const descriptions: Record<string, string> = {
    'Polar': 'Near freezing, sea ice formation zone',
    'Arctic': 'Cold polar waters',
    'Cold': 'Subpolar, upwelling zones',
    'Cool': 'Temperate cold currents',
    'Temperate': 'Mid-latitude ocean',
    'Mild': 'Subtropical transition',
    'Warm': 'Tropical warm pool margin',
    'Tropical': 'Core tropical waters',
    'Hot': 'Extreme tropical, heat stress',
    'Extreme': 'Coral bleaching threshold exceeded',
  };
  
  for (let i = SST_COLORS.length - 1; i >= 0; i--) {
    if (sst >= SST_COLORS[i].temp) {
      return {
        label: SST_COLORS[i].label,
        color: SST_COLORS[i].color,
        description: descriptions[SST_COLORS[i].label] || '',
      };
    }
  }
  return { label: 'Unknown', color: '#888', description: '' };
}

// Convert Celsius to Fahrenheit
function toFahrenheit(celsius: number): number {
  return celsius * 9/5 + 32;
}

// Convert Celsius to Kelvin
function toKelvin(celsius: number): number {
  return celsius + 273.15;
}

// Get approximate climatological mean for latitude band
function getClimatologyMean(lat: number, month: number): number {
  const absLat = Math.abs(lat);
  const seasonalOffset = Math.cos((month - 1) * Math.PI / 6) * (lat > 0 ? 2 : -2);
  
  if (absLat > 60) return 2 + seasonalOffset;
  if (absLat > 45) return 10 + seasonalOffset * 1.5;
  if (absLat > 30) return 18 + seasonalOffset;
  if (absLat > 15) return 24 + seasonalOffset * 0.5;
  return 27 + seasonalOffset * 0.3;
}

// Temperature gauge component
function TemperatureGauge({ value, min = -2, max = 35 }: { value: number; min?: number; max?: number }) {
  const percentage = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  
  return (
    <Box sx={{ position: 'relative', height: 12, borderRadius: 1, overflow: 'hidden', bgcolor: 'rgba(0,0,0,0.2)' }}>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(90deg, #0a1929 0%, #1565c0 15%, #00acc1 35%, #66bb6a 50%, #cddc39 65%, #ff5722 85%, #d32f2f 100%)',
          opacity: 0.5,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          left: `${percentage}%`,
          top: 0,
          bottom: 0,
          width: 3,
          bgcolor: 'white',
          transform: 'translateX(-50%)',
          boxShadow: '0 0 4px rgba(0,0,0,0.5)',
          borderRadius: 1,
        }}
      />
      <Typography
        variant="caption"
        sx={{
          position: 'absolute',
          left: 4,
          top: '50%',
          transform: 'translateY(-50%)',
          fontSize: '0.6rem',
          color: 'white',
          textShadow: '0 0 2px black',
        }}
      >
        {min}°
      </Typography>
      <Typography
        variant="caption"
        sx={{
          position: 'absolute',
          right: 4,
          top: '50%',
          transform: 'translateY(-50%)',
          fontSize: '0.6rem',
          color: 'white',
          textShadow: '0 0 2px black',
        }}
      >
        {max}°
      </Typography>
    </Box>
  );
}

// Mini color scale legend
function ColorScaleLegend() {
  return (
    <Box sx={{ mt: 1 }}>
      <Box
        sx={{
          height: 8,
          borderRadius: 0.5,
          background: 'linear-gradient(90deg, #0a1929 0%, #1565c0 15%, #00acc1 35%, #66bb6a 50%, #cddc39 65%, #ff5722 85%, #d32f2f 100%)',
        }}
      />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>-2°C</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>15°C</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>35°C</Typography>
      </Box>
    </Box>
  );
}

export function SSTInfoPanel({ data, loading, onClose, screenPosition }: SSTInfoPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const initialRight = 80;
  const initialTop = 20;
  const panelWidth = 320;

  // Draggable position state
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
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

    const handleMouseMove = (e: MouseEvent) => {
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      setPosition({
        x: dragStartRef.current.posX + dx,
        y: dragStartRef.current.posY + dy,
      });
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  // Computed panel position
  const panelTop = initialTop + position.y;
  const panelRight = initialRight - position.x;

  // Climatology and percentiles state
  const [climatology, setClimatology] = useState<ClimatologyResponse | null>(null);
  const [percentiles, setPercentiles] = useState<PercentilesResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Fetch climatology and percentiles when location changes
  useEffect(() => {
    if (!data || data.sst === null) {
      setClimatology(null);
      setPercentiles(null);
      return;
    }

    const fetchStats = async () => {
      setStatsLoading(true);
      const month = new Date(data.date).getMonth() + 1;
      
      try {
        // Fetch climatology for the current month and percentiles in parallel
        const [climData, percData] = await Promise.all([
          fetchClimatology('sst', data.lon, data.lat, month),
          fetchPercentiles('sst', data.lon, data.lat, data.date),
        ]);
        setClimatology(climData);
        setPercentiles(percData);
      } catch (err) {
        console.error('Failed to fetch stats:', err);
        setClimatology(null);
        setPercentiles(null);
      } finally {
        setStatsLoading(false);
      }
    };

    fetchStats();
  }, [data?.lon, data?.lat, data?.date]);
  
  if (!data && !loading) return null;

  const classification = data?.sst != null ? getSSTClassification(data.sst) : null;
  
  // Use real climatology if available, otherwise fall back to estimate
  const month = data ? new Date(data.date).getMonth() + 1 : 1;
  // When fetching with month param, monthly is a single MonthlyClimatology object
  const monthlyClim = climatology?.monthly && !Array.isArray(climatology.monthly) ? climatology.monthly : null;
  const hasRealClimatology = monthlyClim?.mean !== null && monthlyClim?.mean !== undefined;
  const climatologyMean = hasRealClimatology 
    ? monthlyClim!.mean! 
    : (data ? getClimatologyMean(data.lat, month) : 0);
  const anomaly = data?.sst != null ? data.sst - climatologyMean : 0;
  
  // Extract percentile values from response
  const pValues = percentiles?.percentiles;
  const percentileRank = percentiles?.current?.percentile_rank ?? null;
  const getPercentileDescription = (rank: number | null | undefined): string => {
    if (rank === null || rank === undefined) return '';
    if (rank >= 90) return `Exceptionally warm (top ${(100 - rank).toFixed(0)}%)`;
    if (rank >= 75) return `Above normal (warmer than ${rank.toFixed(0)}% of history)`;
    if (rank >= 25) return `Near normal`;
    if (rank >= 10) return `Below normal (cooler than ${(100 - rank).toFixed(0)}% of history)`;
    return `Exceptionally cold (bottom ${rank.toFixed(0)}%)`;
  };

  // Export data as CSV
  const handleExport = () => {
    if (!data) return;
    
    // Build CSV content
    let csv = 'Parameter,Value,Unit\n';
    csv += `Date,${data.date},\n`;
    csv += `Latitude,${data.lat},degrees\n`;
    csv += `Longitude,${data.lon},degrees\n`;
    
    if (data.sst !== null) {
      csv += `SST (Celsius),${data.sst.toFixed(2)},°C\n`;
      csv += `SST (Fahrenheit),${toFahrenheit(data.sst).toFixed(2)},°F\n`;
      csv += `SST (Kelvin),${toKelvin(data.sst).toFixed(2)},K\n`;
      csv += `Classification,${classification?.label || ''},\n`;
      csv += `Climatology Mean${hasRealClimatology ? '' : ' (Est.)'},${climatologyMean.toFixed(2)},°C\n`;
      csv += `Anomaly${hasRealClimatology ? '' : ' (Est.)'},${anomaly.toFixed(2)},°C\n`;
      if (percentileRank !== null && percentileRank !== undefined) {
        csv += `Percentile Rank,${percentileRank.toFixed(1)},%\n`;
      }
      if (pValues?.p10 !== null && pValues?.p10 !== undefined) {
        csv += `P10,${pValues.p10.toFixed(2)},°C\n`;
        csv += `P50,${pValues.p50?.toFixed(2) || ''},°C\n`;
        csv += `P90,${pValues.p90?.toFixed(2) || ''},°C\n`;
      }
    }
    
    if (data.source) csv += `\nSource,${data.source}\n`;
    if (data.dataset) csv += `Dataset,${data.dataset}\n`;
    
    // Download
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sst_${data.date}_${data.lat.toFixed(2)}_${data.lon.toFixed(2)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Calculate panel edge position for connection line (left edge of panel)
  const panelLeftEdge = typeof window !== 'undefined' ? window.innerWidth - panelRight - panelWidth : 0;
  const panelConnectionY = panelTop + 40;

  // Debug: log when component renders with positions
  console.log('SSTInfoPanel render:', { 
    hasData: !!data, 
    loading, 
    screenPosition,
    panelLeftEdge,
    panelConnectionY
  });

  // Render connection line via portal to avoid parent stacking context issues
  const connectionLine = screenPosition && (data || loading) ? createPortal(
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
      {/* Subtle dashed line */}
      <line
        x1={screenPosition.x}
        y1={screenPosition.y}
        x2={panelLeftEdge}
        y2={panelConnectionY}
        stroke="rgba(110, 242, 252, 0.6)"
        strokeWidth="1.5"
        strokeDasharray="5,3"
        strokeLinecap="round"
      />
      {/* Dot at clicked point on globe */}
      <circle
        cx={screenPosition.x}
        cy={screenPosition.y}
        r="5"
        fill="rgba(110, 242, 252, 0.9)"
        stroke="rgba(0, 0, 0, 0.5)"
        strokeWidth="1"
      />
      {/* Small dot at panel edge */}
      <circle
        cx={panelLeftEdge}
        cy={panelConnectionY}
        r="3"
        fill="rgba(110, 242, 252, 0.9)"
      />
    </svg>,
    document.body
  ) : null;

  return (
    <>
      {/* Connection line rendered via portal */}
      {connectionLine}

      {/* Main Panel */}
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
        {/* Header */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 2,
            py: 1.5,
            borderBottom: 1,
            borderColor: 'divider',
            background: data?.sst != null 
              ? `linear-gradient(135deg, ${alpha(getSSTColor(data.sst), 0.3)} 0%, transparent 100%)`
              : undefined,
            cursor: isDragging ? 'grabbing' : 'grab',
          }}
          onMouseDown={handleMouseDown}
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <DragIndicator sx={{ fontSize: 16, color: 'rgba(255,255,255,0.4)' }} />
            <Typography variant="subtitle2" fontWeight={600} sx={{ color: 'rgba(255,255,255,0.9)' }}>
              SST
            </Typography>
          </Stack>
          <Stack direction="row" spacing={0.5}>
            <Tooltip title="Export as CSV" arrow>
              <IconButton 
                size="small" 
                onClick={handleExport}
                disabled={!data || data.sst === null}
                sx={{ 
                  color: 'rgba(255,255,255,0.5)',
                  '&:hover': { color: '#6EF2FC' },
                }}
              >
                <Download fontSize="small" />
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={onClose}>
              <Close fontSize="small" />
            </IconButton>
          </Stack>
        </Box>

        {/* Content */}
        <Box sx={{ p: 2 }}>
          {loading ? (
            <Stack alignItems="center" spacing={2} py={4}>
              <CircularProgress size={40} />
              <Typography variant="body2" color="text.secondary">
                Querying SST data...
              </Typography>
            </Stack>
          ) : data ? (
            <Stack spacing={2}>
              {/* Main Temperature Display */}
              {data.sst != null ? (
                <>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      p: 2,
                      borderRadius: 0,
                      bgcolor: alpha(getSSTColor(data.sst), 0.12),
                      border: '1px solid',
                      borderColor: alpha(getSSTColor(data.sst), 0.2),
                    }}
                  >
                    <Box>
                      <Typography 
                        variant="h2" 
                        fontWeight={900} 
                        sx={{ 
                          color: getSSTColor(data.sst), 
                          lineHeight: 1,
                          textShadow: `0 0 12px ${alpha(getSSTColor(data.sst), 0.7)}, 0 0 4px ${alpha(getSSTColor(data.sst), 0.4)}`,
                          filter: 'brightness(1.3)',
                          letterSpacing: '-0.02em',
                        }}
                      >
                        {data.sst.toFixed(1)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        degrees Celsius
                      </Typography>
                    </Box>
                    <Stack spacing={0.5} alignItems="flex-end">
                      <Chip
                        label={classification?.label}
                        size="small"
                        sx={{
                          bgcolor: alpha(classification?.color || '#888', 0.2),
                          color: classification?.color,
                          fontWeight: 600,
                          fontSize: '0.75rem',
                        }}
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 100, textAlign: 'right' }}>
                        {classification?.description}
                      </Typography>
                    </Stack>
                  </Box>

                  {/* Temperature gauge */}
                  <TemperatureGauge value={data.sst} />

                  {/* Historical percentiles */}
                  {(statsLoading || percentiles) && (
                    <Box>
                      <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                        <Timeline sx={{ fontSize: 18, color: 'text.secondary' }} />
                        <Typography variant="body2" fontWeight={600}>
                          Historical Context
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                          1940-2025
                        </Typography>
                      </Stack>
                      {statsLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                          <CircularProgress size={20} />
                        </Box>
                      ) : pValues && (
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 0, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary">P10</Typography>
                            <Typography variant="body2" fontWeight={500}>
                              {pValues.p10?.toFixed(1) ?? '—'}°C
                            </Typography>
                          </Box>
                          <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(110, 242, 252, 0.08)', borderRadius: 0, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary">Median</Typography>
                            <Typography variant="body2" fontWeight={600} sx={{ color: '#6EF2FC' }}>
                              {pValues.p50?.toFixed(1) ?? '—'}°C
                            </Typography>
                          </Box>
                          <Box sx={{ flex: 1, p: 1, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 0, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary">P90</Typography>
                            <Typography variant="body2" fontWeight={500}>
                              {pValues.p90?.toFixed(1) ?? '—'}°C
                            </Typography>
                          </Box>
                        </Box>
                      )}
                      {percentileRank !== null && percentileRank !== undefined && (
                        <Chip
                          label={getPercentileDescription(percentileRank)}
                          size="small"
                          sx={{ 
                            mt: 1, 
                            bgcolor: percentileRank >= 75 ? 'rgba(244, 67, 54, 0.15)' : 
                                     percentileRank <= 25 ? 'rgba(33, 150, 243, 0.15)' : 
                                     'rgba(255,255,255,0.06)',
                            color: percentileRank >= 75 ? 'error.light' : 
                                   percentileRank <= 25 ? 'info.light' : 
                                   'text.secondary',
                            fontSize: '0.7rem',
                          }}
                        />
                      )}
                    </Box>
                  )}

                  {/* Unit conversions */}
                  <Box sx={{ display: 'flex', gap: 2 }}>
                    <Box sx={{ flex: 1, p: 1.5, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 0 }}>
                      <Typography variant="caption" color="text.secondary">Fahrenheit</Typography>
                      <Typography variant="h6" fontWeight={600}>{toFahrenheit(data.sst).toFixed(1)}°F</Typography>
                    </Box>
                    <Box sx={{ flex: 1, p: 1.5, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 0 }}>
                      <Typography variant="caption" color="text.secondary">Kelvin</Typography>
                      <Typography variant="h6" fontWeight={600}>{toKelvin(data.sst).toFixed(2)} K</Typography>
                    </Box>
                  </Box>

                  <Divider />

                  {/* Climatology comparison */}
                  <Box>
                    <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                      <Speed sx={{ fontSize: 18, color: 'text.secondary' }} />
                      <Typography variant="body2" fontWeight={600}>
                        Anomaly{!hasRealClimatology && ' (Est.)'}
                      </Typography>
                      {!hasRealClimatology && (
                        <Tooltip title="Real climatology data unavailable. Showing estimated anomaly based on simplified zonal climatology.">
                          <Info sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
                        </Tooltip>
                      )}
                    </Stack>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                          {hasRealClimatology ? `${new Date(data.date).toLocaleString('en', { month: 'short' })} Mean` : 'Zonal Mean (Est.)'}
                        </Typography>
                        <Typography variant="body1">{hasRealClimatology ? '' : '~'}{climatologyMean.toFixed(1)}°C</Typography>
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Stack direction="row" alignItems="center" spacing={0.5}>
                          {anomaly >= 0 ? (
                            <TrendingUp sx={{ color: 'error.main', fontSize: 18 }} />
                          ) : (
                            <TrendingDown sx={{ color: 'info.main', fontSize: 18 }} />
                          )}
                          <Box>
                            <Typography variant="caption" color="text.secondary">Anomaly</Typography>
                            <Typography 
                              variant="body1" 
                              fontWeight={600}
                              color={anomaly >= 0 ? 'error.main' : 'info.main'}
                            >
                              {anomaly >= 0 ? '+' : ''}{anomaly.toFixed(1)}°C
                            </Typography>
                          </Box>
                        </Stack>
                      </Box>
                    </Box>
                  </Box>
                </>
              ) : (
                <Box
                  sx={{
                    py: 3,
                    px: 2,
                    borderRadius: 2,
                    bgcolor: 'action.disabledBackground',
                    textAlign: 'center',
                  }}
                >
                  <Typography variant="body1" color="text.secondary">
                    {data.message || 'No data available at this location'}
                  </Typography>
                  <Typography variant="caption" color="text.disabled" sx={{ mt: 1, display: 'block' }}>
                    This may be land, ice, or outside data coverage
                  </Typography>
                </Box>
              )}

              <Divider />

              {/* Location Details */}
              <Box>
                <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                  <Place sx={{ fontSize: 18, color: 'text.secondary' }} />
                  <Typography variant="body2" fontWeight={600}>
                    Location
                  </Typography>
                </Stack>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                  <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">Latitude</Typography>
                    <Typography variant="body2" fontFamily="monospace">
                      {Math.abs(data.lat).toFixed(4)}° {data.lat >= 0 ? 'N' : 'S'}
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">Longitude</Typography>
                    <Typography variant="body2" fontFamily="monospace">
                      {Math.abs(data.lon).toFixed(4)}° {data.lon >= 0 ? 'E' : 'W'}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {/* Date */}
              <Stack direction="row" spacing={1} alignItems="center">
                <CalendarMonth sx={{ fontSize: 18, color: 'text.secondary' }} />
                <Typography variant="body2" color="text.secondary">
                  {new Date(data.date).toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </Typography>
              </Stack>

              {/* Data Source */}
              {data.source && (
                <Box sx={{ pt: 1 }}>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip
                      label={data.source}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.7rem' }}
                    />
                    {data.dataset && (
                      <Chip
                        label={data.dataset}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: '0.7rem' }}
                      />
                    )}
                  </Stack>
                </Box>
              )}

              {/* Color scale legend */}
              <ColorScaleLegend />
            </Stack>
          ) : null}
        </Box>
      </Box>
    </>
  );
}
