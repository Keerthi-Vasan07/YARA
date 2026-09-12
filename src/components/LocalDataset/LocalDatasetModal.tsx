import { useState, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Chip,
  LinearProgress,
  IconButton,
  Alert,
  List,
  ListItem,
  Divider,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import StorageIcon from '@mui/icons-material/Storage';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';

import { DatasetInfo } from '../../types/dataset';
import {
  uploadDatasetFile,
  fetchDatasetList,
  activateLocalDataset,
  deactivateLocalDataset,
} from '../../services/localDatasetApi';

interface LocalDatasetModalProps {
  open: boolean;
  onClose: () => void;
  activeDataset: DatasetInfo | null;
  onDatasetActivated: (dataset: DatasetInfo) => void;
  onDatasetDeactivated: () => void;
}

const SUPPORTED_FORMATS = [
  { ext: '.nc / .netcdf', label: 'NetCDF-3 / NetCDF-4', color: '#00e5ff' },
  { ext: 'Zarr', label: 'Zarr Arrays', color: '#00e676' },
  { ext: '.tif / .tiff', label: 'GeoTIFF Raster', color: '#ffb300' },
  { ext: '.h5 / .hdf5', label: 'HDF5', color: '#ab47bc' },
  { ext: '.csv', label: 'Tabular / Observations', color: '#29b6f6' },
  { ext: '.asc / .txt', label: 'ASCII Grid', color: '#8d6e63' },
  { ext: '.json / .geojson', label: 'GeoJSON Points', color: '#ff7043' },
  { ext: '.grib / .grb', label: 'GRIB / GRIB2', color: '#7e57c2' },
  { ext: '.bufr', label: 'WMO BUFR', color: '#78909c' },
];

export function LocalDatasetModal({
  open,
  onClose,
  activeDataset,
  onDatasetActivated,
  onDatasetDeactivated,
}: LocalDatasetModalProps) {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load available datasets
  const loadDatasets = async () => {
    try {
      const list = await fetchDatasetList();
      setDatasets(list);
    } catch (e: any) {
      console.warn('Failed to list datasets:', e);
    }
  };

  useEffect(() => {
    if (open) {
      loadDatasets();
      setError(null);
      setSuccessMsg(null);
    }
  }, [open]);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    setUploadProgress(0);
    setError(null);
    setSuccessMsg(null);

    try {
      const info = await uploadDatasetFile(file, undefined, (pct) => {
        setUploadProgress(pct);
      });
      setSuccessMsg(`Successfully ingested: ${info.name} (${info.format.toUpperCase()})`);
      await loadDatasets();
      onDatasetActivated(info);
    } catch (err: any) {
      setError(err.message || 'Failed to ingest scientific dataset');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleActivate = async (ds: DatasetInfo) => {
    try {
      setError(null);
      const active = await activateLocalDataset(ds.id);
      onDatasetActivated(active);
      setSuccessMsg(`Activated dataset: ${ds.name}`);
    } catch (err: any) {
      setError(err.message || 'Failed to activate dataset');
    }
  };

  const handleDeactivate = async () => {
    try {
      await deactivateLocalDataset();
      onDatasetDeactivated();
      setSuccessMsg('Returned to Online NOAA OPeNDAP Mode');
    } catch (err: any) {
      setError(err.message || 'Failed to deactivate local dataset');
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'rgba(10, 15, 24, 0.96)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          color: '#ffffff',
          borderRadius: 1,
        },
      }}
    >
      <DialogTitle
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          py: 1.5,
          px: 3,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <StorageIcon sx={{ color: '#00e5ff', fontSize: 24 }} />
          <Typography variant="h6" sx={{ fontSize: '1.05rem', fontWeight: 600, letterSpacing: '0.02em' }}>
            Local Scientific Dataset Ingestion
          </Typography>
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: 'rgba(255,255,255,0.6)' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2, bgcolor: 'rgba(211, 47, 47, 0.2)', color: '#ff8a80' }}>
            {error}
          </Alert>
        )}

        {successMsg && (
          <Alert severity="success" sx={{ mb: 2, bgcolor: 'rgba(46, 125, 50, 0.2)', color: '#b9f6ca' }}>
            {successMsg}
          </Alert>
        )}

        {/* Drag and Drop Box */}
        <Box
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          sx={{
            border: `2px dashed ${dragOver ? '#00e5ff' : 'rgba(255,255,255,0.18)'}`,
            borderRadius: 1.5,
            p: 3.5,
            textAlign: 'center',
            cursor: 'pointer',
            bgcolor: dragOver ? 'rgba(0, 229, 255, 0.04)' : 'rgba(255,255,255,0.02)',
            transition: 'all 0.2s ease',
            mb: 3,
            '&:hover': {
              borderColor: '#00e5ff',
              bgcolor: 'rgba(0, 229, 255, 0.03)',
            },
          }}
        >
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                handleFileUpload(e.target.files[0]);
              }
            }}
          />
          <CloudUploadIcon sx={{ fontSize: 44, color: '#00e5ff', mb: 1.5, opacity: 0.9 }} />
          <Typography sx={{ fontWeight: 600, fontSize: '0.95rem', mb: 0.5 }}>
            Drag & Drop your scientific dataset here, or click to browse
          </Typography>
          <Typography sx={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.5)', mb: 2 }}>
            Automatic format detection, coordinate extraction, and variable discovery.
          </Typography>

          {/* Supported Format Chips */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, justifyContent: 'center' }}>
            {SUPPORTED_FORMATS.map((fmt) => (
              <Chip
                key={fmt.ext}
                label={fmt.ext}
                size="small"
                sx={{
                  bgcolor: 'rgba(255,255,255,0.06)',
                  color: fmt.color,
                  border: `1px solid ${fmt.color}33`,
                  fontSize: '0.7rem',
                  fontWeight: 500,
                  height: 22,
                }}
              />
            ))}
          </Box>
        </Box>

        {/* Upload Progress */}
        {isUploading && (
          <Box sx={{ mb: 3 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
              <Typography sx={{ fontSize: '0.78rem', color: '#00e5ff' }}>Ingesting & Analyzing Dataset...</Typography>
              <Typography sx={{ fontSize: '0.78rem', color: '#00e5ff' }}>{uploadProgress}%</Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={uploadProgress}
              sx={{
                bgcolor: 'rgba(255,255,255,0.1)',
                '& .MuiLinearProgress-bar': { bgcolor: '#00e5ff' },
              }}
            />
          </Box>
        )}

        {/* Registered Datasets List */}
        <Box>
          <Typography sx={{ fontSize: '0.85rem', fontWeight: 600, mb: 1, color: 'rgba(255,255,255,0.85)' }}>
            Available Datasets ({datasets.length})
          </Typography>

          {datasets.length === 0 ? (
            <Typography sx={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.4)', fontStyle: 'italic', py: 2 }}>
              No local datasets found. Drop a scientific file above to get started.
            </Typography>
          ) : (
            <List sx={{ bgcolor: 'rgba(0,0,0,0.2)', borderRadius: 1, p: 0, border: '1px solid rgba(255,255,255,0.04)' }}>
              {datasets.map((ds, idx) => {
                const isActive = activeDataset?.id === ds.id;
                const varNames = Object.keys(ds.variables);

                return (
                  <Box key={ds.id}>
                    <ListItem
                      sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        py: 1.5,
                        px: 2,
                        bgcolor: isActive ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
                      }}
                    >
                      <Box sx={{ flex: 1, pr: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                          <Typography sx={{ fontWeight: 600, fontSize: '0.875rem' }}>{ds.name}</Typography>
                          <Chip
                            label={ds.format.toUpperCase()}
                            size="small"
                            sx={{
                              height: 18,
                              fontSize: '0.65rem',
                              bgcolor: 'rgba(0,229,255,0.15)',
                              color: '#00e5ff',
                            }}
                          />
                          {isActive && (
                            <Chip
                              icon={<CheckCircleIcon sx={{ fontSize: '12px !important', color: '#00e676 !important' }} />}
                              label="ACTIVE"
                              size="small"
                              sx={{
                                height: 18,
                                fontSize: '0.65rem',
                                bgcolor: 'rgba(0,230,118,0.15)',
                                color: '#00e676',
                                fontWeight: 700,
                              }}
                            />
                          )}
                        </Box>

                        <Typography sx={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
                          Variables ({varNames.length}): {varNames.join(', ')} • Timesteps: {ds.time_axis.count} ({ds.time_axis.resolution})
                        </Typography>
                      </Box>

                      <Box sx={{ display: 'flex', gap: 1 }}>
                        {isActive ? (
                          <Button
                            variant="outlined"
                            size="small"
                            color="secondary"
                            onClick={handleDeactivate}
                            sx={{
                              fontSize: '0.72rem',
                              borderColor: 'rgba(255,255,255,0.3)',
                              color: 'rgba(255,255,255,0.8)',
                            }}
                          >
                            Switch to Online
                          </Button>
                        ) : (
                          <Button
                            variant="contained"
                            size="small"
                            onClick={() => handleActivate(ds)}
                            startIcon={<PlayArrowIcon fontSize="small" />}
                            sx={{
                              bgcolor: '#00e5ff',
                              color: '#000000',
                              fontWeight: 600,
                              fontSize: '0.72rem',
                              '&:hover': { bgcolor: '#33ebff' },
                            }}
                          >
                            Activate
                          </Button>
                        )}
                      </Box>
                    </ListItem>
                    {idx < datasets.length - 1 && <Divider sx={{ borderColor: 'rgba(255,255,255,0.04)' }} />}
                  </Box>
                );
              })}
            </List>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ borderTop: '1px solid rgba(255,255,255,0.06)', px: 3, py: 1.5 }}>
        <Button onClick={onClose} sx={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.8rem' }}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
