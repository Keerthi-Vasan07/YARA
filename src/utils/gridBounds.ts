/**
 * 1° x 1° grid-cell bounds for a clicked geographic point.
 *
 * Convention is taken from YARA's existing reference grid in
 * server/data_sources/local/coordinate_utils.py (grid_metadata), which draws its
 * reference grid lines on whole integer degrees:
 *
 *     latitudes  = arange(ceil(south), floor(north) + 1)
 *     longitudes = arange(ceil(west),  floor(east)  + 1)
 *
 * A 1° cell is therefore bounded by consecutive integer degrees, so the cell
 * containing a point is floor-based: lat 44.7 -> [44, 45], lon -65.4 -> [-66, -65].
 * This helper exists because that convention lived only in the Python grid-line
 * generator; there was no frontend equivalent to reuse.
 */

export interface GridBounds {
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
}

export function isValidLatitude(lat: number): boolean {
  return Number.isFinite(lat) && lat >= -90 && lat <= 90;
}

export function isValidLongitude(lon: number): boolean {
  return Number.isFinite(lon) && lon >= -180 && lon <= 180;
}

/**
 * Returns the 1° x 1° cell containing the point, or null if the input is not a
 * valid geographic coordinate. At the +90 / +180 edges the cell is clamped
 * inward so the returned box always stays within valid bounds and keeps
 * min < max.
 */
export function getSelectedGridBounds(latitude: number, longitude: number): GridBounds | null {
  if (!isValidLatitude(latitude) || !isValidLongitude(longitude)) return null;

  let latMin = Math.floor(latitude);
  let lonMin = Math.floor(longitude);

  // Clamp the degenerate top edge (lat exactly 90 / lon exactly 180).
  if (latMin >= 90) latMin = 89;
  if (lonMin >= 180) lonMin = 179;

  return { lonMin, lonMax: lonMin + 1, latMin, latMax: latMin + 1 };
}
