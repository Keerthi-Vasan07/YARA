/**
 * Geographic bounds handed over from YARA via URL query parameters.
 *
 * YARA computes the 1° x 1° cell containing the point the user clicked on its
 * Cesium globe and opens this app with:
 *
 *     /?lonMin=-66&lonMax=-65&latMin=44&latMax=45
 *
 * Query parameters are untrusted input: every value is parsed numerically and
 * range-checked, and the whole set is rejected unless all four are valid and
 * consistent. Callers fall back to this app's own defaults when null is returned.
 */

export interface IncomingBounds {
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
}

function parseNumber(raw: string | null): number | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/**
 * Reads and validates bounds from a query string (defaults to the current URL).
 * Returns null when the parameters are absent, malformed, out of range, or
 * inverted — never throws, so a bad link cannot break startup.
 */
export function readIncomingBounds(search?: string): IncomingBounds | null {
  try {
    const params = new URLSearchParams(
      search ?? (typeof window !== "undefined" ? window.location.search : "")
    );

    const lonMin = parseNumber(params.get("lonMin"));
    const lonMax = parseNumber(params.get("lonMax"));
    const latMin = parseNumber(params.get("latMin"));
    const latMax = parseNumber(params.get("latMax"));

    if (lonMin === null || lonMax === null || latMin === null || latMax === null) {
      return null;
    }

    const latInRange = (v: number) => v >= -90 && v <= 90;
    const lonInRange = (v: number) => v >= -180 && v <= 180;
    if (!latInRange(latMin) || !latInRange(latMax)) return null;
    if (!lonInRange(lonMin) || !lonInRange(lonMax)) return null;

    // A zero-width or inverted box would produce an empty/invalid query.
    if (lonMin >= lonMax || latMin >= latMax) return null;

    return { lonMin, lonMax, latMin, latMax };
  } catch {
    return null;
  }
}
