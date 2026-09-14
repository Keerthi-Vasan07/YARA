/**
 * API client for YARA Local Scientific Dataset endpoints.
 */

import { DatasetInfo, ActiveModeResponse, LocalPointQueryResponse, AnalysisOptions, FrameStyle, FrameStats, DatasetGrid } from '../types/dataset';

const rawBase = import.meta.env.VITE_API_BASE_URL || '';
const cleanBase = rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase;
const BASE_URL = `${cleanBase}/api/local-dataset`;
export async function fetchActiveMode(): Promise<ActiveModeResponse> {
  const res = await fetch(`${BASE_URL}/active`);
  if (!res.ok) throw new Error('Failed to fetch active dataset mode');
  return res.json();
}

export async function fetchDatasetList(): Promise<DatasetInfo[]> {
  const res = await fetch(`${BASE_URL}/list`);
  if (!res.ok) throw new Error('Failed to fetch dataset list');
  return res.json();
}

export async function uploadDatasetFile(
  file?: File,
  filePath?: string,
  onProgress?: (pct: number) => void
): Promise<DatasetInfo> {
  const formData = new FormData();
  if (file) {
    formData.append('file', file);
  }
  if (filePath) {
    formData.append('file_path', filePath);
  }

  // Use XMLHttpRequest for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE_URL}/upload`);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          onProgress(pct);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve(data);
        } catch (err) {
          reject(new Error('Invalid response from server'));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || 'Upload failed'));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Network error during dataset upload'));
    xhr.send(formData);
  });
}

export async function activateLocalDataset(datasetId: string): Promise<DatasetInfo> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(datasetId)}/activate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to activate dataset');
  }
  return res.json();
}

export async function deactivateLocalDataset(): Promise<{ mode: string }> {
  const res = await fetch(`${BASE_URL}/deactivate`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to deactivate dataset');
  return res.json();
}

export async function fetchDatasetMetadata(datasetId: string): Promise<DatasetInfo> {
  const res = await fetch(`${BASE_URL}/${encodeURIComponent(datasetId)}/metadata`);
  if (!res.ok) throw new Error('Failed to fetch dataset metadata');
  return res.json();
}

export function getLocalFrameUrl(
  datasetId: string,
  variable?: string,
  timeIndex: number = 0,
  time?: string,
  colormap?: string,
  minVal?: number,
  maxVal?: number,
  analysis?: AnalysisOptions
): string {
  const params = new URLSearchParams();
  if (variable) params.set('variable', variable);
  params.set('time_index', String(timeIndex));
  if (time) params.set('time', time);
  if (colormap) params.set('colormap', colormap);
  if (minVal !== undefined) params.set('min_val', String(minVal));
  if (maxVal !== undefined) params.set('max_val', String(maxVal));
  if (analysis) params.set('analysis', JSON.stringify(analysis));

  return `${BASE_URL}/${encodeURIComponent(datasetId)}/frame?${params.toString()}`;
}

export async function fetchLocalPoint(
  datasetId: string,
  lat: number,
  lon: number,
  variable?: string,
  timeIndex: number = 0,
  time?: string
): Promise<LocalPointQueryResponse> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    time_index: String(timeIndex),
  });
  if (variable) params.set('variable', variable);
  if (time) params.set('time', time);

  const res = await fetch(`${BASE_URL}/${encodeURIComponent(datasetId)}/point?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to query data point');
  return res.json();
}

export async function prefetchLocalFrames(
  datasetId: string,
  variable?: string,
  startIndex: number = 0,
  count: number = 10,
  style?: FrameStyle
): Promise<{ status: string; prefetched_count: number }> {
  const params = new URLSearchParams({
    start_index: String(startIndex),
    count: String(count),
  });
  if (variable) params.set('variable', variable);
  if (style?.analysis) params.set('analysis', JSON.stringify(style.analysis));
  if (style?.colormap) params.set('colormap', style.colormap);
  if (style?.minVal !== undefined) params.set('min_val', String(style.minVal));
  if (style?.maxVal !== undefined) params.set('max_val', String(style.maxVal));

  const res = await fetch(`${BASE_URL}/${encodeURIComponent(datasetId)}/prefetch?${params.toString()}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to trigger prefetching');
  return res.json();
}

async function localJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Dataset request failed (${response.status})`);
  }
  return response.json();
}

export function fetchLocalStats(datasetId: string, variable: string, index: number, style: FrameStyle, signal?: AbortSignal): Promise<FrameStats> {
  const frameUrl = getLocalFrameUrl(datasetId, variable, index, undefined, style.colormap, style.minVal, style.maxVal, style.analysis);
  return localJson(frameUrl.replace('/frame?', '/frame/stats?'), signal);
}

export function fetchLocalGrid(datasetId: string, variable: string, signal?: AbortSignal): Promise<DatasetGrid> {
  return localJson(`${BASE_URL}/${encodeURIComponent(datasetId)}/grid?${new URLSearchParams({ variable })}`, signal);
}

