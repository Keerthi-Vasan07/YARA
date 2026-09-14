import { useEffect, useState } from 'react';
import { Alert, Box } from '@mui/material';
import { FrameStats, FrameStyle } from '../types/dataset';
import { fetchLocalStats } from '../services/localDatasetApi';

export function LocalAnalysisStatus({ datasetId, variable, index, style }: {
  datasetId: string; variable: string; index: number; style: FrameStyle;
}) {
  const [stats, setStats] = useState<FrameStats | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setStats(null); setError('');
    fetchLocalStats(datasetId, variable, index, style, controller.signal).then(setStats).catch(err => {
      if (!controller.signal.aborted) setError(String(err));
    });
    return () => controller.abort();
  }, [datasetId, variable, index, style]);
  return <Box role="status" sx={{ position: 'absolute', top: 110, right: 12, zIndex: 1000, maxWidth: 350 }}>
    {error ? <Alert severity="error">{error}</Alert> : <Alert severity={stats?.message ? 'info' : 'success'}>
      {stats ? stats.message || `${stats.matching_cells.toLocaleString()} / ${stats.valid_cells.toLocaleString()} valid cells (${stats.matching_percent.toFixed(2)}%). Range: ${stats.min}–${stats.max} ${stats.units || ''}` : 'Analyzing frame…'}
    </Alert>}
  </Box>;
}
