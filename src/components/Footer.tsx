import { Box, Typography, Link } from '@mui/material';

export function Footer() {
  return (
    <Box
      component="footer"
      sx={{
        position: 'absolute',
        bottom: 0,
        right: 12,
        height: 28,
        px: 1.5,
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        bgcolor: 'rgba(8, 12, 18, 0.85)',
        backdropFilter: 'blur(16px)',
        borderRadius: 0,
        zIndex: 1001,
      }}
    >
      <Typography variant="caption" sx={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)' }}>
        ARCO 3D Globe — Ocean ECV Visualization Platform
      </Typography>
      <Box sx={{ width: 1, height: 12, bgcolor: 'rgba(255,255,255,0.15)' }} />
      <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.35)' }}>
        Data: Copernicus Marine Service
      </Typography>
      <Box sx={{ width: 1, height: 12, bgcolor: 'rgba(255,255,255,0.15)' }} />
      <Link
        href="https://oceanstream.io"
        target="_blank"
        rel="noopener"
        underline="none"
        sx={{
          fontSize: '0.65rem',
          color: 'rgba(255,255,255,0.5)',
          '&:hover': { color: 'rgba(255,255,255,0.8)' },
          transition: 'color 0.15s',
        }}
      >
        oceanstream.io
      </Link>
    </Box>
  );
}
