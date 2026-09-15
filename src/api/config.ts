/**
 * Consolidated API Base URL configuration for YARA frontend.
 */
const rawBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '';
export const API_BASE_URL = rawBase.trim().endsWith('/') ? rawBase.trim().slice(0, -1) : rawBase.trim();

export function buildApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

/**
 * Base URL of the separate GLORYS 3D volume ("detailed subsurface analysis") app.
 * It is its own Vite application with its own backend, so it is addressed by URL
 * rather than being routed inside YARA.
 *
 * In development we fall back to that app's configured dev server
 * (frontend/vite.config.ts -> server.port = 5173) so the flow works locally with
 * no setup. In a production build there is NO fallback: opening a localhost URL
 * from a deployed site can never work, so an unset variable is surfaced to the
 * user as a configuration error instead of a broken tab. Set VITE_GLORYS_APP_URL
 * to the deployed GLORYS frontend origin.
 */
const GLORYS_DEV_FALLBACK = 'http://localhost:5173';
const rawGlorys = ((import.meta.env.VITE_GLORYS_APP_URL as string | undefined) ?? '').trim();
const resolvedGlorys = rawGlorys || (import.meta.env.DEV ? GLORYS_DEV_FALLBACK : '');

export const GLORYS_APP_URL = resolvedGlorys.replace(/\/+$/, '');
export const isGlorysConfigured = GLORYS_APP_URL.length > 0;
