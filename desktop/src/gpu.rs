//! wgpu renderer: per-part BLAS + one TLAS (an instance per part, each with its own transform), compute path
//! tracer, a-trous denoiser. The model can be replaced while it runs.
use crate::scene::{FLAG_SEL, GpuPart, Scene};
use bytemuck::{Pod, Zeroable};
use glam::Vec3;
use std::time::Instant;
use wgpu::util::DeviceExt;

/// Where a picture at rest stops. (With the last light denoise it is then as clean as the reference's.)
pub const MAX_SPP: u32 = 1024;
/// The most samples a pixel is given in one frame.
pub const MAX_SPF: u32 = 64;
pub const ATROUS_PASSES: usize = 5;
pub const IDENT: [f32; 12] = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0];

/// A camera in the CAD frame (Z up): where it is, its right / up / forward, the vertical field of view.
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Camera {
    pub eye: Vec3,
    pub r: Vec3,
    pub u: Vec3,
    pub f: Vec3,
    pub tan_y: f32,
    pub near: f32,
}

/// The page's matrices are three.js's: column-major, Y up, the model turned -90 deg about X at its root.
/// The model here is as the CAD drew it, so a page matrix M becomes C @ M, C = [[1,0,0],[0,0,-1],[0,1,0]].
/// Returns the 3x4 rows of C @ M.
pub fn page_to_cad(m: &[f32; 16]) -> [f32; 12] {
    let e = |r: usize, c: usize| m[c * 4 + r];
    [e(0, 0), e(0, 1), e(0, 2), e(0, 3), -e(2, 0), -e(2, 1), -e(2, 2), -e(2, 3), e(1, 0), e(1, 1), e(1, 2), e(1, 3)]
}

impl Camera {
    /// From the page camera's matrixWorld (it looks down its own -Z).
    pub fn from_page(m: &[f32; 16], fov_deg: f32, near: f32) -> Camera {
        let a = page_to_cad(m);
        let col = |c: usize| Vec3::new(a[c], a[4 + c], a[8 + c]);
        Camera { eye: col(3), r: col(0).normalize(), u: col(1).normalize(), f: -col(2).normalize(), tan_y: (fov_deg.to_radians() * 0.5).tan(), near }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable, Default)]
struct Globals {
    cam_pos: [f32; 4],
    cam_r: [f32; 4],
    cam_u: [f32; 4],
    cam_f: [f32; 4],
    prev_pos: [f32; 4],
    prev_r: [f32; 4],
    prev_u: [f32; 4],
    prev_f: [f32; 4],
    size: [u32; 2],
    frame: u32,
    n: u32,
    reset: u32,
    mode: u32,
    spf: u32,
    flags: u32,
    denoise: f32,
    hist_w: f32,
    max_hist: f32,
    near: f32,
    surf: [u32; 2],
    vsize: [f32; 2],
    sun: [f32; 4],
    bg: [f32; 4],
    clip: [f32; 4],
}

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
struct PassP {
    step: i32,
    sigma_l: f32,
    pad: [f32; 2],
}

#[derive(Clone, Copy)]
pub struct Settings {
    pub denoise: bool,
    pub temporal: bool,
    pub spf_moving: u32,
    pub spf_still: u32,
    /// > 0: while moving, raise samples per frame until a frame costs about this much GPU time
    pub budget_ms: f32,
    pub max_hist: f32,
    /// how many standard deviations of the samples' own noise two pixels may differ by and still be blended
    pub sigma_l: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { denoise: true, temporal: false, spf_moving: 1, spf_still: 1, budget_ms: 0.0, max_hist: 16.0, sigma_l: 4.0 }
    }
}

/// What the page says about the light and the cut. All in the CAD frame.
#[derive(Clone, Copy, PartialEq)]
pub struct Look {
    pub sun: Vec3,
    pub sun_strength: f32,
    /// backdrop, linear
    pub bg: [f32; 3],
    /// section plane [nx, ny, nz, c]: kept where n.p + c >= 0
    pub clip: Option<[f32; 4]>,
    /// the size the page projects onto (device px); None = the picture's own size
    pub vsize: Option<(f32, f32)>,
}

impl Default for Look {
    fn default() -> Self {
        Look { sun: Vec3::new(3.0, -2.0, 4.0).normalize(), sun_strength: 2.4, bg: [0.00802, 0.00913, 0.01161], clip: None, vsize: None }
    }
}

struct Targets {
    w: u32,
    h: u32,
    out_px: wgpu::Buffer,
    staging: wgpu::Buffer,
    guide: [wgpu::Buffer; 2],
    guide_staging: wgpu::Buffer,
    bg_trace: [wgpu::BindGroup; 2],
    bg_pre: [wgpu::BindGroup; 2],
    bg_atrous: [[wgpu::BindGroup; ATROUS_PASSES]; 2],
    bg_resolve: [wgpu::BindGroup; 2],
    bg_blit: wgpu::BindGroup,
}

/// The model on the card.
struct SceneGpu {
    parts_buf: wgpu::Buffer,
    idx_buf: wgpu::Buffer,
    vattr_buf: wgpu::Buffer,
    blases: Vec<wgpu::Blas>,
    tlas: wgpu::Tlas,
    parts: Vec<GpuPart>,
    xf: Vec<[f32; 12]>,
    /// where each part stood in the last frame drawn, and whether any has moved since
    xf_prev: Vec<[f32; 12]>,
    xf_moved: bool,
    /// per part, 3x4 rows: takes a point from where the part is to where it was a frame ago
    motion_buf: wgpu::Buffer,
    motion_live: bool,
    hidden: Vec<bool>,
    tlas_dirty: bool,
    parts_dirty: bool,
}

pub struct Renderer {
    pub device: wgpu::Device,
    pub queue: wgpu::Queue,
    globals: wgpu::Buffer,
    pass_bufs: Vec<wgpu::Buffer>,
    scene: Option<SceneGpu>,
    l_trace: wgpu::BindGroupLayout,
    l_pre: wgpu::BindGroupLayout,
    l_atrous: wgpu::BindGroupLayout,
    l_resolve: wgpu::BindGroupLayout,
    l_blit: wgpu::BindGroupLayout,
    p_trace: wgpu::ComputePipeline,
    p_pre: wgpu::ComputePipeline,
    p_atrous: wgpu::ComputePipeline,
    p_resolve: wgpu::ComputePipeline,
    p_blit: wgpu::RenderPipeline,
    targets: Option<Targets>,
    size: (u32, u32),
    pub settings: Settings,
    pub look: Look,
    /// work done, for the proof that a picture at rest costs nothing: frames traced, compute dispatches
    pub n_renders: u64,
    pub n_dispatches: u64,
    /// the surface encodes sRGB itself (an ...Srgb format): hand it linear values
    pub linear_out: bool,
    /// what shows the surface decodes it with a plain 2.4 power (Vulkan on an HDR desktop): encode to suit
    pub power_out: bool,
    pub n: u32,
    frame: u32,
    parity: usize,
    prev_cam: Option<Camera>,
    last_globals: Globals,
}

fn shader(device: &wgpu::Device, name: &str, src: &str) -> wgpu::ShaderModule {
    let src = src.replace("//!include common", include_str!("common.wgsl")).replace("//!include tables", include_str!("tables.wgsl"));
    device.create_shader_module(wgpu::ShaderModuleDescriptor { label: Some(name), source: wgpu::ShaderSource::Wgsl(src.into()) })
}

fn e_buf(binding: u32, ty: wgpu::BufferBindingType, vis: wgpu::ShaderStages) -> wgpu::BindGroupLayoutEntry {
    wgpu::BindGroupLayoutEntry { binding, visibility: vis, ty: wgpu::BindingType::Buffer { ty, has_dynamic_offset: false, min_binding_size: None }, count: None }
}
const UNI: wgpu::BufferBindingType = wgpu::BufferBindingType::Uniform;
const RO: wgpu::BufferBindingType = wgpu::BufferBindingType::Storage { read_only: true };
const RW: wgpu::BufferBindingType = wgpu::BufferBindingType::Storage { read_only: false };

fn layout(device: &wgpu::Device, label: &str, entries: &[wgpu::BindGroupLayoutEntry]) -> wgpu::BindGroupLayout {
    device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: Some(label), entries })
}

fn compute_pipeline(device: &wgpu::Device, label: &str, l: &wgpu::BindGroupLayout, m: &wgpu::ShaderModule) -> wgpu::ComputePipeline {
    let pl = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: Some(label), bind_group_layouts: &[Some(l)], immediate_size: 0 });
    device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: Some(label),
        layout: Some(&pl),
        module: m,
        entry_point: Some("main"),
        compilation_options: Default::default(),
        cache: None,
    })
}

fn bind(device: &wgpu::Device, l: &wgpu::BindGroupLayout, res: &[wgpu::BindingResource]) -> wgpu::BindGroup {
    let entries: Vec<_> = res.iter().enumerate().map(|(i, r)| wgpu::BindGroupEntry { binding: i as u32, resource: r.clone() }).collect();
    device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: l, entries: &entries })
}

fn basis(c: &Camera, aspect: f32) -> ([f32; 4], [f32; 4], [f32; 4], [f32; 4]) {
    ([c.eye.x, c.eye.y, c.eye.z, c.tan_y], [c.r.x, c.r.y, c.r.z, c.tan_y * aspect], [c.u.x, c.u.y, c.u.z, 0.0], [c.f.x, c.f.y, c.f.z, 0.0])
}

pub fn srgb_to_linear(v: f32) -> f32 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}

pub fn linear_to_srgb(v: f32) -> f32 {
    let v = v.clamp(0.0, 1.0);
    if v <= 0.0031308 { v * 12.92 } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 }
}

impl Renderer {
    pub fn new(device: wgpu::Device, queue: wgpu::Queue, surface_format: wgpu::TextureFormat) -> Self {
        let c = wgpu::ShaderStages::COMPUTE;
        let l_trace = layout(
            &device,
            "trace",
            &[
                e_buf(0, UNI, c),
                wgpu::BindGroupLayoutEntry { binding: 1, visibility: c, ty: wgpu::BindingType::AccelerationStructure { vertex_return: false }, count: None },
                e_buf(2, RO, c),
                e_buf(3, RO, c),
                e_buf(4, RO, c),
                e_buf(5, RW, c),
                e_buf(6, RW, c),
                e_buf(7, RW, c),
                e_buf(8, RW, c),
                e_buf(9, RW, c),
            ],
        );
        let l_pre = layout(&device, "pre", &[e_buf(0, UNI, c), e_buf(1, RO, c), e_buf(2, RO, c), e_buf(3, RO, c), e_buf(4, RO, c), e_buf(5, RW, c), e_buf(6, RW, c), e_buf(7, RO, c), e_buf(8, RO, c), e_buf(9, RO, c)]);
        let l_atrous = layout(&device, "atrous", &[e_buf(0, UNI, c), e_buf(1, UNI, c), e_buf(2, RO, c), e_buf(3, RO, c), e_buf(4, RW, c)]);
        let l_resolve = layout(&device, "resolve", &[e_buf(0, UNI, c), e_buf(1, RO, c), e_buf(2, RO, c), e_buf(3, RO, c), e_buf(4, RW, c), e_buf(5, RO, c), e_buf(6, RO, c), e_buf(7, RO, c)]);
        let f = wgpu::ShaderStages::FRAGMENT;
        let l_blit = layout(&device, "blit", &[e_buf(0, UNI, f), e_buf(1, RO, f)]);

        let p_trace = compute_pipeline(&device, "trace", &l_trace, &shader(&device, "trace", include_str!("trace.wgsl")));
        let p_pre = compute_pipeline(&device, "pre", &l_pre, &shader(&device, "pre", include_str!("pre.wgsl")));
        let p_atrous = compute_pipeline(&device, "atrous", &l_atrous, &shader(&device, "atrous", include_str!("atrous.wgsl")));
        let p_resolve = compute_pipeline(&device, "resolve", &l_resolve, &shader(&device, "resolve", include_str!("resolve.wgsl")));
        let m_blit = shader(&device, "blit", include_str!("blit.wgsl"));
        let pl_blit = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: None, bind_group_layouts: &[Some(&l_blit)], immediate_size: 0 });
        let p_blit = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("blit"),
            layout: Some(&pl_blit),
            vertex: wgpu::VertexState { module: &m_blit, entry_point: Some("vs"), compilation_options: Default::default(), buffers: &[] },
            primitive: Default::default(),
            depth_stencil: None,
            multisample: Default::default(),
            fragment: Some(wgpu::FragmentState { module: &m_blit, entry_point: Some("fs"), compilation_options: Default::default(), targets: &[Some(surface_format.into())] }),
            multiview_mask: None,
            cache: None,
        });

        let globals = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("globals"),
            size: std::mem::size_of::<Globals>() as u64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let pass_bufs = (0..ATROUS_PASSES)
            .map(|_| device.create_buffer(&wgpu::BufferDescriptor { label: Some("passp"), size: 16, usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST, mapped_at_creation: false }))
            .collect();

        Renderer {
            device,
            queue,
            globals,
            pass_bufs,
            scene: None,
            l_trace,
            l_pre,
            l_atrous,
            l_resolve,
            l_blit,
            p_trace,
            p_pre,
            p_atrous,
            p_resolve,
            p_blit,
            targets: None,
            size: (1, 1),
            settings: Settings::default(),
            look: Look::default(),
            n_renders: 0,
            n_dispatches: 0,
            linear_out: surface_format.is_srgb(),
            power_out: false,
            n: 0,
            frame: 0,
            parity: 0,
            prev_cam: None,
            last_globals: Globals::default(),
        }
    }

    pub fn has_scene(&self) -> bool {
        self.scene.is_some()
    }

    /// Put a model on the card in place of whatever was there. Every part starts shown, where the file has
    /// it, unselected. Returns (upload ms, BLAS build ms).
    pub fn set_scene(&mut self, scene: &Scene) -> (f64, f64) {
        let device = &self.device;
        let t0 = Instant::now();
        let buf = |label: &str, contents: &[u8], usage: wgpu::BufferUsages| device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: Some(label), contents, usage });
        let vb = buf("positions", bytemuck::cast_slice(&scene.positions), wgpu::BufferUsages::BLAS_INPUT);
        let idx_buf = buf("indices", bytemuck::cast_slice(&scene.indices), wgpu::BufferUsages::BLAS_INPUT | wgpu::BufferUsages::STORAGE);
        let vattr_buf = buf("vattr", bytemuck::cast_slice(&scene.vattr), wgpu::BufferUsages::STORAGE);
        let parts_buf = buf("parts", bytemuck::cast_slice(&scene.gpu_parts), wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST);
        self.queue.submit([]);
        device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
        let upload_ms = t0.elapsed().as_secs_f64() * 1e3;

        let t0 = Instant::now();
        let sizes: Vec<wgpu::BlasTriangleGeometrySizeDescriptor> = scene
            .parts
            .iter()
            .map(|p| wgpu::BlasTriangleGeometrySizeDescriptor {
                vertex_format: wgpu::VertexFormat::Float32x3,
                vertex_count: p.vtx_count,
                index_format: Some(wgpu::IndexFormat::Uint32),
                index_count: Some(p.idx_count),
                flags: if p.clear { wgpu::AccelerationStructureGeometryFlags::empty() } else { wgpu::AccelerationStructureGeometryFlags::OPAQUE },
            })
            .collect();
        let blases: Vec<wgpu::Blas> = sizes
            .iter()
            .map(|s| {
                device.create_blas(
                    &wgpu::CreateBlasDescriptor { label: None, flags: wgpu::AccelerationStructureFlags::PREFER_FAST_TRACE, update_mode: wgpu::AccelerationStructureUpdateMode::Build },
                    wgpu::BlasGeometrySizeDescriptors::Triangles { descriptors: vec![s.clone()] },
                )
            })
            .collect();
        let entries: Vec<wgpu::BlasBuildEntry> = scene
            .parts
            .iter()
            .enumerate()
            .map(|(i, p)| wgpu::BlasBuildEntry {
                blas: &blases[i],
                geometry: wgpu::BlasGeometries::TriangleGeometries(vec![wgpu::BlasTriangleGeometry {
                    size: &sizes[i],
                    vertex_buffer: &vb,
                    first_vertex: p.vtx_off,
                    vertex_stride: 12,
                    index_buffer: Some(&idx_buf),
                    first_index: Some(p.idx_off),
                    transform_buffer: None,
                    transform_buffer_offset: None,
                }]),
            })
            .collect();
        let mut enc = device.create_command_encoder(&Default::default());
        enc.build_acceleration_structures(entries.iter(), std::iter::empty());
        self.queue.submit([enc.finish()]);
        device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
        let blas_ms = t0.elapsed().as_secs_f64() * 1e3;
        drop(entries);

        let np = scene.parts.len();
        let tlas = device.create_tlas(&wgpu::CreateTlasDescriptor {
            label: Some("tlas"),
            max_instances: np.max(1) as u32,
            flags: wgpu::AccelerationStructureFlags::PREFER_FAST_TRACE,
            update_mode: wgpu::AccelerationStructureUpdateMode::Build,
        });
        let motion_buf = buf("motion", bytemuck::cast_slice(&vec![IDENT; np.max(1)]), wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST);
        self.scene = Some(SceneGpu { parts_buf, idx_buf, vattr_buf, blases, tlas, parts: scene.gpu_parts.clone(), xf: vec![IDENT; np], xf_prev: vec![IDENT; np], xf_moved: false, motion_buf, motion_live: false, hidden: vec![false; np], tlas_dirty: true, parts_dirty: false });
        for i in 0..np {
            self.put_instance(i);
        }
        // the bind groups name the model's buffers
        let (w, h) = self.size;
        self.targets = None;
        self.resize(w, h);
        (upload_ms, blas_ms)
    }

    fn put_instance(&mut self, i: usize) {
        let Some(s) = self.scene.as_mut() else { return };
        s.tlas[i] = if s.hidden[i] { None } else { Some(wgpu::TlasInstance::new(&s.blases[i], s.xf[i], i as u32, 0xff)) };
        s.tlas_dirty = true;
    }

    /// A hidden part is out of the TLAS: no ray of any kind meets it. True if that changed anything.
    pub fn set_hidden(&mut self, i: usize, hidden: bool) -> bool {
        let Some(s) = self.scene.as_mut() else { return false };
        if s.hidden[i] == hidden {
            return false;
        }
        s.hidden[i] = hidden;
        self.put_instance(i);
        true
    }

    /// Where a part stands: 3x4 rows, CAD frame.
    pub fn set_xf(&mut self, i: usize, xf: [f32; 12]) -> bool {
        let Some(s) = self.scene.as_mut() else { return false };
        if s.xf[i] == xf {
            return false;
        }
        s.xf[i] = xf;
        s.xf_moved = true;
        self.put_instance(i);
        true
    }

    pub fn set_selected(&mut self, i: usize, sel: bool) -> bool {
        let Some(s) = self.scene.as_mut() else { return false };
        let f = if sel { s.parts[i].flags | FLAG_SEL } else { s.parts[i].flags & !FLAG_SEL };
        if f == s.parts[i].flags {
            return false;
        }
        s.parts[i].flags = f;
        s.parts_dirty = true;
        true
    }

    /// (parts hidden, parts not where the file has them, parts selected)
    pub fn counts(&self) -> (usize, usize, usize) {
        match &self.scene {
            Some(s) => (s.hidden.iter().filter(|h| **h).count(), s.xf.iter().filter(|x| **x != IDENT).count(), s.parts.iter().filter(|p| p.flags & FLAG_SEL != 0).count()),
            None => (0, 0, 0),
        }
    }

    /// Forget accumulation and temporal history.
    pub fn invalidate(&mut self) {
        self.n = 0;
        self.prev_cam = None;
    }

    pub fn size(&self) -> (u32, u32) {
        self.size
    }

    pub fn resize(&mut self, w: u32, h: u32) {
        let (w, h) = (w.max(1), h.max(1));
        if self.size == (w, h) && self.targets.is_some() {
            return;
        }
        self.size = (w, h);
        self.invalidate();
        let Some(sc) = self.scene.as_ref() else {
            self.targets = None;
            return;
        };
        let d = &self.device;
        let px = (w * h) as u64;
        let sto = |label: &str, stride: u64, extra: wgpu::BufferUsages| d.create_buffer(&wgpu::BufferDescriptor { label: Some(label), size: px * stride, usage: wgpu::BufferUsages::STORAGE | extra, mapped_at_creation: false });
        let none = wgpu::BufferUsages::empty();
        let (acc_a, acc_b, acc_c) = (sto("acc_a", 16, none), sto("acc_b", 16, none), sto("acc_c", 16, none));
        let other = sto("other", 4, none);
        let guide = [sto("guide0", 16, wgpu::BufferUsages::COPY_SRC), sto("guide1", 16, wgpu::BufferUsages::COPY_SRC)];
        let hist = [sto("hist0", 32, none), sto("hist1", 32, none)];
        let fa = sto("fa", 16, none);
        let fb = sto("fb", 16, none);
        let out_px = sto("out", 4, wgpu::BufferUsages::COPY_SRC);
        let stg = |size: u64| d.create_buffer(&wgpu::BufferDescriptor { label: Some("staging"), size, usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST, mapped_at_creation: false });
        let (staging, guide_staging) = (stg(px * 4), stg(px * 16));
        let g = self.globals.as_entire_binding();
        let mk_trace = |p: usize| bind(d, &self.l_trace, &[g.clone(), sc.tlas.as_binding(), sc.parts_buf.as_entire_binding(), sc.idx_buf.as_entire_binding(), sc.vattr_buf.as_entire_binding(), acc_a.as_entire_binding(), guide[p].as_entire_binding(), acc_b.as_entire_binding(), acc_c.as_entire_binding(), other.as_entire_binding()]);
        let mk_pre = |p: usize| bind(d, &self.l_pre, &[g.clone(), acc_a.as_entire_binding(), guide[p].as_entire_binding(), guide[1 - p].as_entire_binding(), hist[1 - p].as_entire_binding(), hist[p].as_entire_binding(), fa.as_entire_binding(), acc_b.as_entire_binding(), acc_c.as_entire_binding(), sc.motion_buf.as_entire_binding()]);
        let mk_atrous = |p: usize| -> [wgpu::BindGroup; ATROUS_PASSES] {
            std::array::from_fn(|i| {
                let (src, dst) = if i % 2 == 0 { (&fa, &fb) } else { (&fb, &fa) };
                bind(d, &self.l_atrous, &[g.clone(), self.pass_bufs[i].as_entire_binding(), guide[p].as_entire_binding(), src.as_entire_binding(), dst.as_entire_binding()])
            })
        };
        // odd pass count: the final result lands in fb
        let mk_resolve = |p: usize| bind(d, &self.l_resolve, &[g.clone(), guide[p].as_entire_binding(), acc_a.as_entire_binding(), fb.as_entire_binding(), out_px.as_entire_binding(), acc_b.as_entire_binding(), acc_c.as_entire_binding(), other.as_entire_binding()]);
        let t = Targets {
            w,
            h,
            bg_trace: [mk_trace(0), mk_trace(1)],
            bg_pre: [mk_pre(0), mk_pre(1)],
            bg_atrous: [mk_atrous(0), mk_atrous(1)],
            bg_resolve: [mk_resolve(0), mk_resolve(1)],
            bg_blit: bind(d, &self.l_blit, &[g.clone(), out_px.as_entire_binding()]),
            out_px,
            staging,
            guide,
            guide_staging,
        };
        self.targets = Some(t);
    }

    /// Render one frame. `changed`: the camera or anything in the picture changed since the last frame, so
    /// accumulation restarts. `keep`: the last frame is still a picture of this scene from nearby (the camera
    /// moved, parts moved, were hidden or picked), so its light is carried over, each surface point looked up
    /// where it was; not after a resize, a new model, a new cut or new light.
    /// Returns None (and submits nothing) when there is no model or the image is already converged.
    pub fn render(&mut self, cam: &Camera, changed: bool, keep: bool, surface: Option<(&wgpu::TextureView, u32, u32)>) -> Option<wgpu::SubmissionIndex> {
        self.scene.as_ref()?;
        let reset = changed || self.n == 0;
        if !reset && self.n >= MAX_SPP {
            return None;
        }
        if changed && !keep {
            self.prev_cam = None;
        }
        let t = self.targets.as_ref().expect("resize first");
        let s = self.settings;
        let spf = if reset { s.spf_moving.clamp(1, MAX_SPF) } else { s.spf_still.clamp(1, MAX_SPP - self.n) };
        self.n = if reset { spf } else { self.n + spf };
        self.frame = self.frame.wrapping_add(1);
        let temporal = s.temporal && s.denoise;
        let mut mode = 0;
        let mut hist_w = 0.0;
        if temporal {
            if reset {
                mode = 1;
                self.parity ^= 1;
            } else {
                mode = 2;
                hist_w = 12.0 * (1.0 - (self.n as f32 / 48.0)).clamp(0.0, 1.0);
            }
        }
        let vsize = self.look.vsize.unwrap_or((t.w as f32, t.h as f32));
        let aspect = vsize.0 / vsize.1;
        let (cp, cr, cu, cf) = basis(cam, aspect);
        // no previous camera: point the reprojection somewhere that can never validate
        let (pp, pr, pu, pf) = match self.prev_cam {
            Some(pc) => basis(&pc, aspect),
            None => ([1e9, 1e9, 1e9, cp[3]], cr, cu, cf),
        };
        let (sw, sh) = surface.map(|x| (x.1, x.2)).unwrap_or((t.w, t.h));
        let l = self.look;
        let g = Globals {
            cam_pos: cp,
            cam_r: cr,
            cam_u: cu,
            cam_f: cf,
            prev_pos: pp,
            prev_r: pr,
            prev_u: pu,
            prev_f: pf,
            size: [t.w, t.h],
            frame: self.frame,
            n: self.n,
            reset: reset as u32,
            mode,
            spf,
            flags: if l.clip.is_some() { 2 } else { 0 } | if s.denoise { 0 } else { 1 } | if self.linear_out { 8 } else { 0 } | if self.power_out { 16 } else { 0 },
            denoise: if s.denoise { 1.0 } else { 0.0 },
            hist_w,
            max_hist: s.max_hist,
            near: cam.near,
            surf: [sw, sh],
            vsize: [vsize.0, vsize.1],
            sun: [l.sun.x, l.sun.y, l.sun.z, l.sun_strength],
            bg: [l.bg[0], l.bg[1], l.bg[2], 1.0],
            clip: l.clip.unwrap_or([0.0; 4]),
        };
        self.last_globals = g;
        self.queue.write_buffer(&self.globals, 0, bytemuck::bytes_of(&g));
        if s.denoise {
            for i in 0..ATROUS_PASSES {
                self.queue.write_buffer(&self.pass_bufs[i], 0, bytemuck::bytes_of(&PassP { step: 1 << i, sigma_l: s.sigma_l, pad: [0.0; 2] }));
            }
        }
        let p = self.parity;
        let (gx, gy) = (t.w.div_ceil(8), t.h.div_ceil(8));
        let mut enc = self.device.create_command_encoder(&Default::default());
        // parts shown, hidden or moved since the last frame: the TLAS is built again (the BLASes never are)
        let sc = self.scene.as_mut().unwrap();
        if sc.parts_dirty {
            self.queue.write_buffer(&sc.parts_buf, 0, bytemuck::cast_slice(&sc.parts));
            sc.parts_dirty = false;
        }
        if reset && (sc.xf_moved || sc.motion_live) {
            // each moved part's step back to where the last frame had it: was * now^-1
            let m4 = |r: &[f32; 12]| glam::Mat4::from_cols_array(&[r[0], r[4], r[8], 0.0, r[1], r[5], r[9], 0.0, r[2], r[6], r[10], 0.0, r[3], r[7], r[11], 1.0]);
            let mot: Vec<[f32; 12]> = sc
                .xf
                .iter()
                .zip(&sc.xf_prev)
                .map(|(now, was)| {
                    if now == was {
                        return IDENT;
                    }
                    let m = (m4(was) * m4(now).inverse()).to_cols_array();
                    [m[0], m[4], m[8], m[12], m[1], m[5], m[9], m[13], m[2], m[6], m[10], m[14]]
                })
                .collect();
            self.queue.write_buffer(&sc.motion_buf, 0, bytemuck::cast_slice(&mot));
            sc.motion_live = sc.xf_moved;
            sc.xf_moved = false;
            sc.xf_prev.clone_from(&sc.xf);
        }
        if sc.tlas_dirty {
            enc.build_acceleration_structures(std::iter::empty(), std::iter::once(&sc.tlas));
            sc.tlas_dirty = false;
        }
        {
            let mut cp = enc.begin_compute_pass(&Default::default());
            cp.set_pipeline(&self.p_trace);
            cp.set_bind_group(0, &t.bg_trace[p], &[]);
            cp.dispatch_workgroups(gx, gy, 1);
            self.n_dispatches += 2;
            if s.denoise {
                cp.set_pipeline(&self.p_pre);
                cp.set_bind_group(0, &t.bg_pre[p], &[]);
                cp.dispatch_workgroups(gx, gy, 1);
                cp.set_pipeline(&self.p_atrous);
                for i in 0..ATROUS_PASSES {
                    cp.set_bind_group(0, &t.bg_atrous[p][i], &[]);
                    cp.dispatch_workgroups(gx, gy, 1);
                }
                self.n_dispatches += 1 + ATROUS_PASSES as u64;
            }
            cp.set_pipeline(&self.p_resolve);
            cp.set_bind_group(0, &t.bg_resolve[p], &[]);
            cp.dispatch_workgroups(gx, gy, 1);
        }
        self.n_renders += 1;
        if let Some((view, _, _)) = surface {
            self.blit(&mut enc, view, true);
        }
        self.prev_cam = Some(*cam);
        Some(self.queue.submit([enc.finish()]))
    }

    fn blit(&self, enc: &mut wgpu::CommandEncoder, view: &wgpu::TextureView, draw: bool) {
        let bg = self.look.bg.map(|v| if self.linear_out { v as f64 } else if self.power_out { v.powf(1.0 / 2.4) as f64 } else { linear_to_srgb(v) as f64 });
        let mut rp = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: None,
            color_attachments: &[Some(wgpu::RenderPassColorAttachment { view, depth_slice: None, resolve_target: None, ops: wgpu::Operations { load: wgpu::LoadOp::Clear(wgpu::Color { r: bg[0], g: bg[1], b: bg[2], a: 1.0 }), store: wgpu::StoreOp::Store } })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
            multiview_mask: None,
        });
        if let (true, Some(t)) = (draw, self.targets.as_ref()) {
            rp.set_pipeline(&self.p_blit);
            rp.set_bind_group(0, &t.bg_blit, &[]);
            rp.draw(0..3, 0..1);
        }
    }

    /// No model yet: the backdrop alone.
    pub fn clear(&mut self, view: &wgpu::TextureView) {
        let mut enc = self.device.create_command_encoder(&Default::default());
        self.blit(&mut enc, view, false);
        self.queue.submit([enc.finish()]);
    }

    fn read(&self, src: &wgpu::Buffer, staging: &wgpu::Buffer) -> Vec<u8> {
        let mut enc = self.device.create_command_encoder(&Default::default());
        enc.copy_buffer_to_buffer(src, 0, staging, 0, src.size());
        self.queue.submit([enc.finish()]);
        let slice = staging.slice(..);
        slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
        self.device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
        let v = slice.get_mapped_range().unwrap().to_vec();
        staging.unmap();
        v
    }

    /// Read back the image as presented (RGBA8, sRGB). Empty without a model.
    pub fn read_pixels(&mut self) -> Vec<u8> {
        match self.targets.as_ref() {
            Some(t) => self.read(&t.out_px, &t.staging),
            None => vec![],
        }
    }

    /// The first-hit distance along each pixel's centre ray (< 0: backdrop) and the part met there, as of
    /// the last restart of the picture.
    pub fn read_guide(&mut self) -> Vec<(f32, u32)> {
        let Some(t) = self.targets.as_ref() else { return vec![] };
        let raw = self.read(&t.guide[self.parity], &t.guide_staging);
        raw.chunks_exact(16).map(|c| (f32::from_le_bytes([c[4], c[5], c[6], c[7]]), u32::from_le_bytes([c[12], c[13], c[14], c[15]]))).collect()
    }

    /// Samples a frame follow the card: as many as fit the time a frame may take (`budget_ms`, which the
    /// shell sets from the display's refresh), found from the time the last frame DID take, so a slower
    /// card gives fewer samples at the same frame rate instead of fewer frames.
    pub fn note_frame(&mut self, changed: bool, gpu_ms: f64) {
        let b = self.settings.budget_ms as f64;
        let step = |n: u32, ms: f64, b: f64| -> u32 {
            // towards the count that would just fill the budget, a part of the way each frame (one slow
            // frame is not a slow card), at once when over it
            let want = (n as f64 * (0.9 * b / ms.max(0.05))).clamp(1.0, MAX_SPF as f64);
            let next = if ms > b { want.floor() } else { n as f64 + ((want - n as f64) * 0.25).clamp(-4.0, 4.0) };
            (next.round() as u32).clamp(1, MAX_SPF)
        };
        if changed && b > 0.0 {
            self.settings.spf_moving = step(self.settings.spf_moving, gpu_ms, b);
        }
        // at rest: start from what a moving frame takes and fill twice the budget (nothing else is waiting)
        let s = &mut self.settings.spf_still;
        if changed {
            *s = self.settings.spf_moving.max(1);
        } else {
            *s = step(*s, gpu_ms, if b > 0.0 { 2.0 * b } else { 6.0 });
        }
    }

    pub fn wait(&self, idx: wgpu::SubmissionIndex) {
        self.device.poll(wgpu::PollType::Wait { submission_index: Some(idx), timeout: None }).unwrap();
    }
}
