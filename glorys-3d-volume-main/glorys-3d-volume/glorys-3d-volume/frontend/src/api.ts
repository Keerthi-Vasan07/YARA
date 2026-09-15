import type {
  TimeRangeResponse,
  DateMetadata,
  VolumeParams,
  VolumeData,
  VolumeMeta,
  ProfileResponse,
  GlorysHealth,
  GlorysInfo,
  OceanVariable,
  VerticalColumnResponse,
  PointProbeResponse,
} from "./types";

const BASE = "/api";

export async function fetchHealth(): Promise<GlorysHealth> {
  const res = await fetch(`${BASE}/glorys/health`);
  if (!res.ok) throw new Error(`GLORYS health check failed (${res.status})`);
  return res.json();
}

export async function fetchTimeRange(variable: OceanVariable = "thetao"): Promise<TimeRangeResponse> {
  const res = await fetch(`${BASE}/glorys/time-range?variable=${encodeURIComponent(variable)}`);
  if (!res.ok) throw new Error(`Failed to fetch GLORYS time range (${res.status})`);
  return res.json();
}

export async function fetchMetadata(date: string, variable: OceanVariable = "thetao"): Promise<DateMetadata> {
  const res = await fetch(
    `${BASE}/glorys/metadata?date=${encodeURIComponent(date)}&variable=${encodeURIComponent(variable)}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Failed to fetch metadata for ${date}`);
  }
  return res.json();
}

/**
 * Fetch remote GLORYS volume as compact binary Float32 packet:
 *   [4-byte uint32 big-endian JSON metadata length]
 *   + [UTF-8 JSON metadata]
 *   + [Raw Float32Array bytes]
 *
 * Works for both 3D variables (thetao, so) and 2D variables (mlotst, ohc_0_700m).
 * The byte length is derived from the shape in the metadata — NOT hardcoded.
 */
export async function fetchVolume(
  params: VolumeParams,
  signal?: AbortSignal
): Promise<VolumeData> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      qs.set(k, String(v));
    }
  });

  const url = `${BASE}/glorys/volume?${qs.toString()}`;
  console.log(
    `%c[GLORYS-FETCH] ▶ ${url}`,
    "color: #22d3ee; font-weight: bold;"
  );

  const res = await fetch(url, { signal });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Volume fetch failed (${res.status})`);
  }

  const buffer = await res.arrayBuffer();
  if (buffer.byteLength < 4) {
    throw new Error("Received empty or invalid binary packet from GLORYS volume API.");
  }

  const view = new DataView(buffer);
  const metaLen = view.getUint32(0, false); // big-endian uint32
  if (buffer.byteLength < 4 + metaLen) {
    throw new Error(`Corrupted binary packet: header specifies ${metaLen} bytes, received ${buffer.byteLength}.`);
  }

  const metaBytes = new Uint8Array(buffer, 4, metaLen);
  const metaJsonStr = new TextDecoder().decode(metaBytes);
  const meta: VolumeMeta = JSON.parse(metaJsonStr);

  const float32Offset = 4 + metaLen;
  // buffer.slice creates an aligned ArrayBuffer starting at 0 for safe Float32Array construction
  const float32Slice = buffer.slice(float32Offset);
  const float32 = new Float32Array(float32Slice);

  // Verify payload byte length matches metadata-declared shape
  const channelCount = meta.channel_count ?? (meta.is_multi_channel ? 4 : 1);
  const expectedVoxels = meta.shape.depth * meta.shape.lat * meta.shape.lon * channelCount;
  const expectedBytes  = expectedVoxels * 4;
  if (float32Slice.byteLength !== expectedBytes) {
    console.warn(
      `[GLORYS-FETCH] Payload size mismatch: expected ${expectedBytes} bytes ` +
      `(${meta.shape.depth}×${meta.shape.lat}×${meta.shape.lon}×${channelCount}×4) ` +
      `but received ${float32Slice.byteLength} bytes.`
    );
  }

  // Compute client-side SHA-256 hash of the raw float32 bytes for independent verification
  const hashBuffer = await crypto.subtle.digest("SHA-256", float32Slice);
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);

  const serverHash = meta.payload_hash ?? "N/A";
  const hashMatch = hashHex === serverHash;
  console.log(
    `%c[GLORYS-FETCH] ◀ var=${meta.variable ?? "?"} mode=${meta.mode ?? "?"} date=${meta.date ?? "?"} ` +
    `is_2d=${meta.is_2d ?? false} ` +
    `shape=${meta.shape.lon}×${meta.shape.lat}×${meta.shape.depth} ` +
    `bytes=${meta.byte_length} server_hash=${serverHash} client_hash=${hashHex} ` +
    `hash_match=${hashMatch ? "✅" : "❌ MISMATCH!"}`,
    hashMatch ? "color: #4ade80; font-weight: bold;" : "color: #f87171; font-weight: bold;"
  );

  return { meta, float32 };
}

export async function fetchProfile(
  lat: number,
  lon: number,
  date?: string,
  variable: OceanVariable = "thetao"
): Promise<ProfileResponse> {
  const qs = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    variable: variable,
  });
  if (date) qs.set("date", date);

  const res = await fetch(`${BASE}/glorys/profile?${qs.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Profile fetch failed (${res.status})`);
  }
  return res.json();
}

export async function fetchInfo(): Promise<GlorysInfo> {
  const res = await fetch(`${BASE}/glorys/info`);
  if (!res.ok) throw new Error(`info failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch a derived subsurface variable from the OPeNDAP THREDDS endpoint.
 * Supported variables: temperature | salinity | current_speed | sound_speed | density
 *
 * Wire format is identical to fetchVolume() — same binary packet decoder is reused.
 */
export async function fetchSubsurfaceVolume(params: {
  variable: string;
  latMin?: number;
  latMax?: number;
  lonMin?: number;
  lonMax?: number;
  depthMin?: number;
  depthMax?: number;
  downsampleStride?: number;
}, signal?: AbortSignal): Promise<VolumeData> {
  const qs = new URLSearchParams({ variable: params.variable });
  if (params.latMin    !== undefined) qs.set("lat_min",           String(params.latMin));
  if (params.latMax    !== undefined) qs.set("lat_max",           String(params.latMax));
  if (params.lonMin    !== undefined) qs.set("lon_min",           String(params.lonMin));
  if (params.lonMax    !== undefined) qs.set("lon_max",           String(params.lonMax));
  if (params.depthMin  !== undefined) qs.set("depth_min",         String(params.depthMin));
  if (params.depthMax  !== undefined) qs.set("depth_max",         String(params.depthMax));
  if (params.downsampleStride !== undefined) qs.set("downsample_stride", String(params.downsampleStride));

  const url = `${BASE}/v1/subsurface/volume?${qs.toString()}`;
  console.log(`%c[OPENDAP-FETCH] ▶ ${url}`, "color: #f59e0b; font-weight: bold;");

  const res = await fetch(url, { signal });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Subsurface volume fetch failed (${res.status})`);
  }

  // ── Identical binary packet decoder to fetchVolume ──────────────────────
  const buffer = await res.arrayBuffer();
  if (buffer.byteLength < 4) {
    throw new Error("Received empty or invalid binary packet from subsurface volume API.");
  }

  const view    = new DataView(buffer);
  const metaLen = view.getUint32(0, false);
  if (buffer.byteLength < 4 + metaLen) {
    throw new Error(`Corrupted binary packet: header specifies ${metaLen} bytes, received ${buffer.byteLength}.`);
  }

  const metaBytes  = new Uint8Array(buffer, 4, metaLen);
  const meta: VolumeMeta = JSON.parse(new TextDecoder().decode(metaBytes));

  const float32Slice = buffer.slice(4 + metaLen);
  const float32      = new Float32Array(float32Slice);

  const expectedVoxels = meta.shape.depth * meta.shape.lat * meta.shape.lon;
  if (float32.length !== expectedVoxels) {
    console.warn(
      `[OPENDAP-FETCH] Size mismatch: expected ${expectedVoxels} voxels, got ${float32.length}`
    );
  }

  const hashBuffer = await crypto.subtle.digest("SHA-256", float32Slice);
  const hashHex    = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);

  console.log(
    `%c[OPENDAP-FETCH] ◀ var=${meta.variable} ` +
    `shape=${meta.shape.lon}×${meta.shape.lat}×${meta.shape.depth} ` +
    `bytes=${meta.byte_length} hash=${hashHex}`,
    "color: #f59e0b; font-weight: bold;"
  );

  return { meta, float32 };
}

/**
 * Fetch 3D subsurface vertical column profile (Temperature, Salinity, Chlorophyll-a).
 */
export async function fetchVerticalColumn(
  lat: number,
  lon: number,
  maxDepth: number = 1000.0,
  signal?: AbortSignal
): Promise<VerticalColumnResponse> {
  const url = `${BASE}/ocean/vertical-column?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&max_depth=${encodeURIComponent(maxDepth)}`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Vertical column fetch failed (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch point probe telemetry with dataset & global land mask enforcement.
 */
export async function fetchPointProbe(
  lat: number,
  lon: number,
  depth: number = 0.5,
  date?: string,
  variable?: OceanVariable,
  signal?: AbortSignal
): Promise<PointProbeResponse> {
  const qs = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    depth: String(depth),
  });
  if (date) qs.set("date", date);
  if (variable) qs.set("variable", variable);

  const res = await fetch(`${BASE}/glorys/point?${qs.toString()}`, { signal });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Point probe fetch failed (${res.status})`);
  }
  return res.json();
}

