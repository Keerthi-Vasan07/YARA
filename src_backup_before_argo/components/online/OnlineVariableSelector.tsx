import { MenuItem, Select } from '@mui/material';
import type { OnlineVariable } from '../../api/onlineApi';

export function OnlineVariableSelector({ variables, value, onChange, disabled }: { variables: OnlineVariable[]; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return <Select fullWidth size="small" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    {variables.map((variable) => <MenuItem key={variable.id} value={variable.id}>{variable.name} ({variable.units})</MenuItem>)}
  </Select>;
}
