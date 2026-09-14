/**
 * LayerInfoDialog - Shows detailed metadata about a layer
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Box,
  Typography,
  IconButton,
  Table,
  TableBody,
  TableRow,
  TableCell,
  CircularProgress,
  Chip,
} from '@mui/material';
import { Close, Public, CalendarMonth, Storage, Analytics } from '@mui/icons-material';
import { fetchLayerInfo, LayerInfo } from '../api/sstApi';

interface LayerInfoDialogProps {
  open: boolean;
  onClose: () => void;
  variable: string;
  layerName: string;
}

export function LayerInfoDialog({ open, onClose, variable, layerName }: LayerInfoDialogProps) {
  const [info, setInfo] = useState<LayerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && variable) {
      setLoading(true);
      setError(null);
      fetchLayerInfo(variable)
        .then(setInfo)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    }
  }, [open, variable]);

  const formatNumber = (n: number | undefined) => {
    if (n === undefined) return '—';
    return n.toFixed(2);
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
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 0,
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1rem' }}>
            {layerName}
          </Typography>
          <Chip
            label={variable.toUpperCase()}
            size="small"
            sx={{
              mt: 0.5,
              height: 20,
              fontSize: '0.65rem',
              fontFamily: 'monospace',
              bgcolor: 'rgba(110, 242, 252, 0.15)',
              color: '#6EF2FC',
            }}
          />
        </Box>
        <IconButton onClick={onClose} size="small">
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: 1 }}>
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        )}

        {error && (
          <Box sx={{ py: 2, color: 'error.main' }}>
            <Typography variant="body2">{error}</Typography>
          </Box>
        )}

        {info && !loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Source */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Storage sx={{ fontSize: 16, color: 'text.secondary' }} />
              <Typography variant="body2" color="text.secondary">
                {info.source}
              </Typography>
            </Box>

            {/* Spatial coverage */}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Public sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  Spatial Coverage
                </Typography>
              </Box>
              <Table size="small" sx={{ '& td': { border: 'none', py: 0.25, px: 1, fontSize: '0.75rem' } }}>
                <TableBody>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary', width: 100 }}>Latitude</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>
                      {info.bounds.lat[0].toFixed(2)}° to {info.bounds.lat[1].toFixed(2)}°
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary' }}>Longitude</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>
                      {info.bounds.lon[0].toFixed(2)}° to {info.bounds.lon[1].toFixed(2)}°
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary' }}>Resolution</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>0.25° × 0.25°</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>

            {/* Temporal coverage */}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <CalendarMonth sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  Temporal Coverage
                </Typography>
              </Box>
              <Table size="small" sx={{ '& td': { border: 'none', py: 0.25, px: 1, fontSize: '0.75rem' } }}>
                <TableBody>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary', width: 100 }}>Start</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{info.time_range.start || '—'}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary' }}>End</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{info.time_range.end || '—'}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: 'text.secondary' }}>Time steps</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{info.time_range.count}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>

            {/* Statistics */}
            {info.global_stats && Object.keys(info.global_stats).length > 0 && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Analytics sx={{ fontSize: 16, color: 'primary.main' }} />
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                    Global Statistics
                  </Typography>
                </Box>
                <Table size="small" sx={{ '& td': { border: 'none', py: 0.25, px: 1, fontSize: '0.75rem' } }}>
                  <TableBody>
                    <TableRow>
                      <TableCell sx={{ color: 'text.secondary', width: 100 }}>Min</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{formatNumber(info.global_stats.min)} °C</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell sx={{ color: 'text.secondary' }}>Max</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{formatNumber(info.global_stats.max)} °C</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell sx={{ color: 'text.secondary' }}>Mean</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{formatNumber(info.global_stats.mean)} °C</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell sx={{ color: 'text.secondary' }}>Std Dev</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{formatNumber(info.global_stats.std)} °C</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Box>
            )}

            {/* Data info */}
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
                Data source: ECMWF ERA5 Reanalysis via Google Cloud ARCO
              </Typography>
            </Box>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}
