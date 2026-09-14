/**
 * TimeSeriesDialog - Shows time series chart for a location
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Box,
  Typography,
  IconButton,
  CircularProgress,
  Chip,
  Table,
  TableBody,
  TableRow,
  TableCell,
  Button,
} from '@mui/material';
import { Close, MyLocation, TrendingUp, TrendingDown } from '@mui/icons-material';
import { fetchZarrTimeseries, ZarrTimeseriesResponse, TimeseriesPoint } from '../api/sstApi';

interface TimeSeriesDialogProps {
  open: boolean;
  onClose: () => void;
  location: { lon: number; lat: number } | null;
  selectedDate: string;
}

// Simple SVG line chart with optional percentile bands
function MiniChart({ 
  data, 
  width = 400, 
  height = 150,
  percentiles,
  showPercentileBand = true,
}: { 
  data: TimeseriesPoint[]; 
  width?: number; 
  height?: number;
  percentiles?: { p10: number | null; p50: number | null; p90: number | null };
  showPercentileBand?: boolean;
}) {
  if (data.length === 0) return null;

  const padding = { top: 20, right: 20, bottom: 40, left: 50 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const values = data.map((d) => d.value);
  
  // Include percentiles in min/max calculation if showing band
  let minVal = Math.min(...values);
  let maxVal = Math.max(...values);
  
  if (showPercentileBand && percentiles) {
    if (percentiles.p10 !== null) minVal = Math.min(minVal, percentiles.p10);
    if (percentiles.p90 !== null) maxVal = Math.max(maxVal, percentiles.p90);
  }
  
  const range = maxVal - minVal || 1;

  // Scale functions
  const xScale = (i: number) => padding.left + (i / Math.max(data.length - 1, 1)) * chartWidth;
  const yScale = (val: number) => padding.top + chartHeight - ((val - minVal) / range) * chartHeight;

  // Generate path
  const pathD = data
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(d.value)}`)
    .join(' ');

  // Y-axis ticks
  const yTicks = [minVal, (minVal + maxVal) / 2, maxVal];

  // X-axis labels (show first, middle, last dates)
  const xLabels = [
    { idx: 0, label: data[0]?.date?.slice(0, 7) || '' },
    { idx: Math.floor(data.length / 2), label: data[Math.floor(data.length / 2)]?.date?.slice(0, 7) || '' },
    { idx: data.length - 1, label: data[data.length - 1]?.date?.slice(0, 7) || '' },
  ];

  // Compute percentile band visibility
  const hasPercentileBand = showPercentileBand && percentiles && 
    percentiles.p10 !== null && percentiles.p90 !== null;
  const hasMedian = showPercentileBand && percentiles && percentiles.p50 !== null;
  const p10 = percentiles?.p10 ?? 0;
  const p50 = percentiles?.p50 ?? 0;
  const p90 = percentiles?.p90 ?? 0;

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {/* Percentile band (P10-P90 shaded area) */}
      {hasPercentileBand && (
        <rect
          x={padding.left}
          y={yScale(p90)}
          width={chartWidth}
          height={yScale(p10) - yScale(p90)}
          fill="rgba(110, 242, 252, 0.08)"
        />
      )}
      
      {/* P50 median line */}
      {hasMedian && (
        <line
          x1={padding.left}
          x2={width - padding.right}
          y1={yScale(p50)}
          y2={yScale(p50)}
          stroke="rgba(110, 242, 252, 0.3)"
          strokeDasharray="6,4"
          strokeWidth={1}
        />
      )}
      
      {/* Grid lines */}
      {yTicks.map((tick, i) => (
        <line
          key={i}
          x1={padding.left}
          x2={width - padding.right}
          y1={yScale(tick)}
          y2={yScale(tick)}
          stroke="rgba(255,255,255,0.1)"
          strokeDasharray="4,4"
        />
      ))}

      {/* Y-axis labels */}
      {yTicks.map((tick, i) => (
        <text
          key={i}
          x={padding.left - 8}
          y={yScale(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          fill="rgba(255,255,255,0.5)"
          fontSize={10}
          fontFamily="monospace"
        >
          {tick.toFixed(1)}°
        </text>
      ))}

      {/* X-axis labels */}
      {xLabels.map(({ idx, label }) => (
        <text
          key={idx}
          x={xScale(idx)}
          y={height - padding.bottom + 20}
          textAnchor="middle"
          fill="rgba(255,255,255,0.5)"
          fontSize={10}
          fontFamily="monospace"
        >
          {label}
        </text>
      ))}

      {/* Line */}
      <path d={pathD} fill="none" stroke="#6EF2FC" strokeWidth={2} />

      {/* Points */}
      {data.map((d, i) => (
        <circle key={i} cx={xScale(i)} cy={yScale(d.value)} r={3} fill="#6EF2FC" />
      ))}

      {/* Axes */}
      <line
        x1={padding.left}
        x2={padding.left}
        y1={padding.top}
        y2={height - padding.bottom}
        stroke="rgba(255,255,255,0.2)"
      />
      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={height - padding.bottom}
        y2={height - padding.bottom}
        stroke="rgba(255,255,255,0.2)"
      />
      
      {/* Percentile legend */}
      {hasPercentileBand && (
        <g>
          <text
            x={width - padding.right - 5}
            y={yScale(p90) - 3}
            textAnchor="end"
            fill="rgba(110, 242, 252, 0.5)"
            fontSize={8}
            fontFamily="monospace"
          >
            P90
          </text>
          <text
            x={width - padding.right - 5}
            y={yScale(p10) + 10}
            textAnchor="end"
            fill="rgba(110, 242, 252, 0.5)"
            fontSize={8}
            fontFamily="monospace"
          >
            P10
          </text>
        </g>
      )}
    </svg>
  );
}

export function TimeSeriesDialog({ open, onClose, location, selectedDate }: TimeSeriesDialogProps) {
  const [data, setData] = useState<ZarrTimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!location) return;
    setLoading(true);
    setError(null);
    try {
      // Use Zarr-based API for enhanced stats (climatology, percentiles, trends)
      const result = await fetchZarrTimeseries('sst', location.lon, location.lat);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, [location]);

  useEffect(() => {
    if (open && location) {
      fetchData();
    }
  }, [open, location, fetchData]);

  // Calculate stats from timeseries if not provided by API
  const stats = data?.timeseries ? {
    min: Math.min(...data.timeseries.map(d => d.value)),
    max: Math.max(...data.timeseries.map(d => d.value)),
    mean: data.climatology?.mean ?? (data.timeseries.reduce((a, b) => a + b.value, 0) / data.timeseries.length),
  } : null;

  // Use API trend if available, otherwise calculate from timeseries
  const trend = data?.trend ?? (
    data?.timeseries && data.timeseries.length > 1
      ? data.timeseries[data.timeseries.length - 1].value - data.timeseries[0].value
      : null
  );

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
            SST Time Series
          </Typography>
          {location && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
              <MyLocation sx={{ fontSize: 14, color: 'text.secondary' }} />
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                {location.lat.toFixed(2)}°, {location.lon.toFixed(2)}°
              </Typography>
            </Box>
          )}
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
            <Button size="small" onClick={fetchData} sx={{ mt: 1 }}>
              Retry
            </Button>
          </Box>
        )}

        {!location && !loading && (
          <Box sx={{ py: 4, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Click on the map to select a location for time series analysis.
            </Typography>
          </Box>
        )}

        {data && !loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Chart with percentile band */}
            <Box
              sx={{
                bgcolor: 'rgba(0,0,0,0.2)',
                border: '1px solid rgba(255,255,255,0.06)',
                p: 1,
              }}
            >
              <MiniChart 
                data={data.timeseries} 
                width={450} 
                height={180} 
                percentiles={data.percentiles || undefined}
                showPercentileBand={!!data.percentiles}
              />
            </Box>

            {/* Stats */}
            {stats && (
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <Chip
                  label={`Min: ${stats.min.toFixed(1)}°C`}
                  size="small"
                  sx={{ bgcolor: 'rgba(33, 150, 243, 0.15)', color: '#64B5F6' }}
                />
                <Chip
                  label={`Max: ${stats.max.toFixed(1)}°C`}
                  size="small"
                  sx={{ bgcolor: 'rgba(244, 67, 54, 0.15)', color: '#EF5350' }}
                />
                {stats.mean !== null && (
                  <Chip
                    label={`Mean: ${typeof stats.mean === 'number' ? stats.mean.toFixed(1) : '--'}°C`}
                    size="small"
                    sx={{ bgcolor: 'rgba(255,255,255,0.08)' }}
                  />
                )}
                {trend !== null && (
                  <Chip
                    icon={trend > 0 ? <TrendingUp sx={{ fontSize: 14 }} /> : <TrendingDown sx={{ fontSize: 14 }} />}
                    label={`Trend: ${trend > 0 ? '+' : ''}${trend.toFixed(4)}°C/yr`}
                    size="small"
                    sx={{
                      bgcolor: trend > 0 ? 'rgba(244, 67, 54, 0.15)' : 'rgba(33, 150, 243, 0.15)',
                      color: trend > 0 ? '#EF5350' : '#64B5F6',
                      '& .MuiChip-icon': { color: 'inherit' },
                    }}
                  />
                )}
              </Box>
            )}

            {/* Percentile info */}
            {data.percentiles && (data.percentiles.p10 !== null || data.percentiles.p90 !== null) && (
              <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                <Typography variant="caption" color="text.secondary" sx={{ width: '100%', mb: -1 }}>
                  Historical Percentiles
                </Typography>
                {data.percentiles.p10 !== null && (
                  <Chip
                    label={`P10: ${data.percentiles.p10.toFixed(1)}°C`}
                    size="small"
                    sx={{ bgcolor: 'rgba(110, 242, 252, 0.1)', color: 'rgba(110, 242, 252, 0.8)' }}
                  />
                )}
                {data.percentiles.p50 !== null && (
                  <Chip
                    label={`P50: ${data.percentiles.p50.toFixed(1)}°C`}
                    size="small"
                    sx={{ bgcolor: 'rgba(110, 242, 252, 0.15)', color: '#6EF2FC' }}
                  />
                )}
                {data.percentiles.p90 !== null && (
                  <Chip
                    label={`P90: ${data.percentiles.p90.toFixed(1)}°C`}
                    size="small"
                    sx={{ bgcolor: 'rgba(110, 242, 252, 0.1)', color: 'rgba(110, 242, 252, 0.8)' }}
                  />
                )}
              </Box>
            )}

            {/* Data table */}
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
                Monthly values ({data.count} records)
              </Typography>
              <Box
                sx={{
                  maxHeight: 200,
                  overflow: 'auto',
                  bgcolor: 'rgba(0,0,0,0.2)',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <Table size="small" stickyHeader>
                  <TableBody>
                    {data.timeseries.map((point, i) => (
                      <TableRow
                        key={i}
                        sx={{
                          bgcolor: point.date === selectedDate ? 'rgba(110, 242, 252, 0.1)' : 'transparent',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.04)' },
                        }}
                      >
                        <TableCell
                          sx={{
                            border: 'none',
                            py: 0.5,
                            px: 1.5,
                            fontSize: '0.75rem',
                            fontFamily: 'monospace',
                            color: 'text.secondary',
                          }}
                        >
                          {point.date}
                        </TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            border: 'none',
                            py: 0.5,
                            px: 1.5,
                            fontSize: '0.75rem',
                            fontFamily: 'monospace',
                            fontWeight: point.date === selectedDate ? 600 : 400,
                            color: point.date === selectedDate ? '#6EF2FC' : 'text.primary',
                          }}
                        >
                          {point.value.toFixed(2)}°C
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Box>

            <Box sx={{ pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.65rem' }}>
                Data source: ERA5 ARCO Monthly Reanalysis
              </Typography>
            </Box>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}
