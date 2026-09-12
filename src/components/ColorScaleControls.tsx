/**
 * ColorScaleControls - User-adjustable SST color scale settings
 * Appears as a floating panel near the map controls
 */

import { useState } from 'react';
import {
  Box,
  Typography,
  Slider,
  Stack,
  IconButton,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Switch,
  FormControlLabel,
  Divider,
} from '@mui/material';
import { RestartAlt, FilterAlt } from '@mui/icons-material';
import type { FilterMode, GradientStop } from '../types/dataset';
import { GradientStopEditor } from './GradientStopEditor';
import { DEFAULT_GRADIENT_STOPS } from '../utils/gradientColormap';

// Available colormaps
const COLORMAPS = [
  { id: 'thermal', label: 'Thermal', gradient: 'linear-gradient(90deg, #0a1929, #1565c0, #00acc1, #66bb6a, #cddc39, #ff9800, #f44336)' },
  { id: 'viridis', label: 'Viridis', gradient: 'linear-gradient(90deg, #440154, #3b528b, #21918c, #5ec962, #fde725)' },
  { id: 'plasma', label: 'Plasma', gradient: 'linear-gradient(90deg, #0d0887, #7e03a8, #cc4778, #f89540, #f0f921)' },
  { id: 'coolwarm', label: 'Cool-Warm', gradient: 'linear-gradient(90deg, #3b4cc0, #7092d0, #c9d7e9, #f0cdba, #d67163, #b40426)' },
];

const DEFAULT_MIN = -2;
const DEFAULT_MAX = 35;

// Shared numeric-input styling (matches the threshold-mask inputs below)
const inputSx = {
  width: '100%',
  p: 0.5,
  bgcolor: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 0.5,
  color: 'rgba(255,255,255,0.85)',
  fontSize: '0.7rem',
  fontFamily: 'monospace',
  textAlign: 'center' as const,
  '&:focus': { outline: 'none', borderColor: '#6ef2fc' },
  '&::placeholder': { color: 'rgba(255,255,255,0.25)' },
};

// Preset threshold filters
const THRESHOLD_PRESETS = [
  { label: 'Marine Heatwave', min: 28, max: null, description: 'SST ≥ 28°C' },
  { label: 'Cold Water', min: null, max: 5, description: 'SST ≤ 5°C' },
  { label: 'Optimal Fish', min: 15, max: 25, description: '15-25°C range' },
  { label: 'Coral Bleaching', min: 29, max: null, description: 'SST ≥ 29°C' },
];

interface ColorScaleControlsProps {
  minTemp: number;
  maxTemp: number;
  colormap: string;
  onMinTempChange: (value: number) => void;
  onMaxTempChange: (value: number) => void;
  onColormapChange: (colormap: string) => void;
  bottomOffset?: number;
  // Threshold masking props
  thresholdEnabled?: boolean;
  thresholdMin?: number | null;
  thresholdMax?: number | null;
  onThresholdEnabledChange?: (enabled: boolean) => void;
  onThresholdMinChange?: (value: number | null) => void;
  onThresholdMaxChange?: (value: number | null) => void;
  // Local-dataset temperature analysis (exact/range filtering + custom gradient).
  // Only rendered when a local dataset is active.
  isLocalDataset?: boolean;
  analysisMode?: FilterMode;
  onAnalysisModeChange?: (mode: FilterMode) => void;
  exactTemperature?: number | null;
  onExactTemperatureChange?: (value: number | null) => void;
  exactTolerance?: number;
  onExactToleranceChange?: (value: number) => void;
  rangeMin?: number | null;
  onRangeMinChange?: (value: number | null) => void;
  rangeMax?: number | null;
  onRangeMaxChange?: (value: number | null) => void;
  gradientStops?: GradientStop[];
  onGradientStopsChange?: (stops: GradientStop[]) => void;
  matchingCellsInfo?: { matching: number; total: number } | null;
  gridEnabled?: boolean;
  onGridEnabledChange?: (enabled: boolean) => void;
}

export function ColorScaleControls({
  minTemp,
  maxTemp,
  colormap,
  onMinTempChange,
  onMaxTempChange,
  onColormapChange,
  bottomOffset = 220,
  thresholdEnabled = false,
  thresholdMin = null,
  thresholdMax = null,
  onThresholdEnabledChange,
  onThresholdMinChange,
  onThresholdMaxChange,
  isLocalDataset = false,
  analysisMode = 'none',
  onAnalysisModeChange,
  exactTemperature = null,
  onExactTemperatureChange,
  exactTolerance = 0.5,
  onExactToleranceChange,
  rangeMin = null,
  onRangeMinChange,
  rangeMax = null,
  onRangeMaxChange,
  gradientStops = DEFAULT_GRADIENT_STOPS,
  onGradientStopsChange,
  matchingCellsInfo = null,
  gridEnabled = false,
  onGridEnabledChange,
}: ColorScaleControlsProps) {
  const [_showThresholds, _setShowThresholds] = useState(false);
  const [useCustomGradient, setUseCustomGradient] = useState(false);

  const handleReset = () => {
    onMinTempChange(DEFAULT_MIN);
    onMaxTempChange(DEFAULT_MAX);
    onColormapChange('thermal');
    onThresholdEnabledChange?.(false);
    onThresholdMinChange?.(null);
    onThresholdMaxChange?.(null);
    onAnalysisModeChange?.('none');
    onExactTemperatureChange?.(null);
    onRangeMinChange?.(null);
    onRangeMaxChange?.(null);
    onGradientStopsChange?.(DEFAULT_GRADIENT_STOPS.map((s) => ({ ...s })));
  };

  const rangeInvalid = rangeMin !== null && rangeMax !== null && rangeMin > rangeMax;

  const handlePresetClick = (preset: typeof THRESHOLD_PRESETS[0]) => {
    onThresholdMinChange?.(preset.min);
    onThresholdMaxChange?.(preset.max);
    onThresholdEnabledChange?.(true);
  };

  const currentColormap = COLORMAPS.find(c => c.id === colormap) || COLORMAPS[0];

  return (
    <Box
      sx={{
        position: 'absolute',
        bottom: bottomOffset + 8,
        right: 72,
        bgcolor: 'rgba(8, 12, 18, 0.90)',
        backdropFilter: 'blur(12px)',
        borderRadius: 0,
        border: '1px solid rgba(255,255,255,0.08)',
        overflow: 'hidden',
        zIndex: 100,
        width: 260,
      }}
    >
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 1.5, py: 1, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.75rem', fontWeight: 600 }}>
          Color Scale
        </Typography>
        <Tooltip title="Reset to defaults" arrow>
          <IconButton size="small" onClick={handleReset} sx={{ p: 0.25 }}>
            <RestartAlt sx={{ fontSize: 14, color: 'rgba(255,255,255,0.4)' }} />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* Controls */}
      <Box sx={{ p: 1.5, pt: 1 }}>
        <Stack spacing={1.5}>
          {/* Temperature range slider */}
          <Box>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.65rem', mb: 0.75, display: 'block' }}>
              Temperature Range
            </Typography>
            
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Typography
                sx={{
                  color: 'rgba(255,255,255,0.8)',
                  fontSize: '0.75rem',
                  fontFamily: '"JetBrains Mono", monospace',
                  minWidth: 40,
                }}
              >
                {minTemp}°C
              </Typography>
              <Slider
                value={[minTemp, maxTemp]}
                min={-5}
                max={40}
                onChange={(_, value) => {
                  const [min, max] = value as number[];
                  onMinTempChange(min);
                  onMaxTempChange(max);
                }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => `${v}°C`}
                sx={{
                  flex: 1,
                  height: 6,
                  '& .MuiSlider-track': {
                    background: currentColormap.gradient,
                    border: 'none',
                  },
                  '& .MuiSlider-rail': {
                    bgcolor: 'rgba(255,255,255,0.1)',
                  },
                  '& .MuiSlider-thumb': {
                    width: 14,
                    height: 14,
                    bgcolor: '#fff',
                    '&:hover': {
                      boxShadow: '0 0 6px rgba(255,255,255,0.5)',
                    },
                  },
                  '& .MuiSlider-valueLabel': {
                    bgcolor: 'rgba(8, 12, 18, 0.95)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 0.5,
                    fontSize: '0.65rem',
                  },
                }}
              />
              <Typography
                sx={{
                  color: 'rgba(255,255,255,0.8)',
                  fontSize: '0.75rem',
                  fontFamily: '"JetBrains Mono", monospace',
                  minWidth: 40,
                  textAlign: 'right',
                }}
              >
                {maxTemp}°C
              </Typography>
            </Stack>
          </Box>

          {/* Colormap selection */}
          <Box>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem', mb: 0.5, display: 'block' }}>
              Colormap
            </Typography>
            <ToggleButtonGroup
              value={colormap}
              exclusive
              onChange={(_, value) => value && onColormapChange(value)}
              size="small"
              sx={{
                display: 'flex',
                gap: 0.5,
                '& .MuiToggleButton-root': {
                  flex: 1,
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '0 !important',
                  p: 0.5,
                  '&.Mui-selected': {
                    bgcolor: 'rgba(110, 242, 252, 0.1)',
                    borderColor: 'rgba(110, 242, 252, 0.3)',
                  },
                  '&:hover': {
                    bgcolor: 'rgba(255,255,255,0.05)',
                  },
                },
              }}
            >
              {COLORMAPS.map((cm) => (
                <ToggleButton key={cm.id} value={cm.id}>
                  <Tooltip title={cm.label} arrow>
                    <Box
                      sx={{
                        width: '100%',
                        height: 8,
                        borderRadius: 0.25,
                        background: cm.gradient,
                      }}
                    />
                  </Tooltip>
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>

          {/* Custom gradient toggle + editor */}
          <Box>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem' }}>
                Use custom gradient instead of preset
              </Typography>
              <Switch
                size="small"
                checked={useCustomGradient}
                onChange={(e) => setUseCustomGradient(e.target.checked)}
              />
            </Stack>
            {useCustomGradient && onGradientStopsChange && (
              <Box sx={{ mt: 1 }}>
                <GradientStopEditor
                  stops={gradientStops}
                  onChange={onGradientStopsChange}
                  minLabel={`${minTemp}°C`}
                  maxLabel={`${maxTemp}°C`}
                />
              </Box>
            )}
          </Box>

          {/* Local Dataset Temperature Analysis (Exact / Range modes) */}
          {isLocalDataset && onAnalysisModeChange && (
            <>
              <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', my: 0.5 }} />
              <Box>
                <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.65rem', mb: 0.75, display: 'block' }}>
                  Temperature Analysis
                </Typography>

                {onGridEnabledChange && (
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.65rem' }}>
                      Show 1° Grid
                    </Typography>
                    <Switch
                      size="small"
                      checked={gridEnabled}
                      onChange={(e) => onGridEnabledChange(e.target.checked)}
                    />
                  </Stack>
                )}

                <ToggleButtonGroup
                  value={analysisMode}
                  exclusive
                  onChange={(_, value) => value && onAnalysisModeChange(value)}
                  size="small"
                  sx={{
                    display: 'flex',
                    gap: 0.5,
                    mb: 1,
                    '& .MuiToggleButton-root': {
                      flex: 1,
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '0 !important',
                      py: 0.25,
                      fontSize: '0.6rem',
                      color: 'rgba(255,255,255,0.6)',
                      textTransform: 'none',
                      '&.Mui-selected': {
                        bgcolor: 'rgba(110, 242, 252, 0.1)',
                        borderColor: 'rgba(110, 242, 252, 0.3)',
                        color: '#6ef2fc',
                      },
                    },
                  }}
                >
                  <ToggleButton value="none">None</ToggleButton>
                  <ToggleButton value="exact">Exact</ToggleButton>
                  <ToggleButton value="range">Range</ToggleButton>
                </ToggleButtonGroup>

                {analysisMode === 'exact' && (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Target (°C)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.1"
                          value={exactTemperature ?? ''}
                          placeholder="—"
                          onChange={(e) => {
                            const val = e.target.value;
                            onExactTemperatureChange?.(val === '' ? null : parseFloat(val));
                          }}
                          sx={inputSx}
                        />
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Tolerance (±°C)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.1"
                          min="0"
                          value={exactTolerance}
                          onChange={(e) => onExactToleranceChange?.(parseFloat(e.target.value) || 0)}
                          sx={inputSx}
                        />
                      </Box>
                    </Stack>
                    {matchingCellsInfo && (
                      <Typography variant="caption" sx={{ color: matchingCellsInfo.matching === 0 ? '#ff8a65' : 'rgba(255,255,255,0.5)', fontSize: '0.6rem' }}>
                        {matchingCellsInfo.matching === 0
                          ? `No dataset values found near ${exactTemperature}°C.`
                          : `${matchingCellsInfo.matching.toLocaleString()} matching cells`}
                      </Typography>
                    )}
                  </Stack>
                )}

                {analysisMode === 'range' && (
                  <Stack spacing={1}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Min (°C)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.1"
                          value={rangeMin ?? ''}
                          placeholder="—"
                          onChange={(e) => {
                            const val = e.target.value;
                            onRangeMinChange?.(val === '' ? null : parseFloat(val));
                          }}
                          sx={inputSx}
                        />
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Max (°C)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.1"
                          value={rangeMax ?? ''}
                          placeholder="—"
                          onChange={(e) => {
                            const val = e.target.value;
                            onRangeMaxChange?.(val === '' ? null : parseFloat(val));
                          }}
                          sx={inputSx}
                        />
                      </Box>
                    </Stack>
                    {rangeInvalid && (
                      <Typography variant="caption" sx={{ color: '#ff8a65', fontSize: '0.6rem' }}>
                        Min must be less than or equal to Max.
                      </Typography>
                    )}
                    {!rangeInvalid && matchingCellsInfo && (
                      <Typography variant="caption" sx={{ color: matchingCellsInfo.matching === 0 ? '#ff8a65' : 'rgba(255,255,255,0.5)', fontSize: '0.6rem' }}>
                        {matchingCellsInfo.matching === 0
                          ? `No dataset values found in ${rangeMin}–${rangeMax}°C.`
                          : `${matchingCellsInfo.matching.toLocaleString()} matching cells`}
                      </Typography>
                    )}
                  </Stack>
                )}
              </Box>
            </>
          )}

          {/* Threshold Masking Section */}
          {onThresholdEnabledChange && (
            <>
              <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', my: 0.5 }} />
              
              <Box>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <FilterAlt sx={{ fontSize: 14, color: thresholdEnabled ? '#FFB347' : 'rgba(255,255,255,0.4)' }} />
                    <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.65rem' }}>
                      Threshold Mask
                    </Typography>
                  </Stack>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={thresholdEnabled}
                        onChange={(e) => onThresholdEnabledChange(e.target.checked)}
                        sx={{
                          '& .MuiSwitch-switchBase.Mui-checked': { color: '#FFB347' },
                          '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#FFB347' },
                        }}
                      />
                    }
                    label=""
                    sx={{ m: 0 }}
                  />
                </Stack>
                
                {thresholdEnabled && (
                  <Box sx={{ mt: 1 }}>
                    {/* Preset buttons */}
                    <Stack direction="row" flexWrap="wrap" gap={0.5} sx={{ mb: 1 }}>
                      {THRESHOLD_PRESETS.map((preset) => (
                        <Tooltip key={preset.label} title={preset.description} arrow>
                          <Box
                            onClick={() => handlePresetClick(preset)}
                            sx={{
                              px: 1,
                              py: 0.25,
                              fontSize: '0.6rem',
                              bgcolor: 'rgba(255,179,71,0.1)',
                              border: '1px solid rgba(255,179,71,0.2)',
                              borderRadius: 0.5,
                              color: 'rgba(255,255,255,0.7)',
                              cursor: 'pointer',
                              transition: 'all 0.15s',
                              '&:hover': {
                                bgcolor: 'rgba(255,179,71,0.2)',
                                borderColor: 'rgba(255,179,71,0.4)',
                              },
                            }}
                          >
                            {preset.label}
                          </Box>
                        </Tooltip>
                      ))}
                    </Stack>
                    
                    {/* Custom threshold inputs */}
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Min (≥)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.5"
                          value={thresholdMin ?? ''}
                          placeholder="—"
                          onChange={(e) => {
                            const val = e.target.value;
                            onThresholdMinChange?.(val === '' ? null : parseFloat(val));
                          }}
                          sx={{
                            width: '100%',
                            p: 0.5,
                            bgcolor: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 0.5,
                            color: 'rgba(255,255,255,0.85)',
                            fontSize: '0.7rem',
                            fontFamily: 'monospace',
                            textAlign: 'center',
                            '&:focus': { outline: 'none', borderColor: '#FFB347' },
                            '&::placeholder': { color: 'rgba(255,255,255,0.25)' },
                          }}
                        />
                      </Box>
                      <Typography sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.7rem' }}>to</Typography>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.55rem', display: 'block', mb: 0.25 }}>
                          Max (≤)
                        </Typography>
                        <Box
                          component="input"
                          type="number"
                          step="0.5"
                          value={thresholdMax ?? ''}
                          placeholder="—"
                          onChange={(e) => {
                            const val = e.target.value;
                            onThresholdMaxChange?.(val === '' ? null : parseFloat(val));
                          }}
                          sx={{
                            width: '100%',
                            p: 0.5,
                            bgcolor: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 0.5,
                            color: 'rgba(255,255,255,0.85)',
                            fontSize: '0.7rem',
                            fontFamily: 'monospace',
                            textAlign: 'center',
                            '&:focus': { outline: 'none', borderColor: '#FFB347' },
                            '&::placeholder': { color: 'rgba(255,255,255,0.25)' },
                          }}
                        />
                      </Box>
                      <Typography sx={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem' }}>°C</Typography>
                    </Stack>
                    
                    <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.5rem', display: 'block', mt: 0.75 }}>
                      Only values within range are shown. Leave empty for no limit.
                    </Typography>
                  </Box>
                )}
              </Box>
            </>
          )}
        </Stack>
      </Box>
    </Box>
  );
}

export default ColorScaleControls;
