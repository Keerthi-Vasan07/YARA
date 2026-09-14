import { useRef, useState } from 'react';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
import { HexColorPicker } from 'react-colorful';
import { GradientStop } from '../types/dataset';
import { defaultStops, gradientCss, interpolateColor } from '../utils/gradientColormap';

interface Props { stops: GradientStop[]; onChange: (stops: GradientStop[]) => void }

export function GradientStopEditor({ stops, onChange }: Props) {
  const [selected, setSelected] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  const active = Math.min(selected, stops.length - 1);
  const stop = stops[active];
  const move = (index: number, position: number) => {
    if (!Number.isFinite(position)) return;
    const clamped = Math.max(0, Math.min(1, position));
    if (stops.some((s, i) => i !== index && Math.abs(s.position - clamped) < 0.001)) return;
    onChange(stops.map((s, i) => i === index ? { ...s, position: clamped } : s));
  };
  const fromX = (x: number) => {
    const rect = bar.current?.getBoundingClientRect();
    return rect ? Math.max(0, Math.min(1, (x - rect.left) / rect.width)) : 0.5;
  };
  const add = (position: number) => {
    if (stops.length >= 32 || stops.some(s => Math.abs(s.position - position) < 0.001)) return;
    onChange([...stops, { position, color: interpolateColor(stops, position) }]);
    setSelected(stops.length);
    setPickerOpen(true);
  };
  const addInGap = () => {
    const positions = [0, ...stops.map(s => s.position).sort((a, b) => a - b), 1];
    let gap = [0, 0];
    for (let i = 1; i < positions.length; i++) {
      if (positions[i] - positions[i - 1] > gap[1] - gap[0]) gap = [positions[i - 1], positions[i]];
    }
    add((gap[0] + gap[1]) / 2);
  };
  return <Stack spacing={1}>
    <Typography variant="caption">Gradient — double-click bar to add a stop</Typography>
    <Box ref={bar} onDoubleClick={event => add(fromX(event.clientX))}
      sx={{ height: 30, position: 'relative', background: gradientCss(stops), mx: 1, mb: 2, touchAction: 'none' }}>
      {stops.map((s, index) => <button key={index} type="button" aria-label={`Gradient stop ${index + 1}`}
        role="slider" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.position * 100)}
        aria-valuetext={`${Math.round(s.position * 100)} percent, ${s.color}`}
        style={{ position: 'absolute', left: `${s.position * 100}%`, top: 21, transform: 'translateX(-50%)',
          width: 16, height: 20, background: s.color, border: index === active ? '3px solid white' : '2px solid #888', cursor: 'ew-resize', touchAction: 'none' }}
        onDoubleClick={event => event.stopPropagation()}
        onClick={() => { setSelected(index); setPickerOpen(true); }}
        onPointerDown={event => { setSelected(index); event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) move(index, fromX(event.clientX)); }}
        onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)}
        onKeyDown={event => {
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault(); move(index, s.position + (event.key === 'ArrowRight' ? 0.01 : -0.01));
          }
        }} />)}
    </Box>
    <TextField size="small" label="Stop position (%)" type="number" value={Math.round(stop.position * 10000) / 100}
      inputProps={{ min: 0, max: 100, step: 0.1 }} onChange={event => move(active, Number(event.target.value) / 100)} />
    <Button onClick={() => setPickerOpen(!pickerOpen)} size="small">Edit color {stop.color}</Button>
    {pickerOpen && <HexColorPicker color={stop.color} onChange={color => onChange(stops.map((s, i) => i === active ? { ...s, color } : s))} />}
    <Stack direction="row" flexWrap="wrap">
      <Button size="small" disabled={stops.length >= 32} onClick={addInGap}>Add stop</Button>
      <Button size="small" disabled={stops.length <= 2} onClick={() => { onChange(stops.filter((_, i) => i !== active)); setSelected(0); }}>Delete</Button>
      <Button size="small" onClick={() => onChange(stops.map(s => ({ ...s, position: 1 - s.position })))}>Reverse</Button>
      <Button size="small" onClick={() => { onChange(defaultStops()); setSelected(0); }}>Reset</Button>
    </Stack>
  </Stack>;
}
