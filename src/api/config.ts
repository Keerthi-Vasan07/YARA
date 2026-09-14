/**
 * Consolidated API Base URL configuration for YARA frontend.
 */
const rawBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '';
export const API_BASE_URL = rawBase.trim().endsWith('/') ? rawBase.trim().slice(0, -1) : rawBase.trim();

export function buildApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}
