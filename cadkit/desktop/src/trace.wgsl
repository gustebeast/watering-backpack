enable wgpu_ray_query;
//!include common
//!include tables

struct Part { idx_off: u32, vtx_off: u32, flags: u32, pad: u32, color: vec4f, mr: vec4f }
struct Vtx { nx: f32, ny: f32, nz: f32, col: u32 }

@group(0) @binding(0) var<uniform> G: Globals;
@group(0) @binding(1) var tlas: acceleration_structure;
@group(0) @binding(2) var<storage, read> parts: array<Part>;
@group(0) @binding(3) var<storage, read> indices: array<u32>;
@group(0) @binding(4) var<storage, read> verts: array<Vtx>;
// Each pixel's samples are kept in two heaps. Those that meet the surface the pixel's guide describes (same
// part, much the same normal; or a clear part in front of it, which the guide looks through) are kept with
// the surface colours they met, so the denoiser can smooth the LIGHT (their light over their colour) and
// leave the colour alone; the others (another part at an edge, a string thinner than the pixel) are kept as
// they came and are never smoothed: an edge is as sharp moving as at rest.
//   acc_a: rgb sum of the guide's samples' light, a how many they are
//   acc_b: rgb sum of the surface colours they met, a sum of their luminance
//   acc_c: rgb sum of the other samples' light, a sum of the squared luminance of the guide's
@group(0) @binding(5) var<storage, read_write> acc_a: array<vec4f>;
@group(0) @binding(6) var<storage, read_write> guide: array<Guide>;
@group(0) @binding(7) var<storage, read_write> acc_b: array<vec4f>;
@group(0) @binding(8) var<storage, read_write> acc_c: array<vec4f>;
// what the OTHER samples of the pixel met, as of the last restart: a part's index if they all met one part,
// OTHER_BACKDROP if all went past everything, OTHER_MIXED if they differ, OTHER_NONE if there were none
@group(0) @binding(9) var<storage, read_write> other_id: array<u32>;

// THE LIGHT IS THE BLENDER TRACER'S (cadkit/web/trace_blender.py), figure for figure: its room (bright
// below, as off a pale floor, dim overhead), its sun (0.03 rad across), its path lengths (4 bounces, at
// most 3 of them diffuse and 3 glossy), its clamp on what one sample may bring by way of a bounce (10), its
// pixel filter (Blackman-Harris, 1.5 px wide: a bell of 0.208 px standard deviation).
const MAX_BOUNCES = 4u;
const MAX_DIFFUSE = 3u;
const MAX_GLOSSY = 3u;
const SUN_COS_MAX = 0.99988750; // cos(0.015)
const SUN_INV_OMEGA = 1414.7;   // 1 / (2 pi (1 - SUN_COS_MAX)): the sun's radiance for unit strength
const ROOM_BELOW = vec3f(0.888, 0.913, 0.956);
const ROOM_ABOVE = vec3f(0.102, 0.117, 0.138);
const CLEAR_OPACITY = 0.38;
const INDIRECT_CLAMP = 10.0;
const FILTER_SD = 0.45;
const EPS = 0.004;
const SEL = vec3f(0.074, 0.367, 1.0); // the page's selection blue (#4da3ff), linear
// part flags
const F_VCOL = 1u;
const F_CLEAR = 2u;
const F_SEL = 4u;

var<private> rng: u32;
var<private> see_through: bool;   // the guide's ray: a clear part is always passed
var<private> veiled: bool;        // ... and it did pass one
var<private> was_spec: bool;      // which lobe sample_bsdf last drew from
fn pcg(v: u32) -> u32 {
  let s = v * 747796405u + 2891336453u;
  let w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
  return (w >> 22u) ^ w;
}
fn rand() -> f32 { rng = pcg(rng); return f32(rng >> 8u) * (1.0 / 16777216.0); }
fn rand2() -> vec2f { let a = rand(); let b = rand(); return vec2f(a, b); }

struct Hit { hit: bool, t: f32, part: u32, prim: u32, bary: vec2f, o2w: mat4x3f }

// A candidate hit is passed over (the ray goes on) when it lies on the cut side of the section plane, or,
// with a clear part, most of the time. Only clear parts are non-opaque geometry; with a section on, every
// triangle is made a candidate so the plane can be asked.
fn trace(o: vec3f, d: vec3f, tmin: f32, tmax: f32) -> Hit {
  let clip = (G.flags & 2u) != 0u;
  var rq: ray_query;
  rayQueryInitialize(&rq, tlas, RayDesc(select(RAY_FLAG_NONE, RAY_FLAG_FORCE_NO_OPAQUE, clip), 0xFFu, tmin, tmax, o, d));
  while (rayQueryProceed(&rq)) {
    let c = rayQueryGetCandidateIntersection(&rq);
    if (clip && dot(G.clip.xyz, o + d * c.t) + G.clip.w < 0.0) { continue; }
    if ((parts[c.instance_custom_data].flags & F_CLEAR) != 0u) {
      if (see_through) { veiled = true; continue; }
      if (rand() >= CLEAR_OPACITY) { continue; }
    }
    rayQueryConfirmIntersection(&rq);
  }
  let i = rayQueryGetCommittedIntersection(&rq);
  var h: Hit;
  h.hit = i.kind != RAY_QUERY_INTERSECTION_NONE;
  h.t = i.t; h.part = i.instance_custom_data; h.prim = i.primitive_index; h.bary = i.barycentrics;
  h.o2w = i.object_to_world;
  return h;
}

fn occluded(o: vec3f, d: vec3f) -> bool {
  let clip = (G.flags & 2u) != 0u;
  var rq: ray_query;
  rayQueryInitialize(&rq, tlas, RayDesc(RAY_FLAG_TERMINATE_ON_FIRST_HIT | select(RAY_FLAG_NONE, RAY_FLAG_FORCE_NO_OPAQUE, clip), 0xFFu, 0.0, 30000.0, o, d));
  while (rayQueryProceed(&rq)) {
    let c = rayQueryGetCandidateIntersection(&rq);
    if (clip && dot(G.clip.xyz, o + d * c.t) + G.clip.w < 0.0) { continue; }
    if ((parts[c.instance_custom_data].flags & F_CLEAR) != 0u && rand() >= CLEAR_OPACITY) { continue; }
    rayQueryConfirmIntersection(&rq);
  }
  let i = rayQueryGetCommittedIntersection(&rq);
  return i.kind != RAY_QUERY_INTERSECTION_NONE;
}

struct Surf { n: vec3f, base: vec3f, metal: f32, rough: f32, emit: vec3f }

fn surface(h: Hit) -> Surf {
  let p = parts[h.part];
  let io = p.idx_off + 3u * h.prim;
  let v0 = verts[indices[io] + p.vtx_off];
  let v1 = verts[indices[io + 1u] + p.vtx_off];
  let v2 = verts[indices[io + 2u] + p.vtx_off];
  let b = vec3f(1.0 - h.bary.x - h.bary.y, h.bary.x, h.bary.y);
  var s: Surf;
  // the normal is the part's own; a part the rig has moved is turned with it (poses are rigid)
  let nl = vec3f(v0.nx, v0.ny, v0.nz) * b.x + vec3f(v1.nx, v1.ny, v1.nz) * b.y + vec3f(v2.nx, v2.ny, v2.nz) * b.z;
  s.n = normalize(h.o2w * vec4f(nl, 0.0));
  s.base = p.color.rgb;
  s.metal = p.mr.x;
  s.rough = p.mr.y;
  s.emit = vec3f(0.0);
  if ((p.flags & F_VCOL) != 0u) {
    let c = unpack4x8unorm(v0.col) * b.x + unpack4x8unorm(v1.col) * b.y + unpack4x8unorm(v2.col) * b.z;
    s.base = s.base * c.rgb;
    s.metal = mix(1.0, p.mr.x, c.a);
    s.rough = mix(0.3, p.mr.y, c.a);
  }
  if ((p.flags & F_SEL) != 0u) {
    // a selected part: tinted towards the selection blue, and lit a little of itself so it reads in shadow
    s.base = mix(s.base, SEL, 0.55);
    s.metal = s.metal * 0.3;
    s.emit = SEL * 0.10;
  }
  return s;
}

// the room: bright below, dim overhead
fn sky(d: vec3f) -> vec3f { return mix(ROOM_BELOW, ROOM_ABOVE, d.z * 0.5 + 0.5); }
fn max3(v: vec3f) -> f32 { return max(v.x, max(v.y, v.z)); }

fn onb(n: vec3f) -> mat3x3f {
  let s = select(-1.0, 1.0, n.z >= 0.0);
  let a = -1.0 / (s + n.z);
  let b = n.x * n.y * a;
  return mat3x3f(vec3f(1.0 + s * n.x * n.x * a, s * b, -s * n.x), vec3f(b, s + n.y * n.y * a, -n.y), n);
}

fn g1(nx: f32, a2: f32) -> f32 { return 2.0 * nx / (nx + sqrt(a2 + (1.0 - a2) * nx * nx)); }
// Smith's lambda: masking and shadowing are taken together (height-correlated), as the reference takes them
fn lambda(nx: f32, a2: f32) -> f32 { return 0.5 * (sqrt(1.0 + a2 * (1.0 - nx * nx) / (nx * nx)) - 1.0); }

// THE SURFACE IS THE REFERENCE'S (Cycles' Principled BSDF, as trace_blender.py sets it: base colour, metallic,
// roughness, nothing else). A dielectric: a GGX gloss with the real Fresnel of index 1.5 over a Lambert
// diffuse that gets what the gloss, seen from here, did not take. A metal: a GGX lobe, Schlick from the base
// colour to white. Both lobes are given back what a rough lobe loses to its own shadowing ("multiscatter GGX").
fn tab_e(rough: f32, mu: f32) -> f32 {
  let x = clamp(rough, 0.0, 1.0) * f32(TAB_N - 1);
  let y = clamp(mu, 0.0, 1.0) * f32(TAB_N - 1);
  let i = min(i32(x), TAB_N - 2);
  let j = min(i32(y), TAB_N - 2);
  let fx = x - f32(i);
  let fy = y - f32(j);
  return mix(mix(TAB_E[i * TAB_N + j], TAB_E[i * TAB_N + j + 1], fy), mix(TAB_E[(i + 1) * TAB_N + j], TAB_E[(i + 1) * TAB_N + j + 1], fy), fx);
}
fn tab_ed(rough: f32, mu: f32) -> f32 {
  let x = clamp(rough, 0.0, 1.0) * f32(TAB_N - 1);
  let y = clamp(mu, 0.0, 1.0) * f32(TAB_N - 1);
  let i = min(i32(x), TAB_N - 2);
  let j = min(i32(y), TAB_N - 2);
  let fx = x - f32(i);
  let fy = y - f32(j);
  return mix(mix(TAB_ED[i * TAB_N + j], TAB_ED[i * TAB_N + j + 1], fy), mix(TAB_ED[(i + 1) * TAB_N + j], TAB_ED[(i + 1) * TAB_N + j + 1], fy), fx);
}
fn tab_eavg(rough: f32) -> f32 {
  let x = clamp(rough, 0.0, 1.0) * f32(TAB_N - 1);
  let i = min(i32(x), TAB_N - 2);
  return mix(TAB_EAVG[i], TAB_EAVG[i + 1], x - f32(i));
}
// unpolarised reflection off glass of index 1.5
fn fresnel_diel(c: f32) -> f32 {
  let g = sqrt(1.25 + c * c);
  let a = (g - c) / (g + c);
  let b = (c * (g + c) - 1.0) / (c * (g - c) + 1.0);
  return 0.5 * a * a * (1.0 + b * b);
}

// what of a surface depends on the view alone: found once per hit
struct Lobes {
  kd: f32,       // the dielectric gloss's gain (its lost light given back)
  km: vec3f,     // the metal lobe's
  under: f32,    // the share of light the gloss leaves for the diffuse under it
  ps: f32,       // the chance a bounce is drawn from the gloss
}
// `matte`: the path has already bounced off something diffusely. The reference then drops every gloss (its
// "reflective caustics" are off): a dielectric is its diffuse alone, a metal gives nothing back.
fn lobes(s: Surf, nv: f32, matte: bool) -> Lobes {
  if (matte) { return Lobes(0.0, vec3f(0.0), 1.0, 0.0); }
  let e = max(tab_e(s.rough, nv), 1e-3);
  let ea = tab_eavg(s.rough);
  let miss = (1.0 - e) / e;
  var l: Lobes;
  l.kd = 1.0 + miss * DIEL_FSS * ea / (1.0 - DIEL_FSS * (1.0 - ea));
  let fss = s.base + (1.0 - s.base) / 21.0;
  l.km = 1.0 + miss * fss * ea / (1.0 - fss * (1.0 - ea));
  let ed = tab_ed(s.rough, nv) * l.kd;
  l.under = 1.0 - ed;
  let fr = mix(ed, lum(s.base + (1.0 - s.base) * pow(1.0 - nv, 5.0)), s.metal);
  let di = lum(s.base) * (1.0 - s.metal) * l.under;
  l.ps = clamp(fr / max(fr + di, 1e-4), 0.05, 1.0);
  return l;
}

// rgb = f * cos, w = pdf of the mixture sampler
fn eval(s: Surf, lb: Lobes, n: vec3f, wo: vec3f, wi: vec3f) -> vec4f {
  let nl = dot(n, wi);
  let nv = dot(n, wo);
  if (nl <= 0.0 || nv <= 0.0) { return vec4f(0.0); }
  let h = normalize(wo + wi);
  let nh = dot(n, h);
  let vh = max(dot(wo, h), 0.0);
  let a = max(s.rough * s.rough, 0.003);
  let a2 = a * a;
  let dd = nh * nh * (a2 - 1.0) + 1.0;
  let D = a2 / (PI * dd * dd);
  let gv = g1(nv, a2);
  let F = mix(vec3f(fresnel_diel(vh) * lb.kd), (s.base + (1.0 - s.base) * pow(1.0 - vh, 5.0)) * lb.km, s.metal);
  let spec = F * (D / (4.0 * nv * nl * (1.0 + lambda(nv, a2) + lambda(nl, a2))));
  let diff = s.base * ((1.0 - s.metal) * lb.under / PI);
  let pdf = lb.ps * gv * D / (4.0 * nv) + (1.0 - lb.ps) * nl / PI;
  return vec4f((diff + spec) * nl, pdf);
}

fn sample_bsdf(s: Surf, lb: Lobes, n: vec3f, wo: vec3f) -> vec3f {
  let tbn = onb(n);
  let u = rand2();
  was_spec = rand() < lb.ps;
  if (was_spec) {
    let a = max(s.rough * s.rough, 0.003);
    let ve = vec3f(dot(wo, tbn[0]), dot(wo, tbn[1]), dot(wo, tbn[2]));
    let vh = normalize(vec3f(a * ve.x, a * ve.y, ve.z));
    let lensq = vh.x * vh.x + vh.y * vh.y;
    var t1 = vec3f(1.0, 0.0, 0.0);
    if (lensq > 1e-12) { t1 = vec3f(-vh.y, vh.x, 0.0) / sqrt(lensq); }
    let t2 = cross(vh, t1);
    let r = sqrt(u.x);
    let phi = 2.0 * PI * u.y;
    let p1 = r * cos(phi);
    var p2 = r * sin(phi);
    let sx = 0.5 * (1.0 + vh.z);
    p2 = (1.0 - sx) * sqrt(max(0.0, 1.0 - p1 * p1)) + sx * p2;
    let nh = p1 * t1 + p2 * t2 + sqrt(max(0.0, 1.0 - p1 * p1 - p2 * p2)) * vh;
    let hl = normalize(vec3f(a * nh.x, a * nh.y, max(0.0, nh.z)));
    let h = tbn * hl;
    return reflect(-wo, h);
  }
  let r = sqrt(u.x);
  let phi = 2.0 * PI * u.y;
  return tbn * vec3f(r * cos(phi), r * sin(phi), sqrt(max(0.0, 1.0 - u.x)));
}

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  if (gid.x >= G.size.x || gid.y >= G.size.y) { return; }
  let idx = gid.y * G.size.x + gid.x;
  rng = pcg(idx ^ pcg(G.frame * 0x9E3779B9u + 0x1234567u));
  let sun_dir = G.sun.xyz;
  let sun_tbn = onb(sun_dir);
  see_through = false;
  var g = guide[idx];
  if (G.reset != 0u) {
    // the guide: what stands at the pixel's centre, seen through whatever is clear. A ray of its own, so
    // that it is the same from frame to frame and no sample of the picture is spent on it.
    let d = ray_dir(vec2f(gid.xy) + 0.5, G.vsize, G.cam_r, G.cam_u, G.cam_f, G.cam_pos.w);
    see_through = true;
    veiled = false;
    let h = trace(G.cam_pos.xyz, d, G.near / max(dot(d, G.cam_f.xyz), 1e-3), 200000.0);
    see_through = false;
    // (the colour's fourth byte: 0 = a clear part stands in front)
    let veil = select(1.0, 0.0, veiled);
    g = Guide(0u, -1.0, pack4x8unorm(vec4f(1.0, 1.0, 1.0, veil)), 0xffffffffu);
    if (h.hit) {
      let s = surface(h);
      var n = s.n;
      if (dot(n, d) > 0.0) { n = -n; }
      g = Guide(oct_enc(n), h.t, pack4x8unorm(vec4f(max(s.base, vec3f(0.04)), veil)), h.part);
    }
    guide[idx] = g;
  }
  let g_n = oct_dec(g.n);
  let h0 = pcg(idx * 2u + 0x51ed27u);
  let px_shift = vec2f(f32(h0 >> 8u), f32(pcg(h0) >> 8u)) * (1.0 / 16777216.0);
  let g_veil = (g.albedo >> 24u) == 0u;
  var A = vec4f(0.0);
  var B = vec4f(0.0);
  var C = vec4f(0.0);
  var oid = OTHER_NONE;
  for (var si = 0u; si < G.spf; si++) {
    // where in the pixel: a bell round its centre (the pixel filter), by Box-Muller, from points that are
    // spread EVENLY over it (an R2 sequence, shifted per pixel, carried on from frame to frame at rest): a few
    // of them already give the share of the pixel an edge covers far better than as many thrown at random,
    // and while the picture moves each pixel uses the same few, so an edge does not shimmer
    let u0 = fract(px_shift + f32(G.n - G.spf + si + 1u) * vec2f(0.7548776662, 0.5698402910));
    let jit = vec2f(0.5) + clamp(FILTER_SD * sqrt(-2.0 * log(max(u0.x, 1e-7))) * vec2f(cos(2.0 * PI * u0.y), sin(2.0 * PI * u0.y)), vec2f(-1.5), vec2f(1.5));
    var o = G.cam_pos.xyz;
    var d = ray_dir(vec2f(gid.xy) + jit, G.vsize, G.cam_r, G.cam_u, G.cam_f, G.cam_pos.w);
    var thr = vec3f(1.0);
    var Ld = vec3f(0.0);   // what the eye sees lit at first hand
    var Li = vec3f(0.0);   // what comes by way of a bounce: clamped, as the reference clamps it
    var same = false;
    var met = OTHER_BACKDROP;
    var alb0 = vec3f(1.0);
    var nd = 0u;
    var ng = 0u;
    var p_b = 0.0;         // the chance the last bounce had of going the way it went
    // the page's near plane, as a distance along this ray
    var tmin = G.near / max(dot(d, G.cam_f.xyz), 1e-3);
    for (var b = 0u; b <= MAX_BOUNCES; b++) {
      let h = trace(o, d, tmin, 200000.0);
      if (!h.hit) {
        if (b == 0u) {
          Ld = G.bg.rgb;
          same = g.depth < 0.0;
        } else {
          var c = thr * sky(d);
          // the sun's disc, met by a bounce: shared with the sampling of the sun below by their chances
          if (dot(d, sun_dir) > SUN_COS_MAX) { c += thr * (G.sun.w * SUN_INV_OMEGA) * (p_b / (p_b + SUN_INV_OMEGA)); }
          if (b == 1u) { Ld += c; } else { Li += c; }
        }
        break;
      }
      let s = surface(h);
      let p = o + d * h.t;
      let wo = -d;
      var n = s.n;
      if (dot(n, wo) < 0.0) { n = -n; }
      if (b == 0u) {
        met = h.part;
        alb0 = max(s.base, vec3f(0.04));
        same = (g.depth >= 0.0 && h.part == g.id && dot(n, g_n) > 0.9) || (g_veil && (parts[h.part].flags & F_CLEAR) != 0u);
        Ld += s.emit;
      } else {
        Li += thr * s.emit;
      }
      let lb = lobes(s, dot(n, wo), nd > 0u);
      // the sun, sampled across its disc
      {
        let u = rand2();
        let cz = 1.0 - u.x * (1.0 - SUN_COS_MAX);
        let sz = sqrt(max(0.0, 1.0 - cz * cz));
        let ph = 2.0 * PI * u.y;
        let ld = sun_tbn * vec3f(sz * cos(ph), sz * sin(ph), cz);
        let e = eval(s, lb, n, wo, ld);
        if (e.w > 0.0) {
          if (!occluded(p + n * EPS, ld)) {
            let c = thr * e.rgb * G.sun.w * (SUN_INV_OMEGA / (SUN_INV_OMEGA + e.w));
            if (b == 0u) { Ld += c; } else { Li += c; }
          }
        }
      }
      if (b == MAX_BOUNCES) { break; }
      let wi = sample_bsdf(s, lb, n, wo);
      if (was_spec) { ng++; } else { nd++; }
      if (nd > MAX_DIFFUSE || ng > MAX_GLOSSY) { break; }
      let e = eval(s, lb, n, wo, wi);
      if (e.w <= 0.0) { break; }
      thr = min(thr * e.rgb / e.w, vec3f(64.0));
      p_b = e.w;
      if (b >= 1u) {
        let q = clamp(max3(thr), 0.05, 1.0);
        if (rand() >= q) { break; }
        thr /= q;
      }
      o = p + n * EPS;
      d = wi;
      tmin = 0.0;
    }
    let m = max3(Li);
    if (m > INDIRECT_CLAMP) { Li *= INDIRECT_CLAMP / m; }
    var L = Ld + Li;
    if (!(max3(L) < 1e4)) { L = vec3f(0.0); }      // (a sample that is not a number: left out)
    if (same) {
      let l = lum(L);
      A += vec4f(L, 1.0);
      B += vec4f(alb0, l);
      C.w += l * l;
    } else {
      C += vec4f(L, 0.0);
      if (oid == OTHER_NONE) { oid = met; } else if (oid != met) { oid = OTHER_MIXED; }
    }
  }
  if (G.reset != 0u) { other_id[idx] = oid; }
  if (G.reset == 0u) { A += acc_a[idx]; B += acc_b[idx]; C += acc_c[idx]; }
  acc_a[idx] = A; acc_b[idx] = B; acc_c[idx] = C;
}
