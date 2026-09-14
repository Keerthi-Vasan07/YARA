import { Typography } from '@mui/material';
import type { OnlineDataset, OnlineTimes } from '../../api/onlineApi';

export function OnlineDatasetInfo({ dataset, times }: { dataset: OnlineDataset | undefined; times: OnlineTimes | null }) {
  if (!dataset) return null;
  return <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'rgba(255,255,255,.58)' }}>
    {dataset.source} · {dataset.spatial_resolution} · {times?.temporal_resolution || dataset.temporal_resolution}<br />
    Coverage: {dataset.coverage.south}° to {dataset.coverage.north}°; {dataset.coverage.west}° to {dataset.coverage.east}°
  </Typography>;
}
