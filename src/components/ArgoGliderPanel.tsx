import { useState } from 'react';
import {
  Alert, Box, Button, Checkbox, CircularProgress, Divider,
  FormControlLabel, IconButton, Stack, Tab, Tabs, Typography
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import RefreshIcon from '@mui/icons-material/Refresh';
import type { ArgoFloat, ArgoStats, GliderPlatform } from '../api/argoGliderApi';
import { getArgoFloats, getArgoStats, getGliderLoadResult } from '../api/argoGliderApi';

interface Props {
  open: boolean;
  onClose: () => void;
  argoFloats: ArgoFloat[];
  gliders: GliderPlatform[];
  argoVisible: boolean;
  gliderVisible: boolean;
  onArgoData: (data: ArgoFloat[]) => void;
  onGliderData: (data: GliderPlatform[]) => void;
  onArgoVisible: (value: boolean) => void;
  onGliderVisible: (value: boolean) => void;
  onClearArgo: () => void;
  onClearGlider: () => void;
}

export function ArgoGliderPanel({
  open, onClose, argoFloats, gliders, argoVisible, gliderVisible,
  onArgoData, onGliderData, onArgoVisible, onGliderVisible,
  onClearArgo, onClearGlider
}: Props) {
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState<'argo' | 'glider' | null>(null);
  const [error, setError] = useState('');
  const [stats, setStats] = useState<ArgoStats | null>(null);

  if (!open) return null;

  const loadArgo = async () => {
    setLoading('argo'); setError('');
    try {
      const [data, s] = await Promise.all([getArgoFloats(), getArgoStats()]);
      onArgoData(data); setStats(s); onArgoVisible(true);
    } catch (e) { setError(`Unable to load Argo data from source. ${String(e)}`); }
    finally { setLoading(null); }
  };

  const loadGlider = async () => {
    setLoading('glider'); setError('');
    try {
      const { gliders: data, statuses } = await getGliderLoadResult();
      if (data.length === 0) {
        const failure = statuses.find(
          (s): s is Record<string, unknown> =>
            !!s && typeof s === 'object' && 'error' in (s as Record<string, unknown>)
        );
        if (failure) {
          setError(`Unable to load Glider data from source. ${String(failure.error)}`);
        }
      }
      onGliderData(data); onGliderVisible(true);
    } catch (e) { setError(`Unable to load Glider data from source. ${String(e)}`); }
    finally { setLoading(null); }
  };

  return (
    <Box sx={{
      position: 'absolute', top: 64, right: 12, width: 340, maxHeight: 'calc(100vh - 140px)',
      overflow: 'auto', zIndex: 1100, p: 1.5, bgcolor: 'rgba(8,12,18,0.94)',
      backdropFilter: 'blur(16px)', border: '1px solid rgba(110,242,252,0.25)',
      boxShadow: '0 12px 40px rgba(0,0,0,.5)', color: 'white'
    }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle1" fontWeight={700}>Argo & Glider</Typography>
        <IconButton size="small" onClick={onClose} sx={{ color: 'white' }}><CloseIcon fontSize="small"/></IconButton>
      </Stack>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="fullWidth" sx={{ minHeight: 36 }}>
        <Tab label="Argo" sx={{ minHeight: 36 }} />
        <Tab label="Glider" sx={{ minHeight: 36 }} />
      </Tabs>
      <Divider sx={{ my: 1, borderColor: 'rgba(255,255,255,.12)' }} />
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}

      {tab === 0 ? (
        <Stack spacing={1}>
          <Stack direction="row" spacing={1}>
            <Button fullWidth variant="contained" onClick={loadArgo} disabled={loading !== null}>
              {loading === 'argo' ? <CircularProgress size={18}/> : 'Load Argo'}
            </Button>
            <IconButton onClick={loadArgo} disabled={loading !== null} sx={{ color: 'white' }}><RefreshIcon/></IconButton>
          </Stack>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <FormControlLabel control={<Checkbox checked={argoVisible} onChange={e => onArgoVisible(e.target.checked)} />} label="Show Argo" />
            <Button size="small" onClick={() => { onClearArgo(); setStats(null); }} disabled={argoFloats.length === 0}>Clear</Button>
          </Stack>
          <Typography variant="caption">Platforms loaded: {argoFloats.length}</Typography>
          <Typography variant="caption">Observations: {stats?.observation_count ?? argoFloats.reduce((n,f) => n + f.observations.length, 0)}</Typography>
          {stats?.latest_time && <Typography variant="caption">Latest: {stats.latest_time}</Typography>}
          {argoFloats.slice(0, 30).map(f => (
            <Box key={f.id} sx={{ p: .8, borderRadius: 1, bgcolor: 'rgba(255,255,255,.04)' }}>
              <Typography variant="body2">{f.id}</Typography>
              <Typography variant="caption" sx={{ opacity: .65 }}>{f.observations.length} observations</Typography>
            </Box>
          ))}
          {argoFloats.length > 30 && <Typography variant="caption">Showing first 30 platforms.</Typography>}
        </Stack>
      ) : (
        <Stack spacing={1}>
          <Button fullWidth variant="contained" onClick={loadGlider} disabled={loading !== null}>
            {loading === 'glider' ? <CircularProgress size={18}/> : 'Load Glider'}
          </Button>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <FormControlLabel control={<Checkbox checked={gliderVisible} onChange={e => onGliderVisible(e.target.checked)} />} label="Show Glider" />
            <Button size="small" onClick={onClearGlider} disabled={gliders.length === 0}>Clear</Button>
          </Stack>
          <Typography variant="caption">Platforms loaded: {gliders.length}</Typography>
          {gliders.slice(0, 30).map(g => (
            <Box key={g.id} sx={{ p: .8, borderRadius: 1, bgcolor: 'rgba(255,255,255,.04)' }}>
              <Typography variant="body2">{g.id}</Typography>
              <Typography variant="caption" sx={{ opacity: .65 }}>{g.points.length} trajectory points</Typography>
            </Box>
          ))}
          {gliders.length > 30 && <Typography variant="caption">Showing first 30 platforms.</Typography>}
        </Stack>
      )}
    </Box>
  );
}
