struct Globals {
  cam_pos: vec4f,   // xyz eye, w = tan(half fov y)
  cam_r: vec4f,     // xyz right, w = tan(half fov x)
  cam_u: vec4f,
  cam_f: vec4f,
  prev_pos: vec4f,
  prev_r: vec4f,
  prev_u: vec4f,
  prev_f: vec4f,
  size: vec2u,
  frame: u32,
  n: u32,           // samples in accum after the trace of this frame
  reset: u32,
  mode: u32,        // pre pass: 0 plain, 1 temporal reprojection, 2 still with history prior
  spf: u32,
  flags: u32,       // bit0: resolve raw (no denoise), bit1: section cut on, bit3: the surface wants linear values
  denoise: f32,     // 1 = fully denoised, 0 = raw accumulation
  hist_w: f32,
  max_hist: f32,
  near: f32,        // the page camera's near plane
  surf: vec2u,
  vsize: vec2f,     // the size the PAGE projects onto, device px (its canvas may be a pixel larger than ours)
  sun: vec4f,       // xyz towards the sun (CAD frame), w strength
  bg: vec4f,        // backdrop, linear
  clip: vec4f,      // section plane: kept where dot(xyz, p) + w >= 0
  off: vec2u,       // where on the surface the picture's first pixel is (the tabbed app: below its tab strip)
  pad: vec2u,
}

struct Guide {
  n: u32,       // octahedral normal 16+16
  depth: f32,   // ray distance of first hit; < 0 = background
  albedo: u32,  // rgba8 demodulation albedo
  id: u32,      // part index
}

const PI = 3.14159265358979;
const OTHER_NONE = 0xffffffffu;
const OTHER_MIXED = 0xfffffffeu;
const OTHER_BACKDROP = 0xfffffffdu;

fn oct_wrap(v: vec2f) -> vec2f {
  return (1.0 - abs(v.yx)) * select(vec2f(-1.0), vec2f(1.0), v.xy >= vec2f(0.0));
}
fn oct_enc(n_in: vec3f) -> u32 {
  let n = n_in / (abs(n_in.x) + abs(n_in.y) + abs(n_in.z));
  var o = n.xy;
  if (n.z < 0.0) { o = oct_wrap(o); }
  let q = vec2u(round(clamp(o * 0.5 + 0.5, vec2f(0.0), vec2f(1.0)) * 65535.0));
  return q.x | (q.y << 16u);
}
fn oct_dec(e: u32) -> vec3f {
  let f = vec2f(f32(e & 0xffffu), f32(e >> 16u)) / 65535.0 * 2.0 - 1.0;
  var n = vec3f(f.x, f.y, 1.0 - abs(f.x) - abs(f.y));
  if (n.z < 0.0) { let w = oct_wrap(n.xy); n.x = w.x; n.y = w.y; }
  return normalize(n);
}
fn lum(c: vec3f) -> f32 { return dot(c, vec3f(0.2126, 0.7152, 0.0722)); }

fn ray_dir(px: vec2f, size: vec2f, r: vec4f, u: vec4f, f: vec4f, tany: f32) -> vec3f {
  let ndc = vec2f(px.x / size.x * 2.0 - 1.0, 1.0 - px.y / size.y * 2.0);
  return normalize(f.xyz + r.xyz * (ndc.x * r.w) + u.xyz * (ndc.y * tany));
}
