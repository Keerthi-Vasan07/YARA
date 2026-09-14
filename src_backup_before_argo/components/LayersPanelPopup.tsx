import { useEffect, useRef, useState } from 'react';
import {
  Box,
  Typography,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Chip,
  alpha,
  Divider,
  Fade,
  ClickAwayListener,
  Collapse,
  Button,
  TextField,
  InputAdornment,
  FormControl,
  Select,
  MenuItem,
  Link,
} from '@mui/material';
import {
  Close,
  Visibility,
  VisibilityOff,
  Thermostat,
  Waves,
  Air,
  Opacity,
  AcUnit,
  WaterDrop,
  Height,
  Grass,
  Download,
  Info,
  ExpandMore,
  ChevronRight,
  CropFree,
  Layers,
  WbSunny,
  Palette,
} from '@mui/icons-material';

export interface LayerItem {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  visible: boolean;
  enabled: boolean;
  category: 'ocean' | 'atmosphere';
}

interface LayersPanelPopupProps {
  open: boolean;
  onClose: () => void;
  layers: LayerItem[];
  onToggleLayer: (layerId: string) => void;
  anchorTop: number;
  anchorLeft: number;
  selectedDate?: string;
  onOpenInfo?: (layerId: string) => void;
  onStartDrawing?: () => void;
  drawnBbox?: { north: number; south: number; east: number; west: number } | null;
  isDrawingMode?: boolean;
  onOpenCatalog?: () => void;
}

// Layer metadata for info display
const LAYER_METADATA: Record<string, { unit: string; source: string; resolution: string }> = {
  sst: { unit: '°C', source: 'Copernicus Marine Service L4 OSTIA', resolution: '0.05°' },
  sic: { unit: '%', source: 'EUMETSAT OSI SAF / Copernicus Marine', resolution: '0.1°' },
  sla: { unit: 'm', source: 'Copernicus Marine Service L4', resolution: '0.25°' },
  chl: { unit: 'mg/m³', source: 'Copernicus Marine Service L3/L4', resolution: '0.05°' },
  swh: { unit: 'm', source: 'ERA5 Reanalysis', resolution: '0.25°' },
  msl: { unit: 'hPa', source: 'ERA5 Reanalysis', resolution: '0.25°' },
  u10: { unit: 'm/s', source: 'ERA5 Reanalysis', resolution: '0.25°' },
  tp: { unit: 'mm', source: 'ERA5 Reanalysis', resolution: '0.25°' },
};

export const DEFAULT_LAYERS: LayerItem[] = [
  {
    id: 'sst',
    name: 'Sea Surface Temperature',
    description: 'L4 gap-filled SST',
    icon: <Thermostat />,
    visible: true,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'sic',
    name: 'Sea Ice Concentration',
    description: 'Polar ice coverage',
    icon: <AcUnit />,
    visible: false,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'sla',
    name: 'Sea Level Anomaly',
    description: 'SSH deviation from mean',
    icon: <Height />,
    visible: false,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'chl',
    name: 'Chlorophyll-a',
    description: 'Phytoplankton biomass',
    icon: <Grass />,
    visible: false,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'kd490',
    name: 'Kd490 (Water Clarity)',
    description: 'Light attenuation at 490nm',
    icon: <WbSunny />,
    visible: false,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'rrs',
    name: 'Ocean Colour RGB',
    description: 'Rrs 670/555/443nm composite',
    icon: <Palette />,
    visible: false,
    enabled: true,
    category: 'ocean',
  },
  {
    id: 'swh',
    name: 'Significant Wave Height',
    description: 'Wave height (Hs)',
    icon: <Waves />,
    visible: false,
    enabled: false,
    category: 'ocean',
  },
  {
    id: 'msl',
    name: 'Mean Sea Level Pressure',
    description: 'Atmospheric pressure',
    icon: <Opacity />,
    visible: false,
    enabled: false,
    category: 'atmosphere',
  },
  {
    id: 'u10',
    name: 'Wind Speed (10m)',
    description: 'Surface wind',
    icon: <Air />,
    visible: false,
    enabled: false,
    category: 'atmosphere',
  },
  {
    id: 'tp',
    name: 'Total Precipitation',
    description: 'Rain & snow',
    icon: <WaterDrop />,
    visible: false,
    enabled: false,
    category: 'atmosphere',
  },
];

export function LayersPanelPopup({
  open,
  onClose,
  layers,
  onToggleLayer,
  anchorTop,
  anchorLeft,
  selectedDate = '',
  onOpenInfo,
  onStartDrawing,
  drawnBbox,
  isDrawingMode = false,
  onOpenCatalog,
}: LayersPanelPopupProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [expandedLayer, setExpandedLayer] = useState<string | null>(null);
  const [showDownload, setShowDownload] = useState(false);
  
  // Download form state
  const [bbox, setBbox] = useState({ north: 90, south: -90, east: 180, west: -180 });
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

  const oceanLayers = layers.filter((l) => l.category === 'ocean');
  const atmosphereLayers = layers.filter((l) => l.category === 'atmosphere');

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

  // Estimated file size
  const estimatedSize = () => {
    const latRange = bbox.north - bbox.south;
    const lonRange = bbox.east - bbox.west;
    const sizeKB = Math.round((latRange * lonRange * 4) / 1000);
    if (sizeKB > 1000) return `${(sizeKB / 1000).toFixed(1)} MB`;
    return `${sizeKB} kB`;
  };

  const handleDownload = () => {
    const layerId = expandedLayer || 'sst';
    const url = `/api/download/${layerId}?date=${dateFrom}&format=${format}&north=${bbox.north}&south=${bbox.south}&east=${bbox.east}&west=${bbox.west}`;
    const link = document.createElement('a');
    link.href = url;
    link.download = `${layerId}-${dateFrom}.${format === 'netcdf' ? 'nc' : format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setShowDownload(false);
  };

  const toggleLayerExpand = (layerId: string) => {
    setExpandedLayer(expandedLayer === layerId ? null : layerId);
    setShowDownload(false);
  };

  const renderLayerDetails = (layer: LayerItem) => {
    const meta = LAYER_METADATA[layer.id];
    const isExpanded = expandedLayer === layer.id;
    
    return (
      <Collapse in={isExpanded} key={`${layer.id}-details`}>
        <Box sx={{ px: 1.5, py: 1, bgcolor: 'rgba(0,0,0,0.2)', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          {/* Layer info */}
          <Box sx={{ mb: 1.5 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              {layer.description}
            </Typography>
            {meta && (
              <Box sx={{ display: 'flex', gap: 1.5, mt: 0.75, flexWrap: 'wrap' }}>
                <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem' }}>
                  Unit: <span style={{ color: 'rgba(255,255,255,0.7)' }}>{meta.unit}</span>
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem' }}>
                  Resolution: <span style={{ color: 'rgba(255,255,255,0.7)' }}>{meta.resolution}</span>
                </Typography>
              </Box>
            )}
            {meta && (
              <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: '0.6rem', display: 'block', mt: 0.5 }}>
                Source: {meta.source}
              </Typography>
            )}
          </Box>
          
          {/* Action buttons */}
          <Box sx={{ display: 'flex', gap: 0.5, mb: 1 }}>
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); setShowDownload(!showDownload); }}
              sx={{
                p: 0.75,
                bgcolor: showDownload ? 'rgba(110, 242, 252, 0.15)' : 'rgba(255,255,255,0.06)',
                color: showDownload ? '#6EF2FC' : 'inherit',
                '&:hover': { bgcolor: showDownload ? 'rgba(110, 242, 252, 0.2)' : 'rgba(255,255,255,0.1)' },
              }}
            >
              <Download sx={{ fontSize: 16 }} />
            </IconButton>
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); onOpenInfo?.(layer.id); }}
              sx={{
                p: 0.75,
                bgcolor: 'rgba(255,255,255,0.06)',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
              }}
            >
              <Info sx={{ fontSize: 16 }} />
            </IconButton>
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); onOpenCatalog?.(); }}
              sx={{
                p: 0.75,
                bgcolor: 'rgba(255,255,255,0.06)',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
              }}
            >
              <Layers sx={{ fontSize: 16 }} />
            </IconButton>
          </Box>
          
          {/* Download form */}
          <Collapse in={showDownload}>
            <Box sx={{ pt: 1, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
              {/* Geographic area */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                  Geographic area
                </Typography>
                {isDrawingMode ? (
                  <Typography variant="caption" sx={{ fontSize: '0.6rem', color: '#6EF2FC' }}>
                    Draw on map...
                  </Typography>
                ) : (
                  <Link
                    component="button"
                    variant="caption"
                    onClick={(e) => { e.stopPropagation(); onStartDrawing?.(); }}
                    sx={{ color: '#6EF2FC', fontSize: '0.6rem', display: 'flex', alignItems: 'center', gap: 0.5 }}
                  >
                    <CropFree sx={{ fontSize: 12 }} /> Draw
                  </Link>
                )}
              </Box>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75, mb: 1 }}>
                <TextField
                  label="N" type="number" size="small" value={bbox.north}
                  onChange={(e) => setBbox({ ...bbox, north: parseFloat(e.target.value) || 0 })}
                  InputProps={{ endAdornment: <InputAdornment position="end">°</InputAdornment> }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
                <TextField
                  label="E" type="number" size="small" value={bbox.east}
                  onChange={(e) => setBbox({ ...bbox, east: parseFloat(e.target.value) || 0 })}
                  InputProps={{ endAdornment: <InputAdornment position="end">°</InputAdornment> }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
                <TextField
                  label="S" type="number" size="small" value={bbox.south}
                  onChange={(e) => setBbox({ ...bbox, south: parseFloat(e.target.value) || 0 })}
                  InputProps={{ endAdornment: <InputAdornment position="end">°</InputAdornment> }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
                <TextField
                  label="W" type="number" size="small" value={bbox.west}
                  onChange={(e) => setBbox({ ...bbox, west: parseFloat(e.target.value) || 0 })}
                  InputProps={{ endAdornment: <InputAdornment position="end">°</InputAdornment> }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
              </Box>
              
              {/* Date range */}
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.75, mb: 1 }}>
                <TextField
                  label="From" type="date" size="small" value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
                <TextField
                  label="To" type="date" size="small" value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ '& .MuiInputBase-input': { fontSize: '0.7rem', py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                />
              </Box>
              
              {/* Format */}
              <FormControl size="small" fullWidth sx={{ mb: 1 }}>
                <Select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                  sx={{ fontSize: '0.7rem', '& .MuiSelect-select': { py: 0.5 } }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <MenuItem value="netcdf">NetCDF (.nc)</MenuItem>
                  <MenuItem value="geotiff">GeoTIFF (.tif)</MenuItem>
                  <MenuItem value="csv">CSV (.csv)</MenuItem>
                </Select>
              </FormControl>
              
              {/* Download button */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.6rem' }}>
                  Est. ~ {estimatedSize()}
                </Typography>
                <Button
                  variant="contained" size="small"
                  onClick={(e) => { e.stopPropagation(); handleDownload(); }}
                  startIcon={<Download sx={{ fontSize: 14 }} />}
                  sx={{
                    bgcolor: '#6EF2FC', color: '#0A0E14',
                    textTransform: 'none', fontSize: '0.7rem', fontWeight: 600, py: 0.5,
                    '&:hover': { bgcolor: '#5DD8E8' },
                  }}
                >
                  Download
                </Button>
              </Box>
            </Box>
          </Collapse>
        </Box>
      </Collapse>
    );
  };

  const renderLayer = (layer: LayerItem) => {
    const isExpanded = expandedLayer === layer.id;
    
    return (
      <Box key={layer.id}>
        <ListItem
          dense
          sx={{
            borderRadius: 0,
            mb: 0,
            py: 0.5,
            px: 1,
            bgcolor: (theme) =>
              isExpanded
                ? alpha(theme.palette.primary.main, 0.12)
                : layer.visible && layer.enabled
                  ? alpha(theme.palette.primary.main, 0.08)
                  : 'transparent',
            opacity: layer.enabled ? 1 : 0.45,
            cursor: layer.enabled ? 'pointer' : 'not-allowed',
            '&:hover': layer.enabled
              ? { bgcolor: 'rgba(255,255,255,0.06)' }
              : {},
            transition: 'background-color 0.15s ease',
          }}
        >
          {/* Expand button */}
          <ListItemIcon
            sx={{ minWidth: 24, cursor: 'pointer' }}
            onClick={(e) => { e.stopPropagation(); if (layer.enabled) toggleLayerExpand(layer.id); }}
          >
            {isExpanded ? (
              <ExpandMore sx={{ fontSize: 16, color: 'primary.main' }} />
            ) : (
              <ChevronRight sx={{ fontSize: 16, color: layer.enabled ? 'text.secondary' : 'text.disabled' }} />
            )}
          </ListItemIcon>
          <ListItemIcon
            sx={{
              minWidth: 28,
              color: layer.visible && layer.enabled ? 'primary.main' : 'text.disabled',
            }}
          >
            {layer.icon}
          </ListItemIcon>
          <ListItemText
            primary={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Typography
                  variant="body2"
                  sx={{
                    fontSize: '0.8125rem',
                    fontWeight: layer.visible && layer.enabled ? 600 : 400,
                    color: layer.enabled ? 'text.primary' : 'text.disabled',
                  }}
                  onClick={(e) => { e.stopPropagation(); if (layer.enabled) toggleLayerExpand(layer.id); }}
                >
                  {layer.name}
                </Typography>
                {!layer.enabled && (
                  <Chip
                    label="Soon"
                    size="small"
                    sx={{
                      height: 16,
                      fontSize: '0.6rem',
                      bgcolor: (theme) => alpha(theme.palette.text.disabled, 0.12),
                      color: 'text.disabled',
                      '& .MuiChip-label': { px: 0.75 },
                    }}
                  />
                )}
              </Box>
            }
            sx={{ my: 0 }}
          />
          <ListItemSecondaryAction>
            <IconButton
              edge="end"
              size="small"
              disabled={!layer.enabled}
              onClick={(e) => {
                e.stopPropagation();
                if (layer.enabled) onToggleLayer(layer.id);
              }}
              sx={{
                p: 0.5,
                color: layer.visible && layer.enabled ? 'primary.main' : 'text.disabled',
              }}
            >
              {layer.visible ? <Visibility fontSize="small" /> : <VisibilityOff fontSize="small" />}
            </IconButton>
          </ListItemSecondaryAction>
        </ListItem>
        {layer.enabled && renderLayerDetails(layer)}
      </Box>
    );
  };

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
            width: 320,
            maxHeight: 'calc(100vh - 160px)',
            bgcolor: 'rgba(8, 12, 18, 0.92)',
            backdropFilter: 'blur(16px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.04)',
            boxShadow: 'none',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1100,
          }}
        >
          {/* Header */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              px: 1.5,
              py: 1,
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
            <Typography variant="subtitle2" fontWeight={600}>
              Data Layers
            </Typography>
            <IconButton size="small" onClick={onClose} sx={{ p: 0.5 }}>
              <Close fontSize="small" />
            </IconButton>
          </Box>

          {/* Content */}
          <Box sx={{ flex: 1, overflow: 'auto', p: 1 }}>
            {/* Ocean */}
            <Box sx={{ mb: 1.5 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5, px: 0.5 }}>
                <Waves sx={{ fontSize: 14, color: 'primary.main' }} />
                <Typography
                  variant="caption"
                  sx={{ 
                    color: 'text.secondary', 
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                    fontSize: '0.65rem',
                  }}
                >
                  Ocean
                </Typography>
              </Box>
              <List dense disablePadding>
                {oceanLayers.map(renderLayer)}
              </List>
            </Box>

            <Divider sx={{ my: 1 }} />

            {/* Atmosphere */}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5, px: 0.5 }}>
                <Air sx={{ fontSize: 14, color: 'primary.main' }} />
                <Typography
                  variant="caption"
                  sx={{ 
                    color: 'text.secondary', 
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                    fontSize: '0.65rem',
                  }}
                >
                  Atmosphere
                </Typography>
              </Box>
              <List dense disablePadding>
                {atmosphereLayers.map(renderLayer)}
              </List>
            </Box>
          </Box>

          {/* Footer */}
          <Box
            sx={{
              px: 1.5,
              py: 0.75,
              borderTop: 1,
              borderColor: 'divider',
              bgcolor: (theme) => alpha(theme.palette.background.default, 0.5),
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
              Copernicus Marine Service
            </Typography>
            <Button
              size="small"
              onClick={onOpenCatalog}
              startIcon={<Waves sx={{ fontSize: 14 }} />}
              sx={{
                textTransform: 'none',
                fontSize: '0.7rem',
                py: 0.25,
                px: 1,
                color: '#6EF2FC',
                '&:hover': { bgcolor: 'rgba(110, 242, 252, 0.08)' },
              }}
            >
              Full Catalog
            </Button>
          </Box>
        </Box>
      </Fade>
    </ClickAwayListener>
  );
}
