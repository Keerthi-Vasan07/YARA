/**
 * Umami Analytics Integration for ECV Viewer
 * 
 * Implements user tracking as required by ECMWF ITT (Requirement 2).
 * Umami is a lightweight, privacy-focused, self-hosted analytics solution.
 * 
 * Benefits over Matomo:
 * - ~10KB script vs 200KB+ for Matomo
 * - No cookies by default (GDPR compliant)
 * - Simple Docker deployment
 * - Modern UI/UX
 * 
 * @see https://umami.is/docs
 */

declare global {
  interface Window {
    umami?: {
      track: (eventName: string, eventData?: Record<string, string | number>) => void;
    };
  }
}

// Umami configuration from environment
const UMAMI_URL = import.meta.env.VITE_UMAMI_URL || '';
const UMAMI_WEBSITE_ID = import.meta.env.VITE_UMAMI_WEBSITE_ID || '';

/**
 * Initialize Umami tracking
 * Should be called once on application startup
 */
export function initAnalytics(): void {
  if (!UMAMI_URL || !UMAMI_WEBSITE_ID) {
    console.info('[Analytics] Disabled: VITE_UMAMI_URL or VITE_UMAMI_WEBSITE_ID not set');
    return;
  }

  // Load Umami script
  const script = document.createElement('script');
  script.async = true;
  script.defer = true;
  script.src = `${UMAMI_URL}/script.js`;
  script.setAttribute('data-website-id', UMAMI_WEBSITE_ID);
  
  // Optional: respect Do Not Track
  script.setAttribute('data-do-not-track', 'true');
  
  // Optional: disable auto-tracking (we'll do manual tracking)
  // script.setAttribute('data-auto-track', 'false');
  
  document.head.appendChild(script);

  console.info('[Analytics] Umami initialized');
}

// Alias for backward compatibility
export const initMatomo = initAnalytics;

/**
 * Track a page view (Umami auto-tracks, but this allows manual control)
 * @param path - The page path (e.g., "/", "/about")
 * @param title - Optional page title
 */
export function trackPageView(path: string, _title?: string): void {
  if (!window.umami) return;
  
  window.umami.track('pageview', { url: path });
}

/**
 * Track an event
 * @param category - Event category (e.g., "Layer", "Download", "Timeline")
 * @param action - Event action (e.g., "select", "download", "animate")
 * @param name - Optional event name
 * @param value - Optional numeric value
 */
export function trackEvent(
  category: string,
  action: string,
  name?: string,
  value?: number
): void {
  if (!window.umami) return;

  const eventData: Record<string, string | number> = {
    category,
    action,
  };
  if (name) eventData.name = name;
  if (value !== undefined) eventData.value = value;
  
  window.umami.track(`${category}:${action}`, eventData);
}

/**
 * Track a site search
 * @param keyword - Search keyword
 * @param category - Optional search category
 * @param resultCount - Optional number of results
 */
export function trackSiteSearch(
  keyword: string,
  category?: string,
  resultCount?: number
): void {
  if (!window.umami) return;

  window.umami.track('search', {
    keyword,
    category: category || 'general',
    results: resultCount || 0,
  });
}

// =============================================================================
// ECV-Specific Tracking Events
// =============================================================================

/**
 * Track when a user selects an ECV variable
 */
export function trackVariableSelection(variable: string): void {
  trackEvent('ECV', 'select-variable', variable);
}

/**
 * Track when a user changes the date/time
 */
export function trackDateChange(date: string, variable: string): void {
  trackEvent('Timeline', 'date-change', `${variable}:${date}`);
}

/**
 * Track when a user starts an animation
 */
export function trackAnimationStart(variable: string, startDate: string, endDate: string): void {
  trackEvent('Animation', 'start', `${variable}:${startDate}-${endDate}`);
}

/**
 * Track when a user downloads data or imagery
 */
export function trackDownload(type: 'image' | 'data' | 'animation', variable: string): void {
  trackEvent('Download', type, variable);
}

/**
 * Track point query (clicking on globe to get value)
 */
export function trackPointQuery(variable: string, lon: number, lat: number): void {
  trackEvent('Query', 'point-value', `${variable}:${lon.toFixed(2)},${lat.toFixed(2)}`);
}

/**
 * Track colormap change
 */
export function trackColormapChange(colormap: string, variable: string): void {
  trackEvent('Visualization', 'colormap-change', `${variable}:${colormap}`);
}

/**
 * Track zoom level changes
 */
export function trackZoom(zoomLevel: number): void {
  trackEvent('Navigation', 'zoom', undefined, zoomLevel);
}

/**
 * Track bounding box selection for data export
 */
export function trackBboxSelection(west: number, south: number, east: number, north: number): void {
  trackEvent('Selection', 'bbox', `${west.toFixed(1)},${south.toFixed(1)},${east.toFixed(1)},${north.toFixed(1)}`);
}

/**
 * Track help/documentation access
 */
export function trackHelpAccess(topic: string): void {
  trackEvent('Help', 'access', topic);
}

/**
 * Track error occurrence (for monitoring)
 */
export function trackError(errorType: string, errorMessage: string): void {
  trackEvent('Error', errorType, errorMessage);
}
