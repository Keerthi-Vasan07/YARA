import { MenuItem, Select } from '@mui/material';
import type { OnlineDataset } from '../../api/onlineApi';

export function OnlineDatasetSelector({ datasets, value, onChange, disabled }: { datasets: OnlineDataset[]; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <Select fullWidth size="small" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    {datasets.map((dataset) => <MenuItem key={dataset.id} value={dataset.id}>{dataset.name}</MenuItem>)}
  </Select>;
}
