import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { LocalPointQueryResponse } from '../types/dataset';

export function LocalPointInfoPanel({ data, loading, error, onClose }: {
  data: LocalPointQueryResponse | null; loading: boolean; error: string; onClose: () => void;
}) {
  if (!data && !loading && !error) return null;
  const bounds = data?.cell_bounds;
  return <Box role="dialog" aria-label="Local dataset point" sx={{ position: 'absolute', top: 80, left: 90,
    maxWidth: 350, maxHeight: '70vh', overflowY: 'auto', p: 2, zIndex: 1100, bgcolor: 'rgba(8,12,18,0.96)' }}>
    <Stack spacing={1}>
      <Typography variant="subtitle2">Local dataset point</Typography>
      {loading && <Typography role="status">Reading dataset value…</Typography>}
      {error && <Alert severity="error">{error}</Alert>}
      {data && <>
        <Typography>Variable: {data.variable}</Typography>
        <Typography>Units: {data.units || 'Not specified'}</Typography>
        <Typography>Actual value: {data.is_valid ? data.value : 'No data / masked cell'}</Typography>
        <Typography>Requested latitude: {data.requested_lat}</Typography>
        <Typography>Requested longitude: {data.requested_lon}</Typography>
        <Typography>Matched latitude: {data.matched_lat}</Typography>
        <Typography>Matched longitude: {data.matched_lon}</Typography>
        <Typography>Timestamp: {data.timestamp || 'Not supplied by dataset'}</Typography>
        <Typography>Frame: {(data.time_index ?? 0) + 1}</Typography>
        {bounds ? <>
          <Typography>Cell south: {bounds.south}°</Typography><Typography>Cell north: {bounds.north}°</Typography>
          <Typography>Cell west: {bounds.west}°</Typography><Typography>Cell east: {bounds.east}°</Typography>
        </> : <Typography>Cell bounds unavailable</Typography>}
        <Typography variant="caption">Native dataset value, independent of display filters. Cell edges are inferred from neighboring coordinates.</Typography>
      </>}
      <Button onClick={onClose}>Close</Button>
    </Stack>
  </Box>;
}
