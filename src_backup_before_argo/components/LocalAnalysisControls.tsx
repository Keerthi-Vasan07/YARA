import { Alert, Box, Button, FormControlLabel, MenuItem, Stack, Switch, TextField, Typography } from '@mui/material';
import { HexColorPicker } from 'react-colorful';
import { AnalysisOptions } from '../types/dataset';
import { analysisError, analysisUnits, defaultAnalysis, defaultStops, gradientCss } from '../utils/gradientColormap';
import { GradientStopEditor } from './GradientStopEditor';

export interface LocalAnalysisControlsProps {
  value: AnalysisOptions;
  onChange: (value: AnalysisOptions) => void;
  gridEnabled: boolean;
  onGridChange: (value: boolean) => void;
  units?: string;
  bottomOffset?: number;
}

export function LocalAnalysisControls({ value, onChange, gridEnabled, onGridChange, units, bottomOffset = 130 }: LocalAnalysisControlsProps) {
  const error = analysisError(value);
  const unit = value.mode === 'none' ? (units || 'dataset units') : analysisUnits(units);
  const numberInput = (field: 'exact_temperature' | 'tolerance' | 'range_min' | 'range_max', label: string) =>
    <TextField size="small" type="number" label={`${label} (${unit})`} value={Number.isFinite(value[field]) ? value[field] : ''}
      inputProps={{ step: 'any', ...(field === 'tolerance' ? { min: 0 } : {}) }}
      onChange={event => onChange({ ...value, [field]: event.target.value === '' ? NaN : Number(event.target.value) })} />;
  return <Box sx={{ position: 'absolute', right: 72, bottom: bottomOffset, width: 310, maxHeight: '65vh',
    overflowY: 'auto', bgcolor: 'rgba(8,12,18,0.96)', p: 2, zIndex: 1100 }}>
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">Local dataset analysis</Typography>
      <TextField select size="small" label="Analysis mode" value={value.mode}
        onChange={event => onChange({ ...value, mode: event.target.value as AnalysisOptions['mode'] })}>
        <MenuItem value="none">All values</MenuItem><MenuItem value="exact">Exact temperature</MenuItem><MenuItem value="range">Temperature range</MenuItem>
      </TextField>
      {value.mode === 'exact' && <>
        {numberInput('exact_temperature', 'Temperature')}{numberInput('tolerance', 'Tolerance ±')}
        <Typography variant="caption">Matching cell color</Typography>
        <HexColorPicker color={value.flat_color} onChange={flat_color => onChange({ ...value, flat_color })} />
      </>}
      {value.mode === 'range' && <>{numberInput('range_min', 'Minimum')}{numberInput('range_max', 'Maximum')}</>}
      {error && <Alert severity="error">{error} The last valid settings remain active.</Alert>}
      {value.mode !== 'exact' && <>
        <GradientStopEditor stops={value.stops ?? defaultStops()} onChange={stops => onChange({ ...value, stops })} />
        {value.mode === 'none' && value.stops === null && <Typography variant="caption">Existing colormap active. Edit a stop to use the custom gradient.</Typography>}
      </>}
      <Box aria-label="Active color scale" sx={{ height: 14, bgcolor: value.flat_color,
        background: value.mode === 'exact' ? value.flat_color : gradientCss(value.stops ?? defaultStops()) }} />
      {value.mode === 'range' && <Typography variant="caption">{value.range_min} → {value.range_max} {unit}</Typography>}
      <FormControlLabel control={<Switch checked={gridEnabled} onChange={(_, checked) => onGridChange(checked)} />} label="1° × 1° dataset grid" />
      <Typography variant="caption">Native 1° cell edges where available; otherwise a geographic reference grid within the dataset extent.</Typography>
      <Button onClick={() => onChange(defaultAnalysis())}>Reset analysis</Button>
    </Stack>
  </Box>;
}
