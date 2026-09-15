precision highp float;
precision highp sampler3D;

varying vec3 vLocalPosition;
varying vec3 vWorldCameraLocal;

out vec4 fragColor;

uniform sampler3D uVolume;       // 3D volume texture (R or RGBA)
uniform float uTempMin;          // colormap lower bound (deg C)
uniform float uTempMax;          // colormap upper bound (deg C)
uniform float uOpacity;          // global opacity multiplier
uniform int uSteps;              // ray march sample count

uniform vec3 uScale;             // scaling applied to the box mesh

// Multi-variable visualization uniforms
uniform int uRenderMode;         // 0: Temperature, 1: Salinity, 2: Chlorophyll, 3: Multi-Variable Composite
uniform float uChlIntensity;     // Intensity scalar for chlorophyll bloom glow
uniform float uSalinityWeight;   // Weight scalar for haline salinity blending
uniform int uIsMultiChannel;     // 1 if 4-channel RGBA packed, 0 if single channel R

const int MAX_STEPS = 512;

// Box-local axes: x = longitude, y = depth (flipped, deep = -Y so it renders downward),
// z = latitude. Texture axes: s = longitude (un-mirrored: 0.5 - p.x), t = latitude, r = depth (ascending, shallow->deep).
vec3 localToTexCoord(vec3 p) {
  float s = p.x + 0.5;        // longitude: West to East
  float t = p.z + 0.5;        // latitude
  float r = 0.5 - p.y;        // depth: box top (y=+0.5) = shallow (r=0), bottom (y=-0.5) = deep (r=1)
  return vec3(s, t, r);
}

// 1. Cold -> warm scientific temperature colormap (dark blue -> cyan -> yellow -> red)
vec3 colormapTemp(float t) {
  t = clamp(t, 0.0, 1.0);
  vec3 c0 = vec3(0.02, 0.02, 0.35);
  vec3 c1 = vec3(0.10, 0.45, 0.90);
  vec3 c2 = vec3(0.10, 0.85, 0.75);
  vec3 c3 = vec3(0.95, 0.95, 0.25);
  vec3 c4 = vec3(0.95, 0.35, 0.10);
  vec3 c5 = vec3(0.75, 0.05, 0.05);

  if (t < 0.2) return mix(c0, c1, t / 0.2);
  if (t < 0.4) return mix(c1, c2, (t - 0.2) / 0.2);
  if (t < 0.6) return mix(c2, c3, (t - 0.4) / 0.2);
  if (t < 0.8) return mix(c3, c4, (t - 0.6) / 0.2);
  return mix(c4, c5, (t - 0.8) / 0.2);
}

// 2. Salinity Colormap (Haline): Fresh/Low Cyan -> Blue -> Violet -> Deep Purple/Magenta
vec3 colormapSalinity(float s) {
  s = clamp(s, 0.0, 1.0);
  vec3 c0 = vec3(0.00, 0.92, 0.96); // low salinity: vibrant electric cyan
  vec3 c1 = vec3(0.15, 0.55, 0.95); // oceanic blue
  vec3 c2 = vec3(0.60, 0.20, 0.88); // halocline violet
  vec3 c3 = vec3(0.48, 0.03, 0.52); // high salinity: deep purple / magenta

  if (s < 0.33) return mix(c0, c1, s / 0.33);
  if (s < 0.66) return mix(c1, c2, (s - 0.33) / 0.33);
  return mix(c2, c3, (s - 0.66) / 0.34);
}

// 3. Chlorophyll Colormap: Subtle dark emerald -> Vivid Emerald -> Neon Green (#00FF66)
vec3 colormapChlorophyll(float c) {
  c = clamp(c, 0.0, 1.0);
  vec3 c0 = vec3(0.04, 0.25, 0.18); // oligotrophic oceanic background
  vec3 c1 = vec3(0.08, 0.72, 0.35); // healthy emerald green
  vec3 c2 = vec3(0.00, 1.00, 0.40); // vivid neon bloom green (#00FF66)

  if (c < 0.5) return mix(c0, c1, c / 0.5);
  return mix(c1, c2, (c - 0.5) / 0.5);
}

vec2 intersectBox(vec3 origin, vec3 dir) {
  vec3 invDir = 1.0 / dir;
  vec3 tMinV = (vec3(-0.5) - origin) * invDir;
  vec3 tMaxV = (vec3(0.5) - origin) * invDir;
  vec3 t1 = min(tMinV, tMaxV);
  vec3 t2 = max(tMinV, tMaxV);
  float tNear = max(max(t1.x, t1.y), t1.z);
  float tFar = min(min(t2.x, t2.y), t2.z);
  return vec2(tNear, tFar);
}

void main() {
  // Compute physically accurate ray direction by accounting for mesh scale
  vec3 truePos = vLocalPosition * uScale;
  vec3 trueCam = vWorldCameraLocal * uScale;
  vec3 trueRayDir = normalize(truePos - trueCam); 
  
  // Transform back to local space to intersect the [-0.5, 0.5]^3 bounding box
  vec3 localRayDir = trueRayDir / uScale;

  vec2 tHit = intersectBox(vWorldCameraLocal, localRayDir);
  float tNear = max(tHit.x, 0.0);
  float tFar = tHit.y;

  if (tNear >= tFar) discard;

  float stepSize = (tFar - tNear) / float(uSteps);

  // Apply Interleaved Gradient Noise for ray jitter to prevent banding
  float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
  tNear += stepSize * jitter;

  vec3 pos = vWorldCameraLocal + localRayDir * tNear;
  vec3 step = localRayDir * stepSize;

  vec4 accumulated = vec4(0.0);
  float baseAlpha = clamp(uOpacity * (2.8 / float(uSteps)), 0.005, 0.25);

  for (int i = 0; i < MAX_STEPS; i++) {
    if (i >= uSteps) break;
    float t = tNear + float(i) * stepSize;
    if (t > tFar) break;

    vec3 texCoord = localToTexCoord(pos);
    vec4 sampleVal = texture(uVolume, texCoord);

    if (uIsMultiChannel == 1) {
      // 4-Channel RGBA Multi-Variable Volume:
      // R: norm_temp [0..1]
      // G: norm_salinity [0..1]
      // B: norm_chl [0..1]
      // A: ocean validity mask (1.0 = ocean, 0.0 = land/NaN)
      float valid = sampleVal.a;
      if (valid > 0.5) {
        // Safe temperature normalization: auto-detect if sampleVal.r is already [0..1] normalized or raw °C
        float tNorm = (sampleVal.r <= 1.05 && uTempMin >= 5.0)
          ? sampleVal.r
          : clamp((sampleVal.r - uTempMin) / max(uTempMax - uTempMin, 0.0001), 0.0, 1.0);
        float sNorm = sampleVal.g;
        float cNorm = sampleVal.b;

        vec3 stepColor = vec3(0.0);
        float stepAlpha = baseAlpha;

        if (uRenderMode == 0) {
          // Temperature (Thermal)
          stepColor = colormapTemp(tNorm);
        } else if (uRenderMode == 1) {
          // Salinity (Haline)
          stepColor = colormapSalinity(sNorm);
          stepAlpha *= uSalinityWeight;
        } else if (uRenderMode == 2) {
          // Chlorophyll-a (Algal)
          stepColor = colormapChlorophyll(cNorm);
          // Transparency in deep waters, glow in euphotic bloom zone
          stepAlpha = clamp(baseAlpha * cNorm * 3.5 * uChlIntensity, 0.0, 0.35);
        } else {
          // Mode 3: Multi-Variable Composite
          // 1. Base thermal oceanic coloring
          vec3 baseCol = colormapTemp(tNorm);
          // 2. Haline salinity shifts onto subsurface density
          vec3 salCol = colormapSalinity(sNorm);
          vec3 mixedCol = mix(baseCol, salCol, clamp(uSalinityWeight * 0.45 * sNorm, 0.0, 0.75));
          // 3. Emissive chlorophyll bloom veil in the upper euphotic layer (depth 0-200m)
          vec3 chlCol = colormapChlorophyll(cNorm);
          stepColor = mix(mixedCol, chlCol, clamp(cNorm * uChlIntensity * 0.85, 0.0, 0.95));
          stepAlpha = clamp(baseAlpha + (cNorm * uChlIntensity * 0.08), 0.005, 0.35);
        }

        accumulated.rgb += (1.0 - accumulated.a) * stepAlpha * stepColor;
        accumulated.a += (1.0 - accumulated.a) * stepAlpha;

        if (accumulated.a > 0.98) break;
      } else {
        vec4 landColor = vec4(0.02, 0.05, 0.14, 0.92 * uOpacity);
        float depthFactor = clamp(0.5 - pos.y, 0.0, 1.0); // 0.0 = surface, 1.0 = bottom
        landColor.rgb += vec3(0.01, 0.02, 0.04) * (1.0 - depthFactor);

        accumulated.rgb += landColor.rgb * landColor.a * (1.0 - accumulated.a);
        accumulated.a += landColor.a * (1.0 - accumulated.a);

        if (accumulated.a >= 0.98) break;
      }
    } else {
      // Single-channel legacy / scalar volume.
      // Land/NaN sentinel check: voxels with val < -9000.0 are land or no-data.
      // We deliberately avoid isnan() here because GLSL isnan() is unreliable
      // for half-float textures under ANGLE / D3D11 GPU drivers on Windows —
      // it often returns false for NaN half-float values, making land cells
      // render as solid deep-blue ocean. The JavaScript upload path converts
      // every NaN to -9999.0 before the float32→float16 step, so a simple
      // threshold comparison is both portable and correct.
      float val = sampleVal.r;
      if (val > -9000.0) {
        float norm = (val <= 1.05 && uTempMin >= 5.0)
          ? val
          : clamp((val - uTempMin) / max(uTempMax - uTempMin, 0.0001), 0.0, 1.0);
        vec3 col = (uRenderMode == 1) ? colormapSalinity(norm) :
                   (uRenderMode == 2) ? colormapChlorophyll(norm) : colormapTemp(norm);

        accumulated.rgb += (1.0 - accumulated.a) * baseAlpha * col;
        accumulated.a += (1.0 - accumulated.a) * baseAlpha;

        if (accumulated.a > 0.98) break;
      } else {
        vec4 landColor = vec4(0.02, 0.05, 0.14, 0.92 * uOpacity);
        float depthFactor = clamp(0.5 - pos.y, 0.0, 1.0); // 0.0 = surface, 1.0 = bottom
        landColor.rgb += vec3(0.01, 0.02, 0.04) * (1.0 - depthFactor);

        accumulated.rgb += landColor.rgb * landColor.a * (1.0 - accumulated.a);
        accumulated.a += landColor.a * (1.0 - accumulated.a);

        if (accumulated.a >= 0.98) break;
      }
    }

    pos += step;
  }

  if (accumulated.a < 0.001) discard;

  fragColor = vec4(accumulated.rgb, accumulated.a);
}
