import { MenuItem, Select, Stack, TextField } from '@mui/material';

export function OnlineTimeSelector({ timestamps, value, onChange, disabled }: { timestamps: string[]; value: string; onChange: (value: string) => void; disabled?: boolean }) {
  const dates = [...new Set(timestamps.map((timestamp) => timestamp.slice(0, 10)))];
  const date = value.slice(0, 10);
  const options = timestamps.filter((timestamp) => timestamp.startsWith(date));
  return <Stack direction="row" spacing={1}>
    <TextField type="date" size="small" value={date} disabled={disabled || !dates.length} inputProps={{ min: dates[0], max: dates[dates.length - 1] }} onChange={(event) => onChange(timestamps.find((timestamp) => timestamp.startsWith(event.target.value)) || value)} sx={{ flex: 1 }} />
    <Select size="small" value={value} disabled={disabled || !options.length} onChange={(event) => onChange(event.target.value)} sx={{ flex: 1 }}>
      {options.map((timestamp) => <MenuItem key={timestamp} value={timestamp}>{timestamp.slice(11, 16)} UTC</MenuItem>)}
    </Select>
  </Stack>;
}
