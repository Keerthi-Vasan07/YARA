import { buildApiUrl } from '../api/config';
import { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Box,
  Typography,
  IconButton,
  Stack,
  Button,
  FormControl,
  Select,
  MenuItem,
  Divider,
  CircularProgress,
  Chip,
} from '@mui/material';
import {
  Close,
  Download,
  CropFree,
  CalendarMonth,
  Storage,
  Public,
} from '@mui/icons-material';
import { LicenseDialog, hasAcknowledgedLicense } from './LicenseDialog';

export interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

interface DownloadPanelProps {
  bbox: BoundingBox | null;
  selectedDate: string;
  variable: string;
  onClose: () => void;
  onStartDrawing: () => void;
  isDrawingMode: boolean;
}

type DownloadFormat = 'netcdf' | 'geotiff' | 'csv';

const FORMAT_OPTIONS: { value: DownloadFormat; label: string; description: string }[] = [
  { value: 'netcdf', label: 'NetCDF', description: 'CF-compliant, full metadata' },
  { value: 'geotiff', label: 'GeoTIFF', description: 'Raster with georeferencing' },
  { value: 'csv', label: 'CSV', description: 'Tabular lat/lon/value' },
];

// Estimate file size based on bbox and format
function estimateFileSize(bbox: BoundingBox | null, format: DownloadFormat): string {
  if (!bbox) return '~0 KB';
  
  const latRange = Math.abs(bbox.north - bbox.south);
  const lonRange = Math.abs(bbox.east - bbox.west);
  
  // Assuming 0.05° resolution (~20 points per degree)
  const pointsLat = Math.ceil(latRange * 20);
  const pointsLon = Math.ceil(lonRange * 20);
  const totalPoints = pointsLat * pointsLon;
  
  let bytesPerPoint: number;
  switch (format) {
    case 'netcdf':
      bytesPerPoint = 8; // float64 + metadata overhead
      break;
    case 'geotiff':
      bytesPerPoint = 4; // float32
      break;
    case 'csv':
      bytesPerPoint = 30; // "lat,lon,value\n" text
      break;
  }
  
  const totalBytes = totalPoints * bytesPerPoint;
  
  if (totalBytes < 1024) return `~${totalBytes} B`;
  if (totalBytes < 1024 * 1024) return `~${(totalBytes / 1024).toFixed(1)} KB`;
  return `~${(totalBytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Display names for variables
const VARIABLE_NAMES: Record<string, string> = {
  sst: 'Sea Surface Temperature',
  sic: 'Sea Ice Concentration',
  sla: 'Sea Level Anomaly',
  chl: 'Chlorophyll-a',
  kd490: 'Kd490',
};

export function DownloadPanel({
  bbox,
  selectedDate,
  variable,
  onClose,
  onStartDrawing,
  isDrawingMode,
}: DownloadPanelProps) {
  const [format, setFormat] = useState<DownloadFormat>('netcdf');
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [showLicenseDialog, setShowLicenseDialog] = useState(false);
  
  const panelTop = 20;
  const panelRight = 80;
  const panelWidth = 340;
  
  const estimatedSize = useMemo(() => estimateFileSize(bbox, format), [bbox, format]);
  
  // Handle Esc key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);
  
  // Check license before download
  const initiateDownload = useCallback(() => {
    if (!bbox || !selectedDate) return;
    
    // Check if already acknowledged this session
    if (hasAcknowledgedLicense()) {
      executeDownload();
    } else {
      setShowLicenseDialog(true);
    }
  }, [bbox, selectedDate]);

  // Handle actual download after license acknowledgement
  const executeDownload = useCallback(async () => {
    if (!bbox || !selectedDate) return;
    
    setIsDownloading(true);
    setDownloadError(null);
    
    try {
      const params = new URLSearchParams({
        date: selectedDate,
        north: bbox.north.toFixed(4),
        south: bbox.south.toFixed(4),
        east: bbox.east.toFixed(4),
        west: bbox.west.toFixed(4),
        format: format,
      });
      
      const response = await fetch(buildApiUrl(`/api/${variable}/subset?${params}`));
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Download failed' }));
        throw new Error(error.detail || 'Download failed');
      }
      
      // Get filename from response headers or generate one
      const contentDisposition = response.headers.get('content-disposition');
      let filename = `${variable}_${selectedDate}_subset.${format === 'netcdf' ? 'nc' : format === 'geotiff' ? 'tif' : 'csv'}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?(.+)"?/);
        if (match) filename = match[1];
      }
      
      // Download the file
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setIsDownloading(false);
    }
  }, [bbox, selectedDate, format, variable]);

  // Handle license acceptance
  const handleLicenseAccept = useCallback(() => {
    setShowLicenseDialog(false);
    executeDownload();
  }, [executeDownload]);

  return (
    <>
      {/* Main Panel */}
      <Box
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
            background: 'linear-gradient(135deg, rgba(110, 242, 252, 0.15) 0%, transparent 100%)',
          }}
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <Download sx={{ fontSize: 20, color: '#6EF2FC' }} />
            <Typography variant="subtitle2" fontWeight={600} sx={{ color: 'rgba(255,255,255,0.9)' }}>
              Download Data
            </Typography>
          </Stack>
          <IconButton size="small" onClick={onClose}>
            <Close fontSize="small" />
          </IconButton>
        </Box>

        {/* Content */}
        <Box sx={{ p: 2 }}>
          <Stack spacing={2}>
            {/* Bounding Box Section */}
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                <CropFree sx={{ fontSize: 18, color: 'text.secondary' }} />
                <Typography variant="body2" fontWeight={600}>
                  Geographic Area
                </Typography>
              </Stack>
              
              {bbox ? (
                <Box
                  sx={{
                    p: 1.5,
                    bgcolor: 'rgba(110, 242, 252, 0.08)',
                    border: '1px solid rgba(110, 242, 252, 0.2)',
                    borderRadius: 0,
                  }}
                >
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">North</Typography>
                      <Typography variant="body2" fontFamily="monospace">{bbox.north.toFixed(2)}°</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">South</Typography>
                      <Typography variant="body2" fontFamily="monospace">{bbox.south.toFixed(2)}°</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">West</Typography>
                      <Typography variant="body2" fontFamily="monospace">{bbox.west.toFixed(2)}°</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">East</Typography>
                      <Typography variant="body2" fontFamily="monospace">{bbox.east.toFixed(2)}°</Typography>
                    </Box>
                  </Box>
                  <Button
                    size="small"
                    startIcon={<CropFree />}
                    onClick={onStartDrawing}
                    disabled={isDrawingMode}
                    sx={{ mt: 1.5, color: '#6EF2FC' }}
                  >
                    Redraw area
                  </Button>
                </Box>
              ) : (
                <Box
                  sx={{
                    p: 2,
                    bgcolor: 'rgba(255,255,255,0.04)',
                    borderRadius: 0,
                    textAlign: 'center',
                  }}
                >
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    No area selected
                  </Typography>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={isDrawingMode ? <CircularProgress size={16} /> : <CropFree />}
                    onClick={onStartDrawing}
                    disabled={isDrawingMode}
                    sx={{
                      borderColor: 'rgba(110, 242, 252, 0.5)',
                      color: '#6EF2FC',
                      '&:hover': { borderColor: '#6EF2FC' },
                    }}
                  >
                    {isDrawingMode ? 'Drawing...' : 'Draw on map'}
                  </Button>
                </Box>
              )}
            </Box>

            <Divider />

            {/* Date Section */}
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                <CalendarMonth sx={{ fontSize: 18, color: 'text.secondary' }} />
                <Typography variant="body2" fontWeight={600}>
                  Date
                </Typography>
              </Stack>
              <Chip
                label={new Date(selectedDate).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
                size="small"
                sx={{ bgcolor: 'rgba(255,255,255,0.08)' }}
              />
            </Box>

            <Divider />

            {/* Format Section */}
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                <Storage sx={{ fontSize: 18, color: 'text.secondary' }} />
                <Typography variant="body2" fontWeight={600}>
                  Format
                </Typography>
              </Stack>
              <FormControl fullWidth size="small">
                <Select
                  value={format}
                  onChange={(e) => setFormat(e.target.value as DownloadFormat)}
                  sx={{
                    bgcolor: 'rgba(255,255,255,0.04)',
                    fontSize: '0.8125rem',
                    '& .MuiSelect-select': { py: 0.75 },
                    '& .MuiOutlinedInput-notchedOutline': {
                      borderColor: 'rgba(255,255,255,0.1)',
                    },
                  }}
                >
                  {FORMAT_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value} sx={{ py: 0.5 }}>
                      <Typography variant="body2" fontSize="0.8125rem">{opt.label}</Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>

            {/* Estimated Size */}
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                p: 1.5,
                bgcolor: 'rgba(255,255,255,0.04)',
                borderRadius: 0,
              }}
            >
              <Typography variant="body2" color="text.secondary">
                Estimated size
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {estimatedSize}
              </Typography>
            </Box>

            {/* Error message */}
            {downloadError && (
              <Box
                sx={{
                  p: 1.5,
                  bgcolor: 'rgba(244, 67, 54, 0.1)',
                  border: '1px solid rgba(244, 67, 54, 0.3)',
                  borderRadius: 0,
                }}
              >
                <Typography variant="caption" color="error">
                  {downloadError}
                </Typography>
              </Box>
            )}

            {/* Download Button */}
            <Button
              variant="contained"
              fullWidth
              size="small"
              startIcon={isDownloading ? <CircularProgress size={14} color="inherit" /> : <Download sx={{ fontSize: 16 }} />}
              onClick={initiateDownload}
              disabled={!bbox || isDownloading}
              sx={{
                bgcolor: '#6EF2FC',
                color: '#0A0E14',
                fontWeight: 600,
                py: 0.75,
                fontSize: '0.8125rem',
                '&:hover': { bgcolor: '#5DD8E8' },
                '&:disabled': { bgcolor: 'rgba(110, 242, 252, 0.3)' },
              }}
            >
              {isDownloading ? 'Downloading...' : 'Download'}
            </Button>

            {/* Data source info */}
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="center">
              <Public sx={{ fontSize: 14, color: 'text.disabled' }} />
              <Typography variant="caption" color="text.disabled">
                {VARIABLE_NAMES[variable] || variable.toUpperCase()} • Copernicus
              </Typography>
            </Stack>
          </Stack>
        </Box>
      </Box>

      {/* License Acknowledgement Dialog */}
      <LicenseDialog
        open={showLicenseDialog}
        onAccept={handleLicenseAccept}
        onCancel={() => setShowLicenseDialog(false)}
        dataSource={VARIABLE_NAMES[variable] || variable.toUpperCase()}
      />
    </>
  );
}
