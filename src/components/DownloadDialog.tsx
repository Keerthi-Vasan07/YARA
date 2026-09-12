import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Typography,
  TextField,
  Button,
  IconButton,
  Chip,
  FormControl,
  Select,
  MenuItem,
  Divider,
  Link,
  InputAdornment,
} from '@mui/material';
import {
  Close,
  Download,
  Map as MapIcon,
  DateRange,
  Layers,
  Storage,
} from '@mui/icons-material';

interface DownloadDialogProps {
  open: boolean;
  onClose: () => void;
  selectedDate: string;
  layerName?: string;
  variableCode?: string;
}

interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

export function DownloadDialog({
  open,
  onClose,
  selectedDate,
  layerName = 'Sea Surface Temperature',
  variableCode = 'sst',
}: DownloadDialogProps) {
  // Geographic area
  const [bbox, setBbox] = useState<BoundingBox>({
    north: 90,
    south: -90,
    east: 180,
    west: -180,
  });
  const [useMapBounds, setUseMapBounds] = useState(false);

  // Date range
  const [dateFrom, setDateFrom] = useState(selectedDate);
  const [dateTo, setDateTo] = useState(selectedDate);

  // Download format
  const [format, setFormat] = useState('netcdf');

  // Estimated file size (mock)
  const estimatedSize = () => {
    const latRange = bbox.north - bbox.south;
    const lonRange = bbox.east - bbox.west;
    const dateRange = 1; // Simplified for now
    const sizeKB = Math.round((latRange * lonRange * dateRange * 4) / 1000);
    if (sizeKB > 1000) {
      return `${(sizeKB / 1000).toFixed(1)} MB`;
    }
    return `${sizeKB} kB`;
  };

  // Reset date when selectedDate changes
  useEffect(() => {
    setDateFrom(selectedDate);
    setDateTo(selectedDate);
  }, [selectedDate]);

  const handleDownload = () => {
    // TODO: Implement actual download with backend endpoint
    // Build download URL with parameters
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
    const url = `/api/tiles/${variableCode}/${selectedDate}/0/0/0.png`;
    const link = document.createElement('a');
    link.href = url;
    link.download = `${variableCode}-${dateFrom}${dateTo !== dateFrom ? `-to-${dateTo}` : ''}.${format === 'netcdf' ? 'nc' : format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'rgba(8, 12, 18, 0.98)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 0,
        },
      }}
    >
      <DialogTitle
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          pb: 1.5,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Download sx={{ fontSize: 20, color: '#6EF2FC' }} />
          <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
            Download Data
          </Typography>
        </Box>
        <IconButton size="small" onClick={onClose} sx={{ color: 'text.secondary' }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 2.5 }}>
        {/* Layer info */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
            {layerName}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Chip 
              label={variableCode} 
              size="small" 
              sx={{ 
                bgcolor: 'rgba(110, 242, 252, 0.15)', 
                color: '#6EF2FC',
                fontFamily: 'monospace',
                fontSize: '0.7rem',
              }} 
            />
            <Typography variant="caption" color="text.secondary">
              Global monthly
            </Typography>
          </Box>
        </Box>

        {/* Geographic area */}
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <MapIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
            <Typography variant="subtitle2" sx={{ fontSize: '0.8rem' }}>
              Geographic area
            </Typography>
            <Link
              component="button"
              variant="caption"
              onClick={() => setUseMapBounds(!useMapBounds)}
              sx={{ ml: 'auto', color: '#6EF2FC', fontSize: '0.7rem' }}
            >
              Define on map
            </Link>
          </Box>
          
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
            <TextField
              label="North"
              type="number"
              size="small"
              value={bbox.north}
              onChange={(e) => setBbox({ ...bbox, north: parseFloat(e.target.value) || 0 })}
              InputProps={{
                endAdornment: <InputAdornment position="end">°</InputAdornment>,
              }}
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
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
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
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
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
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
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
            />
          </Box>
        </Box>

        <Divider sx={{ my: 2, borderColor: 'rgba(255,255,255,0.06)' }} />

        {/* Date range */}
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <DateRange sx={{ fontSize: 16, color: 'text.secondary' }} />
            <Typography variant="subtitle2" sx={{ fontSize: '0.8rem' }}>
              Date range
            </Typography>
          </Box>
          
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
            <TextField
              label="From"
              type="date"
              size="small"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
            />
            <TextField
              label="To"
              type="date"
              size="small"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{ '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
            />
          </Box>
          
          <Button
            size="small"
            variant="text"
            onClick={() => {
              setDateFrom(selectedDate);
              setDateTo(selectedDate);
            }}
            sx={{ 
              mt: 1, 
              fontSize: '0.7rem', 
              color: 'text.secondary',
              textTransform: 'none',
            }}
          >
            As in map
          </Button>
        </Box>

        <Divider sx={{ my: 2, borderColor: 'rgba(255,255,255,0.06)' }} />

        {/* Download format */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Layers sx={{ fontSize: 16, color: 'text.secondary' }} />
            <Typography variant="subtitle2" sx={{ fontSize: '0.8rem' }}>
              Download format
            </Typography>
          </Box>
          
          <FormControl size="small" fullWidth>
            <Select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              sx={{ fontSize: '0.8rem' }}
            >
              <MenuItem value="netcdf">NetCDF (.nc)</MenuItem>
              <MenuItem value="geotiff">GeoTIFF (.tif)</MenuItem>
              <MenuItem value="csv">CSV (.csv)</MenuItem>
              <MenuItem value="png">PNG Image (.png)</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {/* File size estimate */}
        <Box 
          sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1.5,
            p: 1.5,
            bgcolor: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <Storage sx={{ fontSize: 18, color: 'text.disabled' }} />
          <Typography variant="caption" color="text.secondary">
            Estimated size:
          </Typography>
          <Typography variant="caption" fontWeight={600}>
            ~ {estimatedSize()}
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <Button
          variant="text"
          onClick={onClose}
          sx={{ color: 'text.secondary', textTransform: 'none' }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleDownload}
          startIcon={<Download />}
          sx={{
            bgcolor: '#6EF2FC',
            color: '#0A0E14',
            textTransform: 'none',
            fontWeight: 600,
            '&:hover': {
              bgcolor: '#5DD8E8',
            },
          }}
        >
          Download
        </Button>
      </DialogActions>
    </Dialog>
  );
}
