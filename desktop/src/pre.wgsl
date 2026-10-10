//!include common
// Builds the denoiser's input: the light on the guide's surface with its colour divided out (rgb), and how
// far that figure can be trusted: the variance of its luminance (a), measured from the samples themselves.
// mode 0: this picture's samples alone.
// mode 1: with the last frame's, found again where each surface point WAS: the camera's last place, and, for
//         a part the rig is moving, that part's last place (motion[part] takes a point from now to then).
// mode 2: at rest: the samples so far, with the last moving frame's history as a prior that fades.

struct Hist { c: vec4f, v: vec4f }      // c: rgb light / colour, a frames of history; v.x: variance
struct Mot { r0: vec4f, r1: vec4f, r2: vec4f }

@group(0) @binding(0) var<uniform> G: Globals;
@group(0) @binding(1) var<storage, read> acc_a: array<vec4f>;
@group(0) @binding(2) var<storage, read> guide: array<Guide>;
@group(0) @binding(3) var<storage, read> guide_prev: array<Guide>;
@group(0) @binding(4) var<storage, read> hist_prev: array<Hist>;
@group(0) @binding(5) var<storage, read_write> hist: array<Hist>;
@group(0) @binding(6) var<storage, read_write> dst: array<vec4f>;
@group(0) @binding(7) var<storage, read> acc_b: array<vec4f>;
@group(0) @binding(8) var<storage, read> acc_c: array<vec4f>;
@group(0) @binding(9) var<storage, read> motion: array<Mot>;

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  if (gid.x >= G.size.x || gid.y >= G.size.y) { return; }
  let idx = gid.y * G.size.x + gid.x;
  let g = guide[idx];
  let a = acc_a[idx];
  let b = acc_b[idx];
  if (g.depth < 0.0 || a.w < 0.5) {
    dst[idx] = vec4f(a.rgb / max(b.rgb, vec3f(1e-6)), 0.0);
    if (G.mode == 1u) { hist[idx] = Hist(vec4f(0.0), vec4f(0.0)); }
    return;
  }
  // the light: the samples' light over the colours they met (so light x colour is their mean exactly)
  var cur = a.rgb / b.rgb;
  let ml = b.w / a.w;
  // the variance of the mean: of one sample nothing is known, so it is taken to be as uncertain as it is bright
  var v = ml * ml;
  if (a.w > 1.5) { v = max(acc_c[idx].w - a.w * ml * ml, 0.0) / ((a.w - 1.0) * a.w); }
  let la = lum(b.rgb) / a.w;
  v = v / (la * la);
  if (a.w <= 8.0) {
    // firefly clamp: no brighter than the brightest of the 8 neighbours
    var mx = 0.0;
    for (var k = 0; k < 9; k++) {
      if (k == 4) { continue; }
      let q = vec2i(gid.xy) + vec2i(k % 3 - 1, k / 3 - 1);
      if (q.x < 0 || q.y < 0 || q.x >= i32(G.size.x) || q.y >= i32(G.size.y)) { continue; }
      let qi = u32(q.y) * G.size.x + u32(q.x);
      let aq = acc_a[qi];
      if (guide[qi].depth < 0.0 || aq.w < 0.5) { continue; }
      mx = max(mx, lum(aq.rgb / acc_b[qi].rgb));
    }
    let lc = lum(cur);
    if (lc > mx && mx > 0.0) { cur *= mx / lc; }
  }
  if (G.mode == 0u) {
    dst[idx] = vec4f(cur, v);
    return;
  }
  if (G.mode == 2u) {
    let h = hist[idx];
    let w = G.hist_w * min(h.c.w, 8.0) / 8.0;
    let nn = a.w;
    dst[idx] = vec4f((cur * nn + h.c.rgb * w) / (nn + w), (v * nn * nn + h.v.x * w * w) / ((nn + w) * (nn + w)));
    return;
  }
  // mode 1: where was this point a frame ago?
  let n = oct_dec(g.n);
  let p = G.cam_pos.xyz + ray_dir(vec2f(gid.xy) + 0.5, G.vsize, G.cam_r, G.cam_u, G.cam_f, G.cam_pos.w) * g.depth;
  let m = motion[g.id];
  let pw = vec3f(dot(m.r0.xyz, p) + m.r0.w, dot(m.r1.xyz, p) + m.r1.w, dot(m.r2.xyz, p) + m.r2.w);
  let nw = vec3f(dot(m.r0.xyz, n), dot(m.r1.xyz, n), dot(m.r2.xyz, n));
  let d = pw - G.prev_pos.xyz;
  let z = dot(d, G.prev_f.xyz);
  var sum = vec4f(0.0);
  var vsum = 0.0;
  var wsum = 0.0;
  if (z > 0.0) {
    let ndc = vec2f(dot(d, G.prev_r.xyz) / (z * G.prev_r.w), dot(d, G.prev_u.xyz) / (z * G.prev_pos.w));
    let pp = vec2f((ndc.x * 0.5 + 0.5) * G.vsize.x, (0.5 - ndc.y * 0.5) * G.vsize.y) - 0.5;
    let base = floor(pp);
    let fr = pp - base;
    let dist = length(d);
    for (var k = 0; k < 4; k++) {
      let o = vec2i(k & 1, k >> 1);
      let q = vec2i(base) + o;
      if (q.x < 0 || q.y < 0 || q.x >= i32(G.size.x) || q.y >= i32(G.size.y)) { continue; }
      let qi = u32(q.y) * G.size.x + u32(q.x);
      let gp = guide_prev[qi];
      if (gp.id != g.id || gp.depth < 0.0) { continue; }
      if (abs(gp.depth - dist) > 0.01 * dist + 0.3) { continue; }
      if (dot(oct_dec(gp.n), nw) < 0.9) { continue; }
      let hq = hist_prev[qi];
      if (hq.c.w < 0.5) { continue; }
      let w = select(1.0 - fr.x, fr.x, o.x == 1) * select(1.0 - fr.y, fr.y, o.y == 1);
      sum += hq.c * w;
      vsum += hq.v.x * w;
      wsum += w;
    }
  }
  var len = 0.0;
  var hc = vec3f(0.0);
  var hv = 0.0;
  if (wsum > 0.01) { hc = sum.rgb / wsum; len = sum.w / wsum; hv = vsum / wsum; }
  len = min(len + 1.0, G.max_hist);
  let al = 1.0 / len;
  let outc = mix(hc, cur, al);
  let outv = (1.0 - al) * (1.0 - al) * hv + al * al * v;
  hist[idx] = Hist(vec4f(outc, len), vec4f(outv, 0.0, 0.0, 0.0));
  dst[idx] = vec4f(outc, outv);
}
