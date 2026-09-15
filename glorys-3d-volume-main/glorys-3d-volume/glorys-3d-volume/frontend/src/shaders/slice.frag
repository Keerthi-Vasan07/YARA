precision highp float;
precision highp sampler3D;

varying vec2 vUv;

out vec4 fragColor;

uniform sampler3D uVolume; // s = longitude, t = latitude, r = depth
uniform float uTempMin;
uniform float uTempMax;
uniform float uSliceDepth; // normalized [0,1] index along texture r-axis

uniform int uRenderMode;         // 0: Temperature, 1: Salinity, 2: Chlorophyll, 3: Composite
uniform float uChlIntensity;     // Intensity scalar for chlorophyll
uniform float uSalinityWeight;   // Weight scalar for salinity
uniform int uIsMultiChannel;     // 1 if RGBA, 0 if single channel R

// 1. Temperature colormap
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

// 2. Salinity Colormap (Haline)
vec3 colormapSalinity(float s) {
  s = clamp(s, 0.0, 1.0);
  vec3 c0 = vec3(0.00, 0.92, 0.96); // low salinity cyan
  vec3 c1 = vec3(0.15, 0.55, 0.95); // oceanic blue
  vec3 c2 = vec3(0.60, 0.20, 0.88); // violet
  vec3 c3 = vec3(0.48, 0.03, 0.52); // deep purple / magenta

  if (s < 0.33) return mix(c0, c1, s / 0.33);
  if (s < 0.66) return mix(c1, c2, (s - 0.33) / 0.33);
  return mix(c2, c3, (s - 0.66) / 0.34);
}

// 3. Chlorophyll Colormap
vec3 colormapChlorophyll(float c) {
  c = clamp(c, 0.0, 1.0);
  vec3 c0 = vec3(0.04, 0.25, 0.18);
  vec3 c1 = vec3(0.08, 0.72, 0.35);
  vec3 c2 = vec3(0.00, 1.00, 0.40);

  if (c < 0.5) return mix(c0, c1, c / 0.5);
  return mix(c1, c2, (c - 0.5) / 0.5);
}

void main() {
  // plane UV: u = longitude, v = latitude
  vec3 texCoord = vec3(vUv.x, vUv.y, uSliceDepth);
  vec4 sampleVal = texture(uVolume, texCoord);

  if (uIsMultiChannel == 1) {
    float valid = sampleVal.a;
    if (valid < 0.5) discard;

    float tNorm = (sampleVal.r <= 1.05 && uTempMin >= 5.0)
      ? sampleVal.r
      : clamp((sampleVal.r - uTempMin) / max(uTempMax - uTempMin, 0.0001), 0.0, 1.0);
    float sNorm = sampleVal.g;
    float cNorm = sampleVal.b;

    vec3 finalColor;
    if (uRenderMode == 0) {
      finalColor = colormapTemp(tNorm);
    } else if (uRenderMode == 1) {
      finalColor = colormapSalinity(sNorm);
    } else if (uRenderMode == 2) {
      finalColor = colormapChlorophyll(cNorm);
    } else {
      vec3 baseCol = colormapTemp(tNorm);
      vec3 salCol = colormapSalinity(sNorm);
      vec3 mixedCol = mix(baseCol, salCol, clamp(uSalinityWeight * 0.45 * sNorm, 0.0, 0.75));
      vec3 chlCol = colormapChlorophyll(cNorm);
      finalColor = mix(mixedCol, chlCol, clamp(cNorm * uChlIntensity * 0.85, 0.0, 0.95));
    }
    fragColor = vec4(finalColor, 1.0);
  } else {
    float value = sampleVal.r;
    // Land/NaN sentinel check — see volume.frag for full explanation.
    // isnan() is unreliable on half-float textures under ANGLE/D3D11.
    // VolumeViewer stamps NaN cells as -9999.0 before upload, so we
    // detect land by threshold rather than isnan().
    if (value < -9000.0) discard;

    float norm = (value <= 1.05 && uTempMin >= 5.0)
      ? value
      : clamp((value - uTempMin) / max(uTempMax - uTempMin, 0.0001), 0.0, 1.0);
    vec3 col = (uRenderMode == 1) ? colormapSalinity(norm) :
               (uRenderMode == 2) ? colormapChlorophyll(norm) : colormapTemp(norm);
    fragColor = vec4(col, 1.0);
  }
}
