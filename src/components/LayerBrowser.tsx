import { buildApiUrl } from '../api/config';
import { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  IconButton,
  Collapse,
  Tooltip,
  Fade,
  ClickAwayListener,
  TextField,
  Button,
  FormControl,
  Select,
  MenuItem,
  InputAdornment,
  Link,
  CircularProgress,
} from '@mui/material';
import {
  Close,
  ExpandMore,
  ChevronRight,
  Download,
  Info,
  Layers,
  Thermostat,
  Waves,
  Air,
  AcUnit,
  Public,
  KeyboardArrowUp,
  Height,
  CropFree,
} from '@mui/icons-material';

// Variable-specific color scales (match server/datasets.json)
const VARIABLE_SCALES: Record<string, { min: number; max: number; unit: string; gradient?: string }> = {
  sst: { min: -2, max: 35, unit: '°C' },
  sic: { min: 15, max: 100, unit: '%', gradient: 'linear-gradient(to right, #e3f2fd, #90caf9, #42a5f5, #1e88e5, #1565c0, #0d47a1)' },
  sla: { min: -50, max: 50, unit: 'cm', gradient: 'linear-gradient(to right, #0d47a1, #1565c0, #42a5f5, #e0e0e0, #ff7043, #d32f2f, #b71c1c)' },
  chl: { min: 0.01, max: 30, unit: 'mg/m³', gradient: 'linear-gradient(to right, #f0f4e8, #c5e1a5, #8bc34a, #558b2f, #33691e, #1b5e20, #004d40)' },
  kd490: { min: 0.01, max: 1, unit: 'm⁻¹', gradient: 'linear-gradient(to right, #e3f2fd, #90caf9, #42a5f5, #26a69a, #66bb6a, #ffb74d, #8d6e63)' },
  rrs: { min: 0, max: 1, unit: 'sr⁻¹', gradient: 'linear-gradient(to right, #000, #0d47a1, #1e88e5, #26a69a, #8bc34a, #ffc107, #ff5722, #fff)' },
};

// Define layer variable
export interface LayerVariable {
  id: string;
  name: string;
  shortCode: string;
  unit: string;
  enabled: boolean;
}

// Define product (group of variables)
export interface LayerProduct {
  id: string;
  name: string;
  temporal: 'daily' | 'monthly';
  variables: LayerVariable[];
}

// Define category
export interface LayerCategory {
  id: string;
  name: string;
  icon: React.ReactNode;
  products: LayerProduct[];
}

// Active layer selection
export interface ActiveLayer {
  categoryId: string;
  productId: string;
  variableId: string;
}

interface LayerBrowserProps {
  open: boolean;
  onClose: () => void;
  anchorTop: number;
  anchorLeft: number;
  selectedDate: string;
  activeLayer: ActiveLayer | null;
  onLayerSelect: (layer: ActiveLayer) => void;
  colorScaleMin: number;
  colorScaleMax: number;
  colormap: string;
  onOpenInfo: () => void;
  showLayerList: boolean;
  onToggleLayerList: () => void;
  onStartDrawing?: () => void;
  drawnBbox?: BoundingBox | null;
  isDrawingMode?: boolean;
}

interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

// Default layer catalog (ERA5-style)
export const LAYER_CATALOG: LayerCategory[] = [
  {
    id: 'ocean-temp',
    name: 'Ocean Temperature',
    icon: <Thermostat sx={{ fontSize: 16 }} />,
    products: [
      {
        id: 'sst-monthly',
        name: 'Sea Surface Temperature',
        temporal: 'monthly',
        variables: [
          { id: 'sst', name: 'Sea surface temperature', shortCode: 'sst', unit: '°C', enabled: true },
          { id: 'sst-anomaly', name: 'SST anomaly', shortCode: 'sst_anom', unit: '°C', enabled: false },
        ],
      },
      {
        id: 'sst-daily',
        name: 'Sea Surface Temperature',
        temporal: 'daily',
        variables: [
          { id: 'sst-d', name: 'Sea surface temperature', shortCode: 'sst', unit: '°C', enabled: false },
        ],
      },
    ],
  },
  {
    id: 'ocean-ice',
    name: 'Sea Ice',
    icon: <AcUnit sx={{ fontSize: 16 }} />,
    products: [
      {
        id: 'sic-monthly',
        name: 'Sea Ice Concentration',
        temporal: 'monthly',
        variables: [
          { id: 'sic', name: 'Sea ice concentration', shortCode: 'sic', unit: '%', enabled: true },
        ],
      },
      {
        id: 'sit-monthly',
        name: 'Sea Ice Thickness',
        temporal: 'monthly',
        variables: [
          { id: 'sithick', name: 'Sea ice thickness', shortCode: 'sithick', unit: 'm', enabled: false },
        ],
      },
    ],
  },
  {
    id: 'ocean-ssh',
    name: 'Sea Level',
    icon: <Height sx={{ fontSize: 16 }} />,
    products: [
      {
        id: 'sla-daily',
        name: 'Sea Level Anomaly',
        temporal: 'daily',
        variables: [
          { id: 'sla', name: 'Sea level anomaly', shortCode: 'sla', unit: 'm', enabled: true },
        ],
      },
    ],
  },
  {
    id: 'ocean-waves',
    name: 'Waves',
    icon: <Waves sx={{ fontSize: 16 }} />,
    products: [
      {
        id: 'swh-monthly',
        name: 'Significant Wave Height',
        temporal: 'monthly',
        variables: [
          { id: 'swh', name: 'Significant wave height', shortCode: 'swh', unit: 'm', enabled: false },
        ],
      },
      {
        id: 'mwd-monthly',
        name: 'Mean Wave Direction',
        temporal: 'monthly',
        variables: [
          { id: 'mwd', name: 'Mean wave direction', shortCode: 'mwd', unit: '°', enabled: false },
          { id: 'mwp', name: 'Mean wave period', shortCode: 'mwp', unit: 's', enabled: false },
        ],
      },
    ],
  },
  {
    id: 'atmosphere',
    name: 'Atmosphere',
    icon: <Air sx={{ fontSize: 16 }} />,
    products: [
      {
        id: 'wind-monthly',
        name: 'Wind',
        temporal: 'monthly',
        variables: [
          { id: 'u10', name: '10m u-component of wind', shortCode: 'u10', unit: 'm/s', enabled: false },
          { id: 'v10', name: '10m v-component of wind', shortCode: 'v10', unit: 'm/s', enabled: false },
          { id: 'ws10', name: 'Wind speed 10m', shortCode: 'ws10', unit: 'm/s', enabled: false },
        ],
      },
      {
        id: 'pressure-monthly',
        name: 'Pressure',
        temporal: 'monthly',
        variables: [
          { id: 'msl', name: 'Mean sea level pressure', shortCode: 'msl', unit: 'hPa', enabled: false },
        ],
      },
      {
        id: 'precip-monthly',
        name: 'Precipitation',
        temporal: 'monthly',
        variables: [
          { id: 'tp', name: 'Total precipitation', shortCode: 'tp', unit: 'mm', enabled: false },
        ],
      },
    ],
  },
];

// Color scale gradient component
function ColorScaleBar({ 
  min, 
  max, 
  unit, 
  colormap,
  customGradient 
}: { 
  min: number; 
  max: number; 
  unit: string; 
  colormap: string;
  customGradient?: string;
}) {
  const getGradient = () => {
    if (customGradient) return customGradient;
    if (colormap === 'viridis') {
      return 'linear-gradient(to right, #440154, #482878, #3e4a89, #31688e, #26828e, #1f9e89, #35b779, #6ece58, #b5de2b, #fde725)';
    }
    // thermal (default)
    return 'linear-gradient(to right, #042333, #0a4c6a, #2a7e8e, #3ca894, #8fd175, #faf541)';
  };

  const formatValue = (v: number) => {
    if (Math.abs(v) < 1) return v.toFixed(2);
    if (Math.abs(v) < 10) return v.toFixed(1);
    return v.toFixed(0);
  };
  const midValue = formatValue((min + max) / 2);

  return (
    <Box sx={{ mt: 1.5, px: 0.5 }}>
      <Box
        sx={{
          height: 10,
          borderRadius: 0,
          background: getGradient(),
          border: '1px solid rgba(255,255,255,0.1)',
        }}
      />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
          {formatValue(min)}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
          {midValue}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
          {formatValue(max)} {unit}
        </Typography>
      </Box>
    </Box>
  );
}

// Product row component (collapsible) - simplified like Copernicus
function ProductRow({
  category,
  product,
  activeLayer,
  onLayerSelect,
  expanded,
  onToggleExpand,
}: {
  category: LayerCategory;
  product: LayerProduct;
  activeLayer: ActiveLayer | null;
  onLayerSelect: (layer: ActiveLayer) => void;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const totalCount = product.variables.length;
  const temporalLabel = product.temporal === 'daily' ? 'daily' : 'monthly';

  // Check if this product contains the active layer
  const containsActive = activeLayer?.categoryId === category.id && activeLayer?.productId === product.id;

  return (
    <Box>
      {/* Product header - simplified row */}
      <Box
        onClick={onToggleExpand}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          py: 0.625,
          px: 0.5,
          cursor: 'pointer',
          borderRadius: 0,
          bgcolor: containsActive ? 'rgba(110, 242, 252, 0.05)' : 'transparent',
          '&:hover': {
            bgcolor: containsActive ? 'rgba(110, 242, 252, 0.08)' : 'rgba(255,255,255,0.04)',
          },
        }}
      >
        <Typography 
          variant="body2" 
          sx={{ 
            fontSize: '0.8125rem', 
            flex: 1,
            color: containsActive ? 'text.primary' : 'text.secondary',
          }}
        >
          {product.name}, {temporalLabel}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Layers sx={{ fontSize: 14, color: 'text.disabled' }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.75rem' }}>
            {totalCount}
          </Typography>
        </Box>
        {expanded ? (
          <ExpandMore sx={{ fontSize: 16, color: 'text.disabled' }} />
        ) : (
          <ChevronRight sx={{ fontSize: 16, color: 'text.disabled' }} />
        )}
      </Box>

      {/* Variables list - simplified */}
      <Collapse in={expanded}>
        <Box sx={{ pl: 1.5, py: 0.25 }}>
          {product.variables.map((variable) => {
            const isActive =
              activeLayer?.categoryId === category.id &&
              activeLayer?.productId === product.id &&
              activeLayer?.variableId === variable.id;

            return (
              <Box
                key={variable.id}
                onClick={() => {
                  if (variable.enabled) {
                    onLayerSelect({
                      categoryId: category.id,
                      productId: product.id,
                      variableId: variable.id,
                    });
                  }
                }}
                sx={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 0.75,
                  py: 0.5,
                  px: 0.5,
                  cursor: variable.enabled ? 'pointer' : 'not-allowed',
                  opacity: variable.enabled ? 1 : 0.5,
                  borderRadius: 0,
                  bgcolor: isActive ? 'rgba(110, 242, 252, 0.08)' : 'transparent',
                  '&:hover': variable.enabled
                    ? { bgcolor: isActive ? 'rgba(110, 242, 252, 0.12)' : 'rgba(255,255,255,0.04)' }
                    : {},
                }}
              >
                {/* Arrow or bullet indicator */}
                <Typography 
                  sx={{ 
                    fontSize: '0.75rem', 
                    color: isActive ? '#6EF2FC' : 'text.secondary',
                    mt: 0.125,
                  }}
                >
                  →
                </Typography>
                <Box sx={{ flex: 1 }}>
                  <Typography
                    component="span"
                    sx={{
                      fontSize: '0.75rem',
                      color: isActive ? '#6EF2FC' : variable.enabled ? 'text.primary' : 'text.disabled',
                      fontWeight: isActive ? 500 : 400,
                    }}
                  >
                    {variable.name}
                  </Typography>
                  <Typography 
                    component="span" 
                    sx={{ 
                      fontSize: '0.7rem', 
                      color: 'text.disabled',
                      ml: 0.5,
                    }}
                  >
                    [{variable.unit}]
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Collapse>
    </Box>
  );
}

export function LayerBrowser({
  open,
  onClose,
  anchorTop,
  anchorLeft,
  selectedDate,
  activeLayer,
  onLayerSelect,
  colorScaleMin,
  colorScaleMax,
  colormap,
  onOpenInfo,
  showLayerList,
  onToggleLayerList,
  onStartDrawing,
  drawnBbox,
  isDrawingMode = false,
}: LayerBrowserProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [expandedProducts, setExpandedProducts] = useState<Set<string>>(new Set(['sst-monthly']));
  const [showDownload, setShowDownload] = useState(false);

  // Download form state
  const [bbox, setBbox] = useState<BoundingBox>({
    north: 90,
    south: -90,
    east: 180,
    west: -180,
  });
  const [dateFrom, setDateFrom] = useState(selectedDate);
  const [dateTo, setDateTo] = useState(selectedDate);
  const [format, setFormat] = useState('netcdf');

  // Update bbox when drawn from map
  useEffect(() => {
    if (drawnBbox) {
      setBbox(drawnBbox);
    }
  }, [drawnBbox]);

  // Reset dates when selectedDate changes
  useEffect(() => {
    setDateFrom(selectedDate);
    setDateTo(selectedDate);
  }, [selectedDate]);

  // Estimated file size
  const estimatedSize = () => {
    const latRange = bbox.north - bbox.south;
    const lonRange = bbox.east - bbox.west;
    const sizeKB = Math.round((latRange * lonRange * 4) / 1000);
    if (sizeKB > 1000) {
      return `${(sizeKB / 1000).toFixed(1)} MB`;
    }
    return `${sizeKB} kB`;
  };

  const handleDownload = () => {
    const activeDetails = getActiveLayerDetails();
    const variableCode = activeDetails?.variable.shortCode || 'sst';
    
    const downloadParams = {
      variable: variableCode,
      date_from: dateFrom,
      date_to: dateTo,
      north: bbox.north.toString(),
      south: bbox.south.toString(),
      east: bbox.east.toString(),
      west: bbox.west.toString(),
      format: format,
    };
    console.log('Download params:', downloadParams);
    
    // For now, just download the current tile
    const url = buildApiUrl(`/api/tiles/${variableCode}/${selectedDate}/0/0/0.png`);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${variableCode}-${dateFrom}${dateTo !== dateFrom ? `-to-${dateTo}` : ''}.${format === 'netcdf' ? 'nc' : format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    setShowDownload(false);
  };

  // Find active layer details
  const getActiveLayerDetails = () => {
    if (!activeLayer) return null;
    for (const category of LAYER_CATALOG) {
      if (category.id === activeLayer.categoryId) {
        for (const product of category.products) {
          if (product.id === activeLayer.productId) {
            const variable = product.variables.find((v) => v.id === activeLayer.variableId);
            if (variable) {
              return { category, product, variable };
            }
          }
        }
      }
    }
    return null;
  };

  const activeDetails = getActiveLayerDetails();

  const handleToggleProduct = (productId: string) => {
    setExpandedProducts((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [open, onClose]);

  if (!open) return null;

  return (
    <ClickAwayListener onClickAway={onClose}>
      <Fade in={open} timeout={150}>
        <Box
          ref={panelRef}
          sx={{
            position: 'absolute',
            top: anchorTop,
            left: anchorLeft,
            width: 340,
            maxHeight: 'calc(100vh - 120px)',
            bgcolor: 'rgba(8, 12, 18, 0.95)',
            backdropFilter: 'blur(20px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.06)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1200,
          }}
        >
          {/* Header with close button */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              px: 1.5,
              py: 1,
              borderBottom: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <Typography variant="subtitle2" fontWeight={600} sx={{ fontSize: '0.875rem' }}>
              Data Layers
            </Typography>
            <IconButton size="small" onClick={onClose} sx={{ p: 0.5 }}>
              <Close fontSize="small" />
            </IconButton>
          </Box>

          {/* Active layer details */}
          {activeDetails && (
            <Box
              sx={{
                px: 1.5,
                py: 1.25,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                bgcolor: 'rgba(0,0,0,0.2)',
              }}
            >
              {/* Layer name and code */}
              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                <Box sx={{ flex: 1 }}>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 600, fontSize: '0.875rem', lineHeight: 1.3 }}
                  >
                    {activeDetails.variable.name}
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
                    <Typography
                      variant="caption"
                      sx={{
                        bgcolor: 'rgba(110, 242, 252, 0.15)',
                        color: '#6EF2FC',
                        px: 0.75,
                        py: 0.125,
                        borderRadius: 0,
                        fontSize: '0.65rem',
                        fontWeight: 600,
                        fontFamily: 'monospace',
                      }}
                    >
                      {activeDetails.variable.shortCode}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {/* Metadata row */}
              <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  {selectedDate || 'No date'}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  Surface
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  Global {activeDetails.product.temporal}
                </Typography>
              </Box>

              {/* Color scale bar - use variable-specific scale for non-SST layers */}
              {(() => {
                const varCode = activeDetails.variable.shortCode;
                const varScale = VARIABLE_SCALES[varCode] || VARIABLE_SCALES.sst;
                const isSST = varCode === 'sst';
                return (
                  <ColorScaleBar
                    min={isSST ? colorScaleMin : varScale.min}
                    max={isSST ? colorScaleMax : varScale.max}
                    unit={varScale.unit}
                    colormap={colormap}
                    customGradient={isSST ? undefined : varScale.gradient}
                  />
                );
              })()}

              {/* Action buttons */}
              <Box sx={{ display: 'flex', gap: 0.5, mt: 1.5 }}>
                <Tooltip title={showDownload ? 'Hide download' : 'Download data'} placement="top">
                  <IconButton
                    size="small"
                    onClick={() => setShowDownload(!showDownload)}
                    sx={{
                      p: 0.75,
                      bgcolor: showDownload ? 'rgba(110, 242, 252, 0.15)' : 'rgba(255,255,255,0.06)',
                      color: showDownload ? '#6EF2FC' : 'inherit',
                      '&:hover': { bgcolor: showDownload ? 'rgba(110, 242, 252, 0.2)' : 'rgba(255,255,255,0.1)' },
                    }}
                  >
                    <Download sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Layer info" placement="top">
                  <IconButton
                    size="small"
                    onClick={onOpenInfo}
                    sx={{
                      p: 0.75,
                      bgcolor: 'rgba(255,255,255,0.06)',
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
                    }}
                  >
                    <Info sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
                <Tooltip title={showLayerList ? 'Hide layers' : 'Show layers'} placement="top">
                  <IconButton
                    size="small"
                    onClick={onToggleLayerList}
                    sx={{
                      p: 0.75,
                      bgcolor: showLayerList ? 'rgba(110, 242, 252, 0.15)' : 'rgba(255,255,255,0.06)',
                      color: showLayerList ? '#6EF2FC' : 'inherit',
                      '&:hover': { bgcolor: showLayerList ? 'rgba(110, 242, 252, 0.2)' : 'rgba(255,255,255,0.1)' },
                    }}
                  >
                    <Layers sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          )}

          {/* Inline Download Form */}
          <Collapse in={showDownload}>
            <Box
              sx={{
                px: 1.5,
                py: 1.5,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                bgcolor: 'rgba(0,0,0,0.15)',
              }}
            >
              {/* Collapse header */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontSize: '0.8rem', fontWeight: 600 }}>
                  Download Options
                </Typography>
                <IconButton size="small" onClick={() => setShowDownload(false)} sx={{ p: 0.25 }}>
                  <KeyboardArrowUp sx={{ fontSize: 16 }} />
                </IconButton>
              </Box>

              {/* Geographic area */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  Geographic area
                </Typography>
                {isDrawingMode ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <CircularProgress size={12} sx={{ color: '#6EF2FC' }} />
                    <Typography variant="caption" sx={{ fontSize: '0.65rem', color: '#6EF2FC' }}>
                      Click two corners on map...
                    </Typography>
                  </Box>
                ) : (
                  <Link
                    component="button"
                    variant="caption"
                    onClick={() => onStartDrawing?.()}
                    sx={{ 
                      color: '#6EF2FC', 
                      fontSize: '0.65rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      textDecoration: 'none',
                      '&:hover': { textDecoration: 'underline' },
                    }}
                  >
                    <CropFree sx={{ fontSize: 12 }} />
                    Draw on map
                  </Link>
                )}
              </Box>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mb: 1.5 }}>
                <TextField
                  label="North"
                  type="number"
                  size="small"
                  value={bbox.north}
                  onChange={(e) => setBbox({ ...bbox, north: parseFloat(e.target.value) || 0 })}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">°</InputAdornment>,
                  }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
                <TextField
                  label="East"
                  type="number"
                  size="small"
                  value={bbox.east}
                  onChange={(e) => setBbox({ ...bbox, east: parseFloat(e.target.value) || 0 })}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">°</InputAdornment>,
                  }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
                <TextField
                  label="South"
                  type="number"
                  size="small"
                  value={bbox.south}
                  onChange={(e) => setBbox({ ...bbox, south: parseFloat(e.target.value) || 0 })}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">°</InputAdornment>,
                  }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
                <TextField
                  label="West"
                  type="number"
                  size="small"
                  value={bbox.west}
                  onChange={(e) => setBbox({ ...bbox, west: parseFloat(e.target.value) || 0 })}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">°</InputAdornment>,
                  }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
              </Box>

              {/* Date range */}
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem', mb: 0.5, display: 'block' }}>
                Date range
              </Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mb: 1.5 }}>
                <TextField
                  label="From"
                  type="date"
                  size="small"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
                <TextField
                  label="To"
                  type="date"
                  size="small"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.75rem', py: 0.75 } }}
                />
              </Box>

              {/* Format */}
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem', mb: 0.5, display: 'block' }}>
                Format
              </Typography>
              <FormControl size="small" fullWidth sx={{ mb: 1.5 }}>
                <Select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                  sx={{ fontSize: '0.75rem', '& .MuiSelect-select': { py: 0.75 } }}
                >
                  <MenuItem value="netcdf">NetCDF (.nc)</MenuItem>
                  <MenuItem value="geotiff">GeoTIFF (.tif)</MenuItem>
                  <MenuItem value="csv">CSV (.csv)</MenuItem>
                </Select>
              </FormControl>

              {/* Size estimate & Download button */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  Est. ~ {estimatedSize()}
                </Typography>
                <Button
                  variant="contained"
                  size="small"
                  onClick={handleDownload}
                  startIcon={<Download sx={{ fontSize: 14 }} />}
                  sx={{
                    bgcolor: '#6EF2FC',
                    color: '#0A0E14',
                    textTransform: 'none',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    py: 0.5,
                    '&:hover': {
                      bgcolor: '#5DD8E8',
                    },
                  }}
                >
                  Download
                </Button>
              </Box>
            </Box>
          </Collapse>

          {/* Layer catalog - flat list of products */}
          <Collapse in={showLayerList}>
            <Box sx={{ flex: 1, overflow: 'auto', px: 1, py: 0.5, maxHeight: 300 }}>
              {LAYER_CATALOG.flatMap((category) =>
                category.products.map((product) => (
                  <ProductRow
                    key={product.id}
                    category={category}
                    product={product}
                    activeLayer={activeLayer}
                    onLayerSelect={onLayerSelect}
                    expanded={expandedProducts.has(product.id)}
                    onToggleExpand={() => handleToggleProduct(product.id)}
                  />
                ))
              )}
            </Box>
          </Collapse>

          {/* Footer */}
          <Box
            sx={{
              px: 1.5,
              py: 0.75,
              borderTop: '1px solid rgba(255,255,255,0.06)',
              bgcolor: 'rgba(0,0,0,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
              ERA5 ARCO Reanalysis
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Public sx={{ fontSize: 12, color: 'text.disabled' }} />
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
                0.25° resolution
              </Typography>
            </Box>
          </Box>
        </Box>
      </Fade>
    </ClickAwayListener>
  );
}

// Default active layer (SST)
export const DEFAULT_ACTIVE_LAYER: ActiveLayer = {
  categoryId: 'ocean-temp',
  productId: 'sst-monthly',
  variableId: 'sst',
};
