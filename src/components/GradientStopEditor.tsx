/**
 * Photoshop-like gradient stop editor: a horizontal bar with draggable color stops.
 * Click a stop to open a color picker; click empty bar space to add a stop;
 * drag a stop to reposition it; delete/reverse/reset via toolbar buttons.
 */
import { useCallback, useRef, useState } from 'react';
import { Box, IconButton, Stack, Tooltip, Typography, Popover } from '@mui/material';
import { Delete, SwapHoriz, RestartAlt } from '@mui/icons-material';
import { HexColorPicker } from 'react-colorful';
import type { GradientStop } from '../types/dataset';
import {
  DEFAULT_GRADIENT_STOPS,
  gradientCssString,
  interpolateGradient,
  reverseStops,
  sortAndValidateStops,
} from '../utils/gradientColormap';

interface GradientStopEditorProps {
  stops: GradientStop[];
  onChange: (stops: GradientStop[]) => void;
  minLabel?: string;
  maxLabel?: string;
}

function toHex(color: string): string {
  // react-colorful's HexColorPicker requires a hex string; convert rgba(...)/named colors via canvas trick.
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(color)) return color;
  const el = document.createElement('div');
  el.style.color = color;
  document.body.appendChild(el);
  const computed = getComputedStyle(el).color;
  document.body.removeChild(el);
  const match = computed.match(/rgba?\(([^)]+)\)/);
  if (!match) return '#ffffff';
  const [r, g, b] = match[1].split(',').map((p) => parseInt(p.trim(), 10));
  const toHexPart = (v: number) => v.toString(16).padStart(2, '0');
  return `#${toHexPart(r)}${toHexPart(g)}${toHexPart(b)}`;
}

export function GradientStopEditor({ stops, onChange, minLabel, maxLabel }: GradientStopEditorProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [pickerAnchor, setPickerAnchor] = useState<HTMLElement | null>(null);
  const draggingIndexRef = useRef<number | null>(null);

  const sorted = sortAndValidateStops(stops);

  const positionFromClientX = useCallback((clientX: number): number => {
    const rect = barRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  }, []);

  const handleBarClick = (e: React.MouseEvent) => {
    if (draggingIndexRef.current !== null) return;
    const pos = positionFromClientX(e.clientX);
    const color = interpolateGradient(sorted, pos);
    const next = sortAndValidateStops([...sorted, { position: pos, color }]);
    onChange(next);
  };

  const handleStopMouseDown = (index: number) => (e: React.MouseEvent) => {
    e.stopPropagation();
    draggingIndexRef.current = index;

    const handleMove = (moveEvent: MouseEvent) => {
      const pos = positionFromClientX(moveEvent.clientX);
      const next = sorted.map((s, i) => (i === index ? { ...s, position: pos } : s));
      onChange(sortAndValidateStops(next));
    };
    const handleUp = () => {
      draggingIndexRef.current = null;
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  };

  const handleStopClick = (index: number) => (e: React.MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    setSelectedIndex(index);
    setPickerAnchor(e.currentTarget);
  };

  const handleColorChange = (hex: string) => {
    if (selectedIndex === null) return;
    const next = sorted.map((s, i) => (i === selectedIndex ? { ...s, color: hex } : s));
    onChange(sortAndValidateStops(next));
  };

  const handleDeleteSelected = () => {
    if (selectedIndex === null || sorted.length <= 2) return;
    const next = sorted.filter((_, i) => i !== selectedIndex);
    onChange(sortAndValidateStops(next));
    setSelectedIndex(null);
    setPickerAnchor(null);
  };

  const handleReverse = () => onChange(reverseStops(sorted));
  const handleReset = () => onChange(DEFAULT_GRADIENT_STOPS.map((s) => ({ ...s })));

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem' }}>
          Custom Gradient
        </Typography>
        <Stack direction="row" spacing={0.25}>
          <Tooltip title="Reverse gradient" arrow>
            <IconButton size="small" onClick={handleReverse} sx={{ p: 0.25 }}>
              <SwapHoriz sx={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Reset to default" arrow>
            <IconButton size="small" onClick={handleReset} sx={{ p: 0.25 }}>
              <RestartAlt sx={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }} />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete selected stop" arrow>
            <span>
              <IconButton
                size="small"
                onClick={handleDeleteSelected}
                disabled={selectedIndex === null || sorted.length <= 2}
                sx={{ p: 0.25 }}
              >
                <Delete sx={{ fontSize: 14, color: 'rgba(255,255,255,0.5)' }} />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.25 }}>
        <Typography sx={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
          {minLabel}
        </Typography>
        <Typography sx={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
          {maxLabel}
        </Typography>
      </Stack>

      <Box
        ref={barRef}
        onClick={handleBarClick}
        sx={{
          position: 'relative',
          height: 24,
          borderRadius: 0.5,
          border: '1px solid rgba(255,255,255,0.15)',
          background: gradientCssString(sorted),
          cursor: 'copy',
          mb: 1.5,
        }}
      >
        {sorted.map((stop, i) => (
          <Tooltip key={i} title={`${(stop.position * 100).toFixed(0)}% — ${stop.color}`} arrow>
            <Box
              onMouseDown={handleStopMouseDown(i)}
              onClick={handleStopClick(i)}
              sx={{
                position: 'absolute',
                top: '100%',
                left: `${stop.position * 100}%`,
                transform: 'translate(-50%, 2px)',
                width: 12,
                height: 12,
                borderRadius: '2px',
                bgcolor: stop.color,
                border: selectedIndex === i ? '2px solid #fff' : '1px solid rgba(255,255,255,0.6)',
                cursor: 'ew-resize',
                boxShadow: '0 0 3px rgba(0,0,0,0.6)',
              }}
            />
          </Tooltip>
        ))}
      </Box>

      <Popover
        open={Boolean(pickerAnchor) && selectedIndex !== null}
        anchorEl={pickerAnchor}
        onClose={() => setPickerAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Box sx={{ p: 1, bgcolor: '#141a22' }}>
          {selectedIndex !== null && (
            <HexColorPicker color={toHex(sorted[selectedIndex].color)} onChange={handleColorChange} />
          )}
        </Box>
      </Popover>
    </Box>
  );
}

export default GradientStopEditor;
