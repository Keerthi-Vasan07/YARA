/**
 * Settings Panel - Application configuration
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Switch,
  FormControlLabel,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Alert,
} from '@mui/material';
import {
  Close as CloseIcon,
  Refresh as RefreshIcon,
  Palette as PaletteIcon,
  Map as MapIcon,
  Timeline as TimelineIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';

// Color scheme - warm amber/orange accent on very dark background (matches About panel)
const ACCENT_COLOR = '#FFB347';
const BORDER_COLOR = 'rgba(255, 180, 50, 0.12)';
const BG_DARK = '#0a0a0a';
const TEXT_PRIMARY = 'rgba(255, 255, 255, 0.92)';
const TEXT_SECONDARY = 'rgba(255, 255, 255, 0.55)';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

interface SettingsState {
  colormap: string;
  colorScaleMin: number;
  colorScaleMax: number;
  timelineCollapsed: boolean;
  layerOpacity: number;
}

const DEFAULT_SETTINGS: SettingsState = {
  colormap: 'thermal',
  colorScaleMin: -2,
  colorScaleMax: 35,
  timelineCollapsed: true,
  layerOpacity: 65,
};

const COLORMAP_OPTIONS = [
  { value: 'thermal', label: 'Thermal (Ocean)', description: 'Blue to red, ideal for SST' },
  { value: 'viridis', label: 'Viridis', description: 'Perceptually uniform, colorblind safe' },
  { value: 'plasma', label: 'Plasma', description: 'Warm purple to yellow' },
  { value: 'turbo', label: 'Turbo', description: 'Rainbow with improved perceptual uniformity' },
  { value: 'inferno', label: 'Inferno', description: 'Black to yellow through red' },
];

// Helper to read current settings from localStorage
function loadSettingsFromStorage(): SettingsState {
  const colormap = localStorage.getItem('sst-colormap') || DEFAULT_SETTINGS.colormap;
  const colorScaleMin = parseFloat(localStorage.getItem('sst-color-min') || String(DEFAULT_SETTINGS.colorScaleMin));
  const colorScaleMax = parseFloat(localStorage.getItem('sst-color-max') || String(DEFAULT_SETTINGS.colorScaleMax));
  const timelineCollapsed = localStorage.getItem('timeline-collapsed') !== 'false';
  const layerOpacity = parseInt(localStorage.getItem('layer-opacity') || String(DEFAULT_SETTINGS.layerOpacity), 10);
  return { colormap, colorScaleMin, colorScaleMax, timelineCollapsed, layerOpacity };
}

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  // Load settings from existing localStorage keys (the ones that are actually used)
  const [settings, setSettings] = useState<SettingsState>(loadSettingsFromStorage);

  // Re-sync settings from localStorage when panel opens (picks up changes made elsewhere)
  useEffect(() => {
    if (open) {
      setSettings(loadSettingsFromStorage());
    }
  }, [open]);

  const [saved, setSaved] = useState(false);

  // Persist settings to actual localStorage keys that the app uses
  useEffect(() => {
    localStorage.setItem('sst-colormap', settings.colormap);
    localStorage.setItem('sst-color-min', String(settings.colorScaleMin));
    localStorage.setItem('sst-color-max', String(settings.colorScaleMax));
    localStorage.setItem('timeline-collapsed', String(settings.timelineCollapsed));
    localStorage.setItem('layer-opacity', String(settings.layerOpacity));
    // Also store as unified settings object for backup
    localStorage.setItem('app-settings', JSON.stringify(settings));
    
    // Dispatch custom event for realtime sync with Layout
    window.dispatchEvent(new CustomEvent('settings-changed', { detail: settings }));
  }, [settings]);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const handleChange = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleResetDefaults = () => {
    setSettings(DEFAULT_SETTINGS);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleClearCache = () => {
    // Clear all app-related localStorage items
    const keysToRemove = [
      'sst-colormap', 'sst-color-min', 'sst-color-max',
      'layer-visibility', 'layer-opacity', 'timeline-collapsed', 'app-settings'
    ];
    keysToRemove.forEach(key => localStorage.removeItem(key));
    // Reset state to defaults
    setSettings(DEFAULT_SETTINGS);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (!open) return null;

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Backdrop */}
      <Box
        onClick={onClose}
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
        }}
      />

      {/* Main Panel */}
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          width: '90vw',
          maxWidth: 680,
          maxHeight: '90vh',
          backgroundColor: BG_DARK,
          borderRadius: 0,
          border: `1px solid ${BORDER_COLOR}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 3,
            py: 2,
            borderBottom: `1px solid ${BORDER_COLOR}`,
          }}
        >
          <Typography
            variant="h6"
            sx={{
              color: TEXT_PRIMARY,
              fontWeight: 500,
              letterSpacing: '0.02em',
            }}
          >
            Settings
          </Typography>
          <IconButton onClick={onClose} size="small" sx={{ color: TEXT_SECONDARY }}>
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Content */}
        <Box sx={{ p: 4, overflow: 'auto', flexGrow: 1 }}>
          {saved && (
            <Alert severity="success" sx={{ mb: 2 }}>
              Settings saved
            </Alert>
          )}

          {/* Color Settings */}
          <Box sx={{ mb: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <PaletteIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              <Typography variant="subtitle1" sx={{ color: TEXT_PRIMARY, fontWeight: 500 }}>
                Color Scale
              </Typography>
            </Box>

            <FormControl fullWidth size="small" sx={{ mb: 3 }}>
              <InputLabel sx={{ color: TEXT_SECONDARY }}>Colormap</InputLabel>
              <Select
                value={settings.colormap}
                onChange={(e) => handleChange('colormap', e.target.value)}
                label="Colormap"
                sx={{
                  color: TEXT_PRIMARY,
                  '& .MuiOutlinedInput-notchedOutline': { borderColor: BORDER_COLOR },
                  '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: ACCENT_COLOR },
                }}
              >
                {COLORMAP_OPTIONS.map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>
                    <Box>
                      <Typography variant="body2">{opt.label}</Typography>
                      <Typography variant="caption" sx={{ color: TEXT_SECONDARY }}>
                        {opt.description}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="caption" sx={{ color: TEXT_SECONDARY, mb: 0.5, display: 'block' }}>
                  Min Temperature (°C)
                </Typography>
                <Box
                  component="input"
                  type="number"
                  value={settings.colorScaleMin}
                  onChange={(e) => handleChange('colorScaleMin', parseFloat(e.target.value) || -2)}
                  sx={{
                    width: '100%',
                    p: 1,
                    bgcolor: 'transparent',
                    border: `1px solid ${BORDER_COLOR}`,
                    borderRadius: 1,
                    color: TEXT_PRIMARY,
                    fontSize: '0.875rem',
                    '&:focus': { outline: 'none', borderColor: ACCENT_COLOR },
                  }}
                />
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="caption" sx={{ color: TEXT_SECONDARY, mb: 0.5, display: 'block' }}>
                  Max Temperature (°C)
                </Typography>
                <Box
                  component="input"
                  type="number"
                  value={settings.colorScaleMax}
                  onChange={(e) => handleChange('colorScaleMax', parseFloat(e.target.value) || 35)}
                  sx={{
                    width: '100%',
                    p: 1,
                    bgcolor: 'transparent',
                    border: `1px solid ${BORDER_COLOR}`,
                    borderRadius: 1,
                    color: TEXT_PRIMARY,
                    fontSize: '0.875rem',
                    '&:focus': { outline: 'none', borderColor: ACCENT_COLOR },
                  }}
                />
              </Box>
            </Box>

            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', display: 'block' }}>
              Adjust the temperature range for the SST color scale. Changes apply on page reload.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Map Settings */}
          <Box sx={{ mb: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <MapIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              <Typography variant="subtitle1" sx={{ color: TEXT_PRIMARY, fontWeight: 500 }}>
                Map Display
              </Typography>
            </Box>

            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" sx={{ color: TEXT_SECONDARY, mb: 0.5, display: 'block' }}>
                Layer Opacity: {settings.layerOpacity}%
              </Typography>
              <Box
                component="input"
                type="range"
                min="20"
                max="100"
                value={settings.layerOpacity}
                onChange={(e) => handleChange('layerOpacity', parseInt(e.target.value, 10))}
                sx={{
                  width: '100%',
                  accentColor: ACCENT_COLOR,
                }}
              />
            </Box>

            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', display: 'block' }}>
              Controls the transparency of data layers over the basemap. Changes apply on page reload.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Timeline Settings */}
          <Box sx={{ mb: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <TimelineIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              <Typography variant="subtitle1" sx={{ color: TEXT_PRIMARY, fontWeight: 500 }}>
                Timeline
              </Typography>
            </Box>

            <FormControlLabel
              control={
                <Switch
                  checked={settings.timelineCollapsed}
                  onChange={(e) => handleChange('timelineCollapsed', e.target.checked)}
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': { color: ACCENT_COLOR },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: ACCENT_COLOR },
                  }}
                />
              }
              label="Collapse timeline panel"
              sx={{ color: TEXT_SECONDARY }}
            />
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Storage Settings */}
          <Box sx={{ mb: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <StorageIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              <Typography variant="subtitle1" sx={{ color: TEXT_PRIMARY, fontWeight: 500 }}>
                Storage
              </Typography>
            </Box>

            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={handleClearCache}
              sx={{
                color: TEXT_SECONDARY,
                borderColor: BORDER_COLOR,
                '&:hover': { borderColor: ACCENT_COLOR, color: ACCENT_COLOR },
              }}
            >
              Clear All Settings
            </Button>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', display: 'block', mt: 1 }}>
              Removes all saved preferences and layer visibility settings.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Reset */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)' }}>
              Settings are saved automatically
            </Typography>
            <Button
              variant="text"
              onClick={handleResetDefaults}
              sx={{ color: TEXT_SECONDARY, '&:hover': { color: ACCENT_COLOR } }}
            >
              Reset to Defaults
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
