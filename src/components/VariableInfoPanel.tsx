import { useRef, useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { 
  Box, Typography, IconButton, Stack, Chip, alpha, CircularProgress,
  Divider, Tooltip
} from '@mui/material';
import { 
  Close, Place, CalendarMonth, Download, AcUnit, Height, Grass, WbSunny, DragIndicator
} from '@mui/icons-material';
import { VariablePointQuery } from '../api/sstApi';

interface VariableInfoPanelProps {
  data: VariablePointQuery | null;
  loading: boolean;
  onClose: () => void;
  screenPosition?: { x: number; y: number } | null;
  topOffset?: number; // For stacking when multiple panels visible
}

// Variable-specific color scales
const VARIABLE_CONFIG: Record<string, {
  icon: React.ReactNode;
  colors: { value: number; color: string; label: string }[];
  min: number;
  max: number;
  format: (v: number) => string;
}> = {
  sic: {
    icon: <AcUnit sx={{ fontSize: 18 }} />,
    colors: [
      { value: 15, color: '#e3f2fd', label: 'Marginal' },
      { value: 30, color: '#90caf9', label: 'Light' },
      { value: 50, color: '#42a5f5', label: 'Moderate' },
      { value: 70, color: '#1e88e5', label: 'Dense' },
      { value: 85, color: '#1565c0', label: 'Very Dense' },
      { value: 100, color: '#0d47a1', label: 'Consolidated' },
    ],
    min: 0,
    max: 100,
    format: (v) => `${v.toFixed(0)}%`,
  },
  sla: {
    icon: <Height sx={{ fontSize: 18 }} />,
    colors: [
      { value: -0.5, color: '#0d47a1', label: 'Very Low' },
      { value: -0.2, color: '#1565c0', label: 'Low' },
      { value: -0.05, color: '#42a5f5', label: 'Slightly Low' },
      { value: 0.05, color: '#e0e0e0', label: 'Normal' },
      { value: 0.2, color: '#ff7043', label: 'Slightly High' },
      { value: 0.5, color: '#d32f2f', label: 'High' },
      { value: 1.0, color: '#b71c1c', label: 'Very High' },
    ],
    min: -0.5,
    max: 0.5,
    format: (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)} cm`,
  },
  chl: {
    icon: <Grass sx={{ fontSize: 18 }} />,
    colors: [
      { value: 0.01, color: '#f0f4e8', label: 'Oligotrophic' },      // Very low productivity
      { value: 0.1, color: '#c5e1a5', label: 'Low' },                // Low productivity
      { value: 0.3, color: '#8bc34a', label: 'Moderate Low' },       // Moderate-low
      { value: 1.0, color: '#558b2f', label: 'Moderate' },           // Moderate
      { value: 3.0, color: '#33691e', label: 'Moderate High' },      // Moderate-high
      { value: 10.0, color: '#1b5e20', label: 'Productive' },        // High productivity
      { value: 30.0, color: '#004d40', label: 'Highly Productive' }, // Very high
      { value: 100.0, color: '#00251a', label: 'Bloom' },            // Bloom conditions
    ],
    min: 0.01,
    max: 100,
    format: (v) => v < 1 ? `${v.toFixed(2)} mg/m³` : v < 10 ? `${v.toFixed(1)} mg/m³` : `${v.toFixed(0)} mg/m³`,
  },
  kd490: {
    icon: <WbSunny sx={{ fontSize: 18 }} />,
    colors: [
      { value: 0.01, color: '#e3f2fd', label: 'Very Clear' },        // Open ocean, deep blue
      { value: 0.03, color: '#90caf9', label: 'Clear' },             // Clear oceanic
      { value: 0.07, color: '#42a5f5', label: 'Moderate Clear' },    // Moderate oceanic
      { value: 0.15, color: '#1e88e5', label: 'Moderate' },          // Coastal transition
      { value: 0.3, color: '#26a69a', label: 'Moderate Turbid' },    // Coastal
      { value: 0.5, color: '#66bb6a', label: 'Turbid' },             // Turbid coastal
      { value: 1.0, color: '#ffb74d', label: 'Very Turbid' },        // Very turbid
      { value: 5.0, color: '#8d6e63', label: 'Extremely Turbid' },   // Extremely turbid
    ],
    min: 0.01,
    max: 5,
    format: (v) => v < 0.1 ? `${v.toFixed(3)} m⁻¹` : v < 1 ? `${v.toFixed(2)} m⁻¹` : `${v.toFixed(1)} m⁻¹`,
  },
};

// Get color for a value
function getValueColor(variable: string, value: number): string {
  const config = VARIABLE_CONFIG[variable];
  if (!config) return '#888';
  
  for (let i = config.colors.length - 1; i >= 0; i--) {
    if (value >= config.colors[i].value) {
      return config.colors[i].color;
    }
  }
  return config.colors[0].color;
}

// Get classification for a value
function getClassification(variable: string, value: number): { label: string; color: string } | null {
  const config = VARIABLE_CONFIG[variable];
  if (!config) return null;
  
  for (let i = config.colors.length - 1; i >= 0; i--) {
    if (value >= config.colors[i].value) {
      return { label: config.colors[i].label, color: config.colors[i].color };
    }
  }
  return { label: config.colors[0].label, color: config.colors[0].color };
}

// Value gauge component
function ValueGauge({ 
  value, 
  min, 
  max, 
  gradient 
}: { 
  value: number; 
  min: number; 
  max: number; 
  gradient: string;
}) {
  const percentage = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  
  return (
    <Box sx={{ position: 'relative', height: 12, borderRadius: 1, overflow: 'hidden', bgcolor: 'rgba(0,0,0,0.2)' }}>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background: gradient,
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
    </Box>
  );
}

export function VariableInfoPanel({ data, loading, onClose, screenPosition, topOffset = 0 }: VariableInfoPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const initialTop = 20 + topOffset;
  const initialRight = 80;
  const panelWidth = 300;

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

  if (!data && !loading) return null;

  const variable = data?.variable || 'unknown';
  const config = VARIABLE_CONFIG[variable];
  const classification = data?.value != null && config ? getClassification(variable, data.value) : null;
  const valueColor = data?.value != null && config ? getValueColor(variable, data.value) : '#888';

  // Calculate panel edge position for connection line
  const panelLeftEdge = typeof window !== 'undefined' ? window.innerWidth - panelRight - panelWidth : 0;
  const panelConnectionY = panelTop + 40;

  // Gradients for different variables
  const gradients: Record<string, string> = {
    sic: 'linear-gradient(90deg, #e3f2fd 0%, #90caf9 20%, #42a5f5 40%, #1e88e5 60%, #1565c0 80%, #0d47a1 100%)',
    sla: 'linear-gradient(90deg, #0d47a1 0%, #42a5f5 35%, #e0e0e0 50%, #ff7043 65%, #d32f2f 100%)',
  };

  // Export data as CSV
  const handleExport = () => {
    if (!data || data.value === null) return;
    
    let csv = 'Parameter,Value,Unit\n';
    csv += `Date,${data.date},\n`;
    csv += `Variable,${data.variable},\n`;
    csv += `Name,${data.name || data.variable.toUpperCase()},\n`;
    csv += `Latitude,${data.lat},degrees\n`;
    csv += `Longitude,${data.lon},degrees\n`;
    csv += `Value,${data.value},${data.unit}\n`;
    if (classification) csv += `Classification,${classification.label},\n`;
    if (data.source) csv += `Source,${data.source},\n`;
    if (data.dataset) csv += `Dataset,${data.dataset},\n`;
    
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${data.variable}_${data.date}_${data.lat.toFixed(2)}_${data.lon.toFixed(2)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Render connection line via portal
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
      <circle
        cx={screenPosition.x}
        cy={screenPosition.y}
        r="5"
        fill="rgba(110, 242, 252, 0.9)"
        stroke="rgba(0, 0, 0, 0.5)"
        strokeWidth="1"
      />
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
            background: data?.value != null 
              ? `linear-gradient(135deg, ${alpha(valueColor, 0.3)} 0%, transparent 100%)`
              : undefined,
            cursor: isDragging ? 'grabbing' : 'grab',
          }}
          onMouseDown={handleMouseDown}
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <DragIndicator sx={{ fontSize: 16, color: 'rgba(255,255,255,0.4)' }} />
            {config?.icon}
            <Typography variant="subtitle2" fontWeight={600} sx={{ color: 'rgba(255,255,255,0.9)' }}>
              {data?.name || variable.toUpperCase()}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={0.5}>
            <Tooltip title="Export as CSV" arrow>
              <IconButton 
                size="small" 
                onClick={handleExport}
                disabled={!data || data.value === null}
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
                Querying {variable.toUpperCase()} data...
              </Typography>
            </Stack>
          ) : data ? (
            <Stack spacing={2}>
              {/* Main Value Display */}
              {data.value != null && config ? (
                <>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      p: 2,
                      borderRadius: 0,
                      bgcolor: alpha(valueColor, 0.12),
                      border: '1px solid',
                      borderColor: alpha(valueColor, 0.2),
                    }}
                  >
                    <Box>
                      <Typography variant="h3" fontWeight={700} sx={{ color: valueColor, lineHeight: 1 }}>
                        {config.format(data.value)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {data.unit}
                      </Typography>
                    </Box>
                    {classification && (
                      <Chip
                        label={classification.label}
                        size="small"
                        sx={{
                          bgcolor: alpha(classification.color, 0.2),
                          color: classification.color,
                          fontWeight: 600,
                          fontSize: '0.75rem',
                        }}
                      />
                    )}
                  </Box>

                  {/* Value gauge */}
                  <ValueGauge 
                    value={data.value} 
                    min={config.min} 
                    max={config.max} 
                    gradient={gradients[variable] || 'linear-gradient(90deg, #888, #fff)'}
                  />
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
                    This may be land or outside data coverage
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
            </Stack>
          ) : null}
        </Box>
      </Box>
    </>
  );
}
