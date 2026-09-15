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
 * rather than being routed inside YARA. Defaults to that app's dev server; set
 * VITE_GLORYS_APP_URL to its deployed origin in production.
 */
const rawGlorys = (import.meta.env.VITE_GLORYS_APP_URL as string | undefined) || 'http://localhost:5173';
export const GLORYS_APP_URL = rawGlorys.trim().endsWith('/')
  ? rawGlorys.trim().slice(0, -1)
  : rawGlorys.trim();
