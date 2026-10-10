//!include common
// One pass of an edge-avoiding a-trous wavelet filter (5x5 B3 spline, holes = step), guided by variance:
// two pixels are blended as far as their difference could be noise (it is measured against the standard
// deviation the samples themselves showed), so a noisy patch is smoothed hard, and a contact shadow that
// the samples agree on is left alone. As the samples pile up the variance falls and the filter lets go by
// itself. rgb: light with the surface colour divided out; a: the variance of its luminance.

struct PassP { step: i32, sigma_l: f32, pad0: f32, pad1: f32 }

@group(0) @binding(0) var<uniform> G: Globals;
@group(0) @binding(1) var<uniform> P: PassP;
@group(0) @binding(2) var<storage, read> guide: array<Guide>;
@group(0) @binding(3) var<storage, read> src: array<vec4f>;
@group(0) @binding(4) var<storage, read_write> dst: array<vec4f>;

const KERN = array<f32, 3>(0.375, 0.25, 0.0625);
const G3 = array<f32, 2>(0.5, 0.25);

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  if (gid.x >= G.size.x || gid.y >= G.size.y) { return; }
  let idx = gid.y * G.size.x + gid.x;
  let g = guide[idx];
  let c = src[idx];
  if (g.depth < 0.0) { dst[idx] = c; return; }
  let n = oct_dec(g.n);
  let alb = unpack4x8unorm(g.albedo).rgb;
  let p = ray_dir(vec2f(gid.xy) + 0.5, G.vsize, G.cam_r, G.cam_u, G.cam_f, G.cam_pos.w) * g.depth;
  let lc = lum(c.rgb);
  let pix = 2.0 * G.cam_pos.w / G.vsize.y;
  let inv_sp = 1.0 / (g.depth * pix * f32(P.step) * 0.75 + 0.02);
  // the variance here, smoothed over the 3x3 round (one pixel's own figure is itself a noisy estimate)
  var vs = 0.0;
  var vw = 0.0;
  for (var dy = -1; dy <= 1; dy++) {
    for (var dx = -1; dx <= 1; dx++) {
      let q = vec2i(gid.xy) + vec2i(dx, dy);
      if (q.x < 0 || q.y < 0 || q.x >= i32(G.size.x) || q.y >= i32(G.size.y)) { continue; }
      let qi = u32(q.y) * G.size.x + u32(q.x);
      if (guide[qi].depth < 0.0) { continue; }
      let w = G3[abs(dx)] * G3[abs(dy)];
      vs += src[qi].a * w;
      vw += w;
    }
  }
  let inv_sl = 1.0 / (P.sigma_l * sqrt(max(vs / vw, 0.0)) + 1e-5);
  var sum = c.rgb * (KERN[0] * KERN[0]);
  var var_sum = c.a * (KERN[0] * KERN[0]) * (KERN[0] * KERN[0]);
  var wsum = KERN[0] * KERN[0];
  for (var dy = -2; dy <= 2; dy++) {
    for (var dx = -2; dx <= 2; dx++) {
      if (dx == 0 && dy == 0) { continue; }
      let q = vec2i(gid.xy) + vec2i(dx, dy) * P.step;
      if (q.x < 0 || q.y < 0 || q.x >= i32(G.size.x) || q.y >= i32(G.size.y)) { continue; }
      let qi = u32(q.y) * G.size.x + u32(q.x);
      let gq = guide[qi];
      if (gq.depth < 0.0) { continue; }
      let nq = oct_dec(gq.n);
      let wn = pow(max(dot(n, nq), 0.0), 48.0);
      if (wn < 1e-3) { continue; }
      let pq = ray_dir(vec2f(q) + 0.5, G.vsize, G.cam_r, G.cam_u, G.cam_f, G.cam_pos.w) * gq.depth;
      let wp = exp(-abs(dot(n, pq - p)) * inv_sp);
      let da = unpack4x8unorm(gq.albedo).rgb - alb;
      let wa = exp(-dot(da, da) * 60.0);
      let cq = src[qi];
      let wl = exp(-abs(lum(cq.rgb) - lc) * inv_sl);
      let w = KERN[abs(dx)] * KERN[abs(dy)] * wn * wp * wa * wl;
      sum += cq.rgb * w;
      var_sum += cq.a * w * w;
      wsum += w;
    }
  }
  dst[idx] = vec4f(sum / wsum, var_sum / (wsum * wsum));
}
