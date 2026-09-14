import { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { fetchOnlineDatasets, fetchOnlineMetadata, fetchOnlineTimes, type OnlineDataset, type OnlineMetadata, type OnlineTimes } from '../api/onlineApi';
import { OnlineDatasetInfo } from './online/OnlineDatasetInfo';
import { OnlineDatasetSelector } from './online/OnlineDatasetSelector';
import { OnlineTimeSelector } from './online/OnlineTimeSelector';
import { OnlineVariableSelector } from './online/OnlineVariableSelector';

export interface OnlineState {
  datasetId: string;
  variable: string;
  date: string;
  resolvedDate: string | null;
  availableDates: string[];
  metadata: OnlineMetadata | null;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error: string | null;
  registry: OnlineDataset[];
}

export function OnlineControls({ state, onChange, onApply, frameLoading = false }: { state: OnlineState; onChange: (next: Partial<OnlineState>) => void; onApply: (datasetId: string, variable: string, time: string) => void; frameLoading?: boolean }) {
  const [draftDataset, setDraftDataset] = useState(state.datasetId);
  const [draftVariable, setDraftVariable] = useState(state.variable);
  const [draftTime, setDraftTime] = useState(state.date);
  const [times, setTimes] = useState<OnlineTimes | null>(null);
  const [loading, setLoading] = useState(false);
  const selected = useMemo(() => state.registry.find((dataset) => dataset.id === draftDataset), [state.registry, draftDataset]);
  const scalarVariables = selected?.variables.filter((variable) => variable.type === 'scalar') || [];

  useEffect(() => { fetchOnlineDatasets().then(({ datasets }) => { const id = state.datasetId || datasets[0]?.id || ''; setDraftDataset(id); onChange({ registry: datasets, datasetId: id, status: id ? 'loading' : 'error', error: id ? null : 'No online datasets are registered.' }); }).catch((error) => onChange({ status: 'error', error: String(error) })); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!draftDataset) return;
    let active = true; setLoading(true);
    Promise.all([fetchOnlineMetadata(draftDataset), fetchOnlineTimes(draftDataset)]).then(([metadata, datasetTimes]) => {
      if (!active) return;
      const vars = metadata.inspection.variables.filter((variable) => variable.type === 'scalar');
      const variable = vars.some((item) => item.id === draftVariable) ? draftVariable : vars[0]?.id || '';
      const timestamp = datasetTimes.timestamps.includes(draftTime) ? draftTime : datasetTimes.timestamps[datasetTimes.timestamps.length - 1] || '';
      setDraftVariable(variable); setDraftTime(timestamp); setTimes(datasetTimes);
      onChange({ datasetId: draftDataset, variable, date: timestamp, resolvedDate: timestamp, availableDates: datasetTimes.timestamps, metadata, status: 'ready', error: null });
    }).catch((error) => active && onChange({ status: 'error', error: String(error) })).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [draftDataset]); // eslint-disable-line react-hooks/exhaustive-deps

  const busy = loading || frameLoading;
  return <Box sx={{ position: 'absolute', top: 80, left: 16, zIndex: 1000, width: 330, p: 2, bgcolor: 'rgba(6,10,18,.9)', border: '1px solid rgba(110,242,252,.35)', boxShadow: '0 8px 32px rgba(0,0,0,.45)' }}>
    <Typography variant="overline" sx={{ color: '#6EF2FC' }}>Online ocean data</Typography>
    <Stack spacing={1}>
      <Typography variant="caption">Dataset</Typography><OnlineDatasetSelector datasets={state.registry} value={draftDataset} onChange={setDraftDataset} disabled={busy} />
      <Typography variant="caption">Variable</Typography><OnlineVariableSelector variables={scalarVariables} value={draftVariable} onChange={setDraftVariable} disabled={busy || !scalarVariables.length} />
      <Typography variant="caption">Date and time (UTC)</Typography><OnlineTimeSelector timestamps={times?.timestamps || []} value={draftTime} onChange={setDraftTime} disabled={busy} />
      <OnlineDatasetInfo dataset={selected} times={times} />
      {state.error && <Alert severity="error">{state.error}</Alert>}
      <Button variant="contained" disabled={busy || !draftDataset || !draftVariable || !draftTime} onClick={() => onApply(draftDataset, draftVariable, draftTime)}>{busy ? <CircularProgress size={18} /> : 'Load data'}</Button>
    </Stack>
  </Box>;
}
