varying vec3 vLocalPosition; // box-local position, range [-0.5, 0.5] per axis
varying vec3 vWorldCameraLocal; // camera position transformed into box-local space

void main() {
  vLocalPosition = position;

  // camera position in world space -> object (local) space
  mat4 invModel = inverse(modelMatrix);
  vec4 camLocal = invModel * vec4(cameraPosition, 1.0);
  vWorldCameraLocal = camLocal.xyz;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
