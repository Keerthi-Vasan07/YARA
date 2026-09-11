import { createTheme, alpha } from '@mui/material/styles';

/**
 * ARCO SST Viewer Theme - "Midnight"
 * Sleek, minimal, flat design for geospatial applications
 * Adapted from SAR-Watch design system
 */
export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#3B82F6',
      light: '#60A5FA',
      dark: '#2563EB',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#06B6D4', // Cyan for ocean/SST theme
      light: '#22D3EE',
      dark: '#0891B2',
      contrastText: '#FFFFFF',
    },
    error: { main: '#EF4444', light: '#F87171', dark: '#DC2626' },
    warning: { main: '#F59E0B', light: '#FBBF24', dark: '#D97706' },
    info: { main: '#06B6D4', light: '#22D3EE', dark: '#0891B2' },
    success: { main: '#10B981', light: '#34D399', dark: '#059669' },
    background: {
      default: '#09090B', // Zinc 950
      paper: '#18181B',   // Zinc 900
    },
    text: {
      primary: '#FAFAFA',
      secondary: '#A1A1AA',
      disabled: '#71717A',
    },
    divider: alpha('#FFFFFF', 0.06),
    action: {
      active: '#FAFAFA',
      hover: alpha('#FFFFFF', 0.04),
      selected: alpha('#3B82F6', 0.12),
      disabled: alpha('#FFFFFF', 0.26),
      disabledBackground: alpha('#FFFFFF', 0.12),
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 700, letterSpacing: '-0.02em', fontSize: '2.25rem' },
    h2: { fontWeight: 700, letterSpacing: '-0.015em', fontSize: '1.875rem' },
    h3: { fontWeight: 600, letterSpacing: '-0.01em', fontSize: '1.5rem' },
    h4: { fontWeight: 600, fontSize: '1.25rem' },
    h5: { fontWeight: 600, fontSize: '1.125rem' },
    h6: { fontWeight: 600, fontSize: '1rem' },
    subtitle1: { fontWeight: 500, fontSize: '0.875rem', letterSpacing: '0.02em' },
    subtitle2: { fontWeight: 500, fontSize: '0.8125rem', color: '#A1A1AA', letterSpacing: '0.02em' },
    body1: { fontSize: '0.875rem', lineHeight: 1.7, letterSpacing: '0.01em' },
    body2: { fontSize: '0.8125rem', lineHeight: 1.6, letterSpacing: '0.01em' },
    button: { fontWeight: 600, letterSpacing: '0.02em', textTransform: 'none' as const, fontSize: '0.8125rem' },
    caption: { fontSize: '0.6875rem', color: '#71717A', letterSpacing: '0.03em' },
    overline: { fontSize: '0.625rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' as const, color: '#3B82F6' },
  },
  shape: { borderRadius: 4 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          scrollbarWidth: 'thin',
          scrollbarColor: '#3f3f46 transparent',
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true, disableRipple: true },
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 4,
          padding: '8px 16px',
          transition: 'background-color 0.15s ease',
        },
        contained: {
          '&:hover': { filter: 'brightness(1.1)' },
        },
        outlined: {
          borderColor: alpha('#FFFFFF', 0.12),
          '&:hover': {
            borderColor: alpha('#FFFFFF', 0.24),
            backgroundColor: alpha('#FFFFFF', 0.04),
          },
        },
        text: {
          '&:hover': { backgroundColor: alpha('#FFFFFF', 0.04) },
        },
        sizeSmall: { padding: '6px 12px', fontSize: '0.75rem' },
        sizeLarge: { padding: '12px 24px', fontSize: '0.875rem' },
      },
    },
    MuiIconButton: {
      defaultProps: { disableRipple: true },
      styleOverrides: {
        root: {
          borderRadius: 4,
          transition: 'background-color 0.15s ease',
          '&:hover': { backgroundColor: alpha('#FFFFFF', 0.06) },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          boxShadow: 'none',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none',
        },
      },
    },
    MuiSlider: {
      styleOverrides: {
        root: {
          height: 4,
        },
        track: {
          border: 'none',
        },
        thumb: {
          width: 16,
          height: 16,
          '&:hover, &.Mui-focusVisible': {
            boxShadow: `0 0 0 8px ${alpha('#3B82F6', 0.16)}`,
          },
        },
        rail: {
          opacity: 0.3,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: '#27272A',
          border: `1px solid ${alpha('#FFFFFF', 0.1)}`,
          fontSize: '0.75rem',
          padding: '8px 12px',
        },
      },
    },
  },
});
