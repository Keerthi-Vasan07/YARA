import { Box, Typography, Stack, alpha, CircularProgress, Slide } from '@mui/material';
import { CheckCircle, ErrorOutline, Science } from '@mui/icons-material';

export interface ProcessingState {
  isProcessing: boolean;
  status: 'idle' | 'fetching' | 'processing' | 'success' | 'error';
  title?: string;
  message?: string;
}

interface ScientificProcessingToastProps {
  state: ProcessingState;
}

export function ScientificProcessingToast({ state }: ScientificProcessingToastProps) {
  const { isProcessing, status, title, message } = state;

  if (!isProcessing && status === 'idle') {
    return null;
  }

  const accent =
    status === 'error'
      ? '#ef5350'
      : status === 'success'
      ? '#66bb6a'
      : '#6EF2FC';

  const defaultTitle =
    status === 'fetching'
      ? 'Fetching scientific data…'
      : status === 'processing'
      ? 'Processing scientific data…'
      : status === 'success'
      ? 'Scientific data ready'
      : status === 'error'
      ? 'Unable to process scientific data'
      : 'Scientific processing…';

  const defaultMessage =
    status === 'fetching'
      ? 'Requesting remote OPeNDAP dataset. This may take a moment…'
      : status === 'processing'
      ? 'Rendering raster imagery and preparing globe visualization…'
      : status === 'success'
      ? 'Dataset updated successfully.'
      : status === 'error'
      ? 'Please check dataset parameters or try again.'
      : '';

  return (
    <Slide direction="right" in={isProcessing || status === 'success' || status === 'error'} mountOnEnter unmountOnExit>
      <Box
        sx={{
          position: 'fixed',
          bottom: 28,
          left: 16,
          width: 320,
          bgcolor: 'rgba(6, 10, 18, 0.92)',
          backdropFilter: 'blur(20px)',
          border: `1px solid ${alpha(accent, 0.35)}`,
          borderRadius: 0,
          p: 1.75,
          zIndex: 1200,
          boxShadow: `0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(0,0,0,0.3), inset 0 1px 0 ${alpha(accent, 0.2)}`,
        }}
      >
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 2,
            background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          }}
        />

        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Box sx={{ mt: 0.25, flexShrink: 0 }}>
            {status === 'fetching' || status === 'processing' ? (
              <CircularProgress size={18} sx={{ color: accent }} />
            ) : status === 'success' ? (
              <CheckCircle sx={{ fontSize: 20, color: '#66bb6a' }} />
            ) : status === 'error' ? (
              <ErrorOutline sx={{ fontSize: 20, color: '#ef5350' }} />
            ) : (
              <Science sx={{ fontSize: 20, color: accent }} />
            )}
          </Box>

          <Stack spacing={0.25} sx={{ flex: 1 }}>
            <Typography
              variant="subtitle2"
              sx={{
                fontWeight: 700,
                fontSize: '0.78rem',
                color: accent,
                lineHeight: 1.3,
              }}
            >
              {title || defaultTitle}
            </Typography>

            <Typography
              variant="caption"
              sx={{
                color: 'rgba(255,255,255,0.65)',
                fontSize: '0.65rem',
                lineHeight: 1.4,
              }}
            >
              {message || defaultMessage}
            </Typography>
          </Stack>
        </Stack>
      </Box>
    </Slide>
  );
}
