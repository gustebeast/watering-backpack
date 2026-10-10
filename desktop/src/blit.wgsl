//!include common
@group(0) @binding(0) var<uniform> G: Globals;
@group(0) @binding(1) var<storage, read> outp: array<u32>;

@vertex
fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  let p = vec2f(f32((i << 1u) & 2u), f32(i & 2u));
  return vec4f(p * 2.0 - 1.0, 0.0, 1.0);
}

@fragment
fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let uv = (pos.xy - vec2f(G.off)) / vec2f(G.surf);
  let q = min(vec2u(uv * vec2f(G.size)), G.size - 1u);
  let c = unpack4x8unorm(outp[q.y * G.size.x + q.x]).rgb;
  // (flags bit 3: the surface encodes sRGB itself, so it is handed the linear value)
  if ((G.flags & 8u) != 0u) { return vec4f(select(pow((c + 0.055) / 1.055, vec3f(2.4)), c / 12.92, c <= vec3f(0.04045)), 1.0); }
  // (flags bit 4: what shows the surface decodes it with a plain 2.4 power, not the sRGB curve: encoded to suit)
  if ((G.flags & 16u) != 0u) { return vec4f(pow(select(pow((c + 0.055) / 1.055, vec3f(2.4)), c / 12.92, c <= vec3f(0.04045)), vec3f(1.0 / 2.4)), 1.0); }
  return vec4f(c, 1.0);
}
