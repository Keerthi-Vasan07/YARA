import { Box, IconButton, Stack, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';

export interface ArgoGliderObservation {
  kind: 'argo' | 'glider';
  properties: Record<string, unknown>;
}

const FIELD_LABELS: Array<[key: string, label: string]> = [
  ['platform', 'Platform ID'],
  ['latitude', 'Latitude'],
  ['longitude', 'Longitude'],
  ['time', 'Time'],
  ['temperature', 'Temperature'],
  ['salinity', 'Salinity'],
  ['pressure', 'Pressure'],
  ['depth', 'Depth'],
  ['cycle', 'Cycle'],
  ['source', 'Source'],
];

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return String(Math.round(value * 1000) / 1000);
  return String(value);
}

/**
 * Shows only metadata actually present on the clicked Argo/Glider entity —
 * never fabricates fields the backend/reader didn't provide.
 */
export function ArgoGliderObservationPanel({
  observation,
  onClose,
}: {
  observation: ArgoGliderObservation | null;
  onClose: () => void;
}) {
  if (!observation) return null;
  const { kind, properties } = observation;

  const rows = FIELD_LABELS.filter(([key]) => properties[key] !== undefined);

  return (
    <Box
      role="dialog"
      aria-label={kind === 'argo' ? 'Argo observation' : 'Glider observation'}
      sx={{
        position: 'absolute', bottom: 90, left: 90, width: 280,
        maxHeight: '50vh', overflowY: 'auto', p: 1.5, zIndex: 1100,
        bgcolor: 'rgba(8,12,18,0.96)', color: 'white',
        border: '1px solid rgba(110,242,252,0.25)',
        boxShadow: '0 12px 40px rgba(0,0,0,.5)',
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" fontWeight={700}>
          {kind === 'argo' ? 'Argo observation' : 'Glider observation'}
        </Typography>
        <IconButton size="small" onClick={onClose} sx={{ color: 'white' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Stack spacing={0.5} sx={{ mt: 1 }}>
        {rows.length === 0 && (
          <Typography variant="caption" sx={{ opacity: 0.7 }}>
            No metadata was returned for this observation.
          </Typography>
        )}
        {rows.map(([key, label]) => (
          <Typography variant="body2" key={key}>
            {label}: {formatValue(properties[key])}
          </Typography>
        ))}
      </Stack>
    </Box>
  );
}
