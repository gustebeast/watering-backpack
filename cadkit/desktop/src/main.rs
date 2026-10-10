//! The desktop viewer: the REAL web viewer page (cadkit/web/viewer/index.html), transparent, in a WebView2
//! over a native path tracer in one window. The page is the whole UI and says what the picture is of; this
//! draws the picture.
//!   desk.exe [url]              interactive (default http://127.0.0.1:8161/)
//!   desk.exe [url] --selftest   drives the page through its own controls, captures into ./out, exits
//!                               (--selftest=quality,idle,...: only those parts of it)
//! Options: --out <dir>; --backend dx12|vulkan (default: dx12 if it can trace, which needs the dxcompiler.dll
//! of an installed Windows SDK, or --dxc <path>; else vulkan); --state <file> where the window's place is kept
//! (default: desk-window.json beside the exe).
//!
//! What the page sends (window.ipc.postMessage, JSON, at most one a frame, only what changed):
//!   {t:"view", cam:[16], fov, near, far, w, h,      the page camera's matrixWorld; the size it projects onto
//!    hidden:[names], sel:[names],                   whole lists
//!    poses:{name:[16]},                             matrixWorld of each part the rig has moved (merged)
//!    clip:[nx,ny,nz,c]|null,                        section plane, CAD frame, kept where n.p + c >= 0
//!    sun:[3], sun_strength, bg:[3],                 as the Blender tracer's request has them
//!    glb:"http://.../assembly.glb?v=..."}           the model file, whenever the page has (re)loaded one
mod cap;
mod dda;
mod gpu;
mod http;
mod scene;

use glam::Vec3;
use gpu::{Camera, Renderer};
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};
use winit::application::ApplicationHandler;
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop, EventLoopProxy};
use winit::platform::windows::WindowAttributesExtWindows;
use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};
use winit::window::{Window, WindowId, WindowLevel};

enum Ev {
    Ipc(String),
    /// (url, the model or why not, ms to fetch and read)
    Model(String, Result<scene::Scene, String>, f64),
    /// a selftest service has finished: (request id, its result as JSON)
    Done(u64, String),
    /// the page's title has changed
    Title(String),
}

struct Gfx {
    webview: wry::WebView,
    _ctx: wry::WebContext,
    surface: wgpu::Surface<'static>,
    config: wgpu::SurfaceConfiguration,
    r: Renderer,
    window: Arc<Window>,
    hwnd: isize,
    backend: String,
}

/// The webview covers the whole client area (DESK_WV_FRAC=0.8 leaves the right fifth bare: a control for captures).
fn wv_rect(w: u32, h: u32) -> wry::Rect {
    let frac = std::env::var("DESK_WV_FRAC").ok().and_then(|v| v.parse::<f64>().ok()).unwrap_or(1.0);
    wry::Rect { position: wry::dpi::PhysicalPosition::new(0, 0).into(), size: wry::dpi::PhysicalSize::new((w as f64 * frac) as u32, h).into() }
}

fn hwnd_of(w: &Window) -> isize {
    match w.window_handle().unwrap().as_raw() {
        RawWindowHandle::Win32(h) => h.hwnd.get(),
        _ => 0,
    }
}

struct Args {
    url: String,
    selftest: bool,
    /// the parts of the selftest to run (empty: all)
    only: String,
    out: PathBuf,
    /// "dx12" or "vulkan"; None: dx12 if it can trace rays here, else vulkan
    backend: Option<String>,
    /// dxcompiler.dll for dx12 (ray queries need DXC); found in the Windows SDK if not given
    dxc: Option<String>,
    /// where the window's size and place are kept between runs
    state: Option<PathBuf>,
    /// the webview's data folder (default: webview-data beside the exe)
    data: Option<PathBuf>,
    /// selftest: (from, to) a model folder to copy over the served one, as a rebuild would rewrite it
    recopy: Option<(PathBuf, PathBuf)>,
}

/// The newest dxcompiler.dll of an installed Windows SDK.
fn find_dxc() -> Option<String> {
    let root = PathBuf::from(std::env::var("ProgramFiles(x86)").ok()?).join("Windows Kits").join("10").join("bin");
    let mut found: Vec<PathBuf> = std::fs::read_dir(root).ok()?.filter_map(|e| e.ok()).map(|e| e.path().join("x64").join("dxcompiler.dll")).filter(|p| p.is_file()).collect();
    found.sort();
    found.pop().map(|p| p.to_string_lossy().to_string())
}

/// What the page has said, kept by NAME so it outlives a reload of the model.
#[derive(Default)]
struct View {
    cam: Option<Camera>,
    hidden: HashSet<String>,
    sel: HashSet<String>,
    poses: HashMap<String, [f32; 12]>,
}

#[derive(Default)]
struct Meas {
    on: bool,
    t_first: Option<Instant>,
    t_last: Option<Instant>,
    msgs: u32,
    gpu: Vec<f64>,
    frame: Vec<f64>,
    spf: Vec<f64>,
}

fn summ(v: &[f64]) -> String {
    if v.is_empty() {
        return "n/a".into();
    }
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let q = |p: f64| s[((s.len() - 1) as f64 * p).round() as usize];
    format!("avg {:.2}  p50 {:.2}  p95 {:.2}  max {:.2} (n={})", s.iter().sum::<f64>() / s.len() as f64, q(0.5), q(0.95), s[s.len() - 1], s.len())
}

/// A capture the selftest page has asked for; taken once the picture has come to rest.
struct Shot {
    id: u64,
    name: String,
    req: Value,
    t0: Instant,
}

/// A moving frame to compare with the same view at rest: taken `left` changed frames from now.
struct Snap {
    id: u64,
    name: String,
    left: u32,
}

#[derive(Default)]
struct Test {
    log: String,
    shot: Option<Shot>,
    resize: Option<(u64, u32, u32, Instant)>,
    chrome: isize,
    kept: HashMap<String, Vec<u8>>,
    done: bool,
    snap: Option<Snap>,
}

struct App {
    args: Args,
    proxy: EventLoopProxy<Ev>,
    gfx: Option<Gfx>,
    view: View,
    names: HashMap<String, usize>,
    part_names: Vec<String>,
    glb_want: String,
    glb_have: String,
    loading: u32,
    dirty: bool,
    rigid: bool,
    start: Instant,
    last_msg: Instant,
    last_present: Instant,
    t_dirty: Instant,
    converge_ms: f64,
    stat_t: Instant,
    stat_frames: u32,
    stat_gpu: f64,
    stat_last: String,
    meas: Meas,
    t: Test,
    quit: bool,
    presents: u64,
    stat_sent: u64,
    resizes: u64,
    ctrl: bool,
    shift: bool,
    /// the window's last un-maximised, un-minimised place: [x, y, w, h]
    place: [i32; 4],
}

fn state_file(args: &Args) -> Option<PathBuf> {
    if let Some(p) = &args.state {
        return Some(p.clone());
    }
    if args.selftest {
        return None; // the selftest's window is where its captures expect it
    }
    Some(std::env::current_exe().ok()?.parent()?.join("desk-window.json"))
}

/// One way of getting pictures out of the card. Err: why not.
fn try_backend(window: &Arc<Window>, which: &str, args: &Args, size: PhysicalSize<u32>) -> Result<(wgpu::Surface<'static>, wgpu::SurfaceConfiguration, Renderer, String), String> {
    let mut idesc = wgpu::InstanceDescriptor::new_without_display_handle();
    let mut note = String::new();
    if which == "dx12" {
        idesc.backends = wgpu::Backends::DX12;
        let p = args.dxc.clone().or_else(find_dxc).ok_or("no dxcompiler.dll in an installed Windows SDK (or --dxc <path>)")?;
        if !std::path::Path::new(&p).is_file() {
            return Err(format!("no dxcompiler.dll at {p}"));
        }
        note = format!("; shader compiler {p}");
        idesc.backend_options.dx12.shader_compiler = wgpu::Dx12Compiler::DynamicDxc { dxc_path: p };
    } else {
        idesc.backends = wgpu::Backends::VULKAN;
    }
    let instance = wgpu::Instance::new(idesc);
    let surface = instance.create_surface(window.clone()).map_err(|e| e.to_string())?;
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions { power_preference: wgpu::PowerPreference::HighPerformance, compatible_surface: Some(&surface), ..Default::default() })).map_err(|e| format!("no adapter: {e}"))?;
    let info = adapter.get_info();
    if !adapter.features().contains(wgpu::Features::EXPERIMENTAL_RAY_QUERY) {
        return Err(format!("{} does not offer ray queries there", info.name));
    }
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        label: None,
        required_features: wgpu::Features::EXPERIMENTAL_RAY_QUERY,
        required_limits: adapter.limits(),
        experimental_features: unsafe { wgpu::ExperimentalFeatures::enabled() },
        memory_hints: wgpu::MemoryHints::Performance,
        trace: wgpu::Trace::Off,
    }))
    .map_err(|e| e.to_string())?;
    let caps = surface.get_capabilities(&adapter);
    let mut config = surface.get_default_config(&adapter, size.width.max(1), size.height.max(1)).ok_or("no surface configuration")?;
    // values go to the surface already sRGB-encoded, so: a format that does not encode them again.
    // (DESK_SURFACE=srgb|float picks another, for finding out what a desktop does with each)
    let want = std::env::var("DESK_SURFACE").unwrap_or_default();
    config.format = match want.as_str() {
        "srgb" => caps.formats.iter().copied().find(|f| f.is_srgb()),
        "float" => caps.formats.iter().copied().find(|f| *f == wgpu::TextureFormat::Rgba16Float),
        _ => None,
    }
    .or_else(|| caps.formats.iter().copied().find(|f| !f.is_srgb() && *f != wgpu::TextureFormat::Rgba16Float))
    .unwrap_or(caps.formats[0]);
    config.present_mode = [wgpu::PresentMode::Mailbox, wgpu::PresentMode::Immediate].iter().copied().find(|m| caps.present_modes.contains(m)).unwrap_or(wgpu::PresentMode::AutoNoVsync);
    surface.configure(&device, &config);
    // the shaders are compiled here: a compiler that cannot do them shows now, not at the first frame
    let scope = device.push_error_scope(wgpu::ErrorFilter::Validation);
    let mut r = Renderer::new(device, queue, config.format);
    if let Some(e) = pollster::block_on(scope.pop()) {
        return Err(format!("its shaders do not compile: {}", e.to_string().lines().next().unwrap_or("")));
    }
    if config.format == wgpu::TextureFormat::Rgba16Float {
        r.linear_out = true;
    }
    r.power_out = std::env::var("DESK_POWER_OUT").is_ok_and(|v| v == "1");
    r.settings.temporal = true;
    r.resize(config.width, config.height);
    let line = format!("{:?} / {} / driver {}{note}; surface {:?} {:?} (offered: {:?})", info.backend, info.name, info.driver_info, config.format, config.present_mode, caps.formats);
    Ok((surface, config, r, line))
}


fn init_gfx(event_loop: &ActiveEventLoop, args: &Args, proxy: EventLoopProxy<Ev>) -> (Gfx, String) {
    // with_clip_children(false) is REQUIRED: with WS_CLIPCHILDREN the picture under the webview is white
    let mut attrs = Window::default_attributes().with_title("cadkit desk").with_inner_size(PhysicalSize::new(1280u32, 800u32)).with_clip_children(false);
    let mut said = String::new();
    if args.selftest && args.state.is_none() {
        attrs = attrs.with_position(PhysicalPosition::new(60, 60)).with_window_level(WindowLevel::AlwaysOnTop);
    } else if let Some(v) = state_file(args).and_then(|f| std::fs::read_to_string(f).ok()).and_then(|t| serde_json::from_str::<Value>(&t).ok()) {
        // where it was last time, if that is still on a screen
        let n = |k: &str| v[k].as_i64().unwrap_or(0) as i32;
        let (x, y, w, h) = (n("x"), n("y"), n("w").clamp(320, 16384), n("h").clamp(240, 16384));
        let on_screen = event_loop.available_monitors().any(|m| {
            let (p, s) = (m.position(), m.size());
            x + 80 < p.x + s.width as i32 && x + w - 80 > p.x && y >= p.y - 8 && y + 40 < p.y + s.height as i32
        });
        attrs = attrs.with_inner_size(PhysicalSize::new(w as u32, h as u32)).with_maximized(v["max"].as_bool().unwrap_or(false));
        if on_screen {
            attrs = attrs.with_position(PhysicalPosition::new(x, y));
        }
        said = format!("window: as it was left: {w}x{h} at {x},{y}{}{}\n", if v["max"].as_bool().unwrap_or(false) { ", maximised" } else { "" }, if on_screen { "" } else { " (that place is on no screen now: placed by the desktop)" });
        if args.selftest {
            attrs = attrs.with_window_level(WindowLevel::AlwaysOnTop);
        }
    }
    let window = Arc::new(event_loop.create_window(attrs).unwrap());
    let hwnd = hwnd_of(&window);
    let size = window.inner_size();
    // DX12 first: on an HDR desktop its picture is shown exactly, Vulkan's too dark
    let order: Vec<&str> = match args.backend.as_deref() {
        Some("vulkan") => vec!["vulkan"],
        Some(_) => vec!["dx12"],
        None => vec!["dx12", "vulkan"],
    };
    let mut got = None;
    for (i, which) in order.iter().enumerate() {
        match try_backend(&window, which, args, size) {
            Ok(x) => {
                got = Some((x, which.to_string()));
                break;
            }
            Err(e) if i + 1 < order.len() => said += &format!("{which} is not used: {e}; falling back to {}\n", order[i + 1]),
            Err(e) => panic!("{which} cannot be used: {e}"),
        }
    }
    let ((surface, config, mut r, line), backend) = got.unwrap();
    said += &format!("adapter: {line}\n");
    // A MOVING FRAME GETS A THIRD OF THE CARD, not all of it: its samples are fitted to about 36% of the time
    // the display shows a frame for (1.5 ms at 240 Hz, 3 ms at 120, 6 ms at 60). Filling the whole frame bought
    // a little less grain while moving for a card at full power, fans and all, whenever anything moved.
    let hz = window.current_monitor().and_then(|m| m.refresh_rate_millihertz()).unwrap_or(60000) as f32 / 1000.0;
    r.settings.budget_ms = std::env::var("DESK_BUDGET_MS").ok().and_then(|v| v.parse().ok()).unwrap_or((360.0 / hz.max(1.0)).clamp(1.2, 6.0));
    said += &format!("display {hz:.0} Hz: a moving frame gets as many samples as the card does in {:.1} ms", r.settings.budget_ms);

    // the UI: the page itself in a WebView2 child window over the whole client area, transparent. It is told
    // where it is before any of its own script runs.
    // the page's own storage (it keeps its view there between runs): one folder a window, as two programs
    // cannot share one
    let data_dir = args.data.clone().unwrap_or_else(|| std::env::current_exe().unwrap().parent().unwrap().join("webview-data"));
    let mut ctx = wry::WebContext::new(Some(data_dir));
    let mut init = String::from("window.cadkitNative = true;\n");
    if args.selftest {
        init += &format!("window.__tOnly = {};
", json!(args.only));
        init += include_str!("selftest.js");
    }
    let webview = wry::WebViewBuilder::new_with_web_context(&mut ctx)
        .with_bounds(wv_rect(size.width, size.height))
        .with_transparent(true)
        .with_initialization_script(init)
        .with_url(&args.url)
        .with_document_title_changed_handler({
            let proxy = proxy.clone();
            move |t| {
                let _ = proxy.send_event(Ev::Title(t));
            }
        })
        .with_ipc_handler(move |req: wry::http::Request<String>| {
            let _ = proxy.send_event(Ev::Ipc(req.into_body()));
        })
        .build_as_child(&*window)
        .expect("WebView2 creation failed (is the WebView2 runtime installed?)");
    if args.selftest {
        match dda::init(hwnd) {
            Ok(s) | Err(s) => said += &format!("\n{s}"),
        }
    }
    // the keys are the page's: it has the keyboard from the start
    let _ = webview.focus();
    (Gfx { webview, _ctx: ctx, surface, config, r, window, hwnd, backend }, said)
}

fn acquire(g: &Gfx) -> Option<wgpu::SurfaceTexture> {
    match g.surface.get_current_texture() {
        wgpu::CurrentSurfaceTexture::Success(t) | wgpu::CurrentSurfaceTexture::Suboptimal(t) => Some(t),
        wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
            g.surface.configure(&g.r.device, &g.config);
            match g.surface.get_current_texture() {
                wgpu::CurrentSurfaceTexture::Success(t) | wgpu::CurrentSurfaceTexture::Suboptimal(t) => Some(t),
                _ => None,
            }
        }
        _ => None,
    }
}

fn save_png(path: &std::path::Path, w: u32, h: u32, rgba: &[u8]) {
    let f = std::io::BufWriter::new(std::fs::File::create(path).unwrap());
    let mut e = png::Encoder::new(f, w, h);
    e.set_color(png::ColorType::Rgba);
    e.set_depth(png::BitDepth::Eight);
    e.write_header().unwrap().write_image_data(rgba).unwrap();
}

fn nums<const N: usize>(v: &Value) -> Option<[f32; N]> {
    let a = v.as_array()?;
    if a.len() < N {
        return None;
    }
    let mut o = [0.0; N];
    for i in 0..N {
        o[i] = a[i].as_f64()? as f32;
    }
    Some(o)
}

/// The box round every pixel that is not the backdrop: [x0, y0, x1, y1], pixel edges.
/// (The outermost pixels are left out: the desktop rounds the window's corners.)
fn bbox(px: &[u8], w: u32, h: u32, bg: [u8; 3]) -> Option<[u32; 4]> {
    let (mut x0, mut y0, mut x1, mut y1) = (u32::MAX, u32::MAX, 0, 0);
    for y in 12..h.saturating_sub(12) {
        for x in 12..w.saturating_sub(12) {
            let i = ((y * w + x) * 4) as usize;
            if (0..3).any(|c| px[i + c].abs_diff(bg[c]) > 10) {
                x0 = x0.min(x);
                y0 = y0.min(y);
                x1 = x1.max(x + 1);
                y1 = y1.max(y + 1);
            }
        }
    }
    (x1 > 0).then_some([x0, y0, x1, y1])
}

impl App {
    fn say(&mut self, s: String) {
        println!("{s}");
        self.t.log.push_str(&s);
        self.t.log.push('\n');
    }

    fn eval(&self, js: &str) {
        if let Some(g) = &self.gfx {
            let _ = g.webview.evaluate_script(js);
        }
    }

    fn resume(&self, id: u64, result: &str) {
        self.eval(&format!("window.__t&&__t.resume({id},{result})"));
    }

    /// The model the page shows: fetched from the server the page came from, off this thread.
    fn fetch_model(&mut self, url: String) {
        if url == self.glb_want {
            return;
        }
        self.glb_want = url.clone();
        self.loading += 1;
        let proxy = self.proxy.clone();
        std::thread::spawn(move || {
            let t = Instant::now();
            let r = http::get(&url).and_then(|b| scene::load(&b));
            let _ = proxy.send_event(Ev::Model(url, r, t.elapsed().as_secs_f64() * 1e3));
        });
    }

    fn on_model(&mut self, url: String, r: Result<scene::Scene, String>, ms: f64) {
        self.loading = self.loading.saturating_sub(1);
        if url != self.glb_want {
            return; // the page has moved on to a newer one
        }
        let sc = match r {
            Ok(s) => s,
            Err(e) => {
                self.say(format!("model: {e}"));
                return;
            }
        };
        let Some(g) = self.gfx.as_mut() else { return };
        let (up, blas) = g.r.set_scene(&sc);
        self.part_names = sc.parts.iter().map(|p| p.name.clone()).collect();
        self.names = self.part_names.iter().enumerate().map(|(i, n)| (n.clone(), i)).collect();
        // what the page has already said applies to the new model too
        for (i, n) in self.part_names.iter().enumerate() {
            g.r.set_hidden(i, self.view.hidden.contains(n));
            g.r.set_selected(i, self.view.sel.contains(n));
            if let Some(x) = self.view.poses.get(n) {
                g.r.set_xf(i, *x);
            }
        }
        self.glb_have = url;
        let s = format!("model: {} parts, {} triangles; fetched and read in {ms:.0} ms, uploaded in {up:.0} ms, BLAS built in {blas:.0} ms", sc.parts.len(), sc.indices.len() / 3);
        self.say(s);
        self.touch(false);
        self.redraw();
    }

    /// The picture is no longer what is on screen. `rigid`: it is still a picture of the same things in the
    /// same light from nearby (the camera moved, the rig moved parts, parts were hidden or picked).
    fn touch(&mut self, rigid: bool) {
        self.rigid = if self.dirty { self.rigid && rigid } else { rigid };
        self.dirty = true;
    }

    fn on_view(&mut self, v: &Value) {
        self.last_msg = Instant::now();
        self.meas.msgs += self.meas.on as u32;
        if let Some(u) = v["glb"].as_str() {
            self.fetch_model(u.to_string());
        }
        let Some(g) = self.gfx.as_mut() else { return };
        let mut rigid = true;
        if let Some(m) = nums::<16>(&v["cam"]) {
            self.view.cam = Some(Camera::from_page(&m, v["fov"].as_f64().unwrap_or(40.0) as f32, v["near"].as_f64().unwrap_or(1.0) as f32));
        }
        if let (Some(w), Some(h)) = (v["w"].as_f64(), v["h"].as_f64()) {
            let vs = Some((w as f32, h as f32));
            rigid &= g.r.look.vsize == vs;
            g.r.look.vsize = vs;
        }
        let set = |a: &Value| -> HashSet<String> { a.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default() };
        if v["hidden"].is_array() {
            self.view.hidden = set(&v["hidden"]);
            for (i, n) in self.part_names.iter().enumerate() {
                g.r.set_hidden(i, self.view.hidden.contains(n));
            }
        }
        if v["sel"].is_array() {
            self.view.sel = set(&v["sel"]);
            for (i, n) in self.part_names.iter().enumerate() {
                g.r.set_selected(i, self.view.sel.contains(n));
            }
        }
        if let Some(p) = v["poses"].as_object() {
            for (n, m) in p {
                let Some(m) = nums::<16>(m) else { continue };
                let x = gpu::page_to_cad(&m);
                if let Some(&i) = self.names.get(n) {
                    g.r.set_xf(i, x);
                }
                self.view.poses.insert(n.clone(), x);
            }
        }
        if let Some(c) = v.get("clip") {
            g.r.look.clip = nums::<4>(c);
            rigid = false;
        }
        if let Some(s) = nums::<3>(&v["sun"]) {
            g.r.look.sun = Vec3::new(s[0], -s[2], s[1]).normalize();
            rigid = false;
        }
        if let Some(s) = v["sun_strength"].as_f64() {
            g.r.look.sun_strength = s as f32;
        }
        if let Some(b) = nums::<3>(&v["bg"]) {
            g.r.look.bg = b.map(gpu::srgb_to_linear);
            rigid = false;
        }
        self.touch(rigid);
        // straight away: one frame per message
        self.redraw();
    }

    fn redraw(&mut self) {
        let Some(g) = self.gfx.as_mut() else { return };
        if g.window.is_minimized() == Some(true) {
            return; // nothing to show it on: drawn when the window is back
        }
        let changed = self.dirty;
        let Some(cam) = self.view.cam.filter(|_| g.r.has_scene()) else {
            // nothing to trace yet: the backdrop
            if changed || self.stat_frames == 0 {
                if let Some(frame) = acquire(g) {
                    g.r.clear(&frame.texture.create_view(&Default::default()));
                    g.r.queue.present(frame);
                    self.stat_frames += 1;
                }
            }
            return;
        };
        if !changed && g.r.n >= gpu::MAX_SPP {
            return;
        }
        let t0 = Instant::now();
        let Some(frame) = acquire(g) else { return };
        let view = frame.texture.create_view(&Default::default());
        let spf = if changed { g.r.settings.spf_moving } else { g.r.settings.spf_still };
        let Some(idx) = g.r.render(&cam, changed, self.rigid, Some((&view, g.config.width, g.config.height))) else { return };
        self.dirty = false;
        let t1 = Instant::now();
        g.r.wait(idx);
        let gm = t1.elapsed().as_secs_f64() * 1e3;
        g.r.note_frame(changed, gm);
        g.r.queue.present(frame);
        self.presents += 1;
        let now = Instant::now();
        self.last_present = now;
        self.stat_frames += 1;
        self.stat_gpu += gm;
        if changed {
            self.t_dirty = now;
            if self.meas.on {
                let m = &mut self.meas;
                m.t_first.get_or_insert(now);
                m.t_last = Some(now);
                m.gpu.push(gm);
                m.frame.push((now - t0).as_secs_f64() * 1e3);
                m.spf.push(spf as f64);
            }
        }
        if g.r.n >= gpu::MAX_SPP {
            self.converge_ms = (now - self.t_dirty).as_secs_f64() * 1e3;
        } else {
            g.window.request_redraw();
        }
        if changed && self.t.snap.as_mut().is_some_and(|s| {
            s.left = s.left.saturating_sub(1);
            s.left == 0
        }) {
            let s = self.t.snap.take().unwrap();
            self.t_snap(s, cam, spf);
        }
    }

    /// A MOVING frame (the one just shown) against the same view AT REST: the scene as it stands this
    /// instant, traced afresh to the full count. Both saved; how far apart they are is the answer.
    fn t_snap(&mut self, sn: Snap, cam: Camera, spf: u32) {
        let dir = self.args.out.join("motion");
        let _ = std::fs::create_dir_all(&dir);
        let Some(g) = self.gfx.as_mut() else { return };
        let (w, h) = g.r.size();
        let moving = g.r.read_pixels();
        let still = g.r.settings.spf_still;
        g.r.settings.spf_still = 16;
        let mut first = true;
        while let Some(i) = g.r.render(&cam, first, false, None) {
            g.r.wait(i);
            first = false;
        }
        g.r.settings.spf_still = still;
        let rest = g.r.read_pixels();
        save_png(&dir.join(format!("{}_moving.png", sn.name)), w, h, &moving);
        save_png(&dir.join(format!("{}_rest.png", sn.name)), w, h, &rest);
        let lum = |p: &[u8]| 0.2126 * p[0] as f64 + 0.7152 * p[1] as f64 + 0.0722 * p[2] as f64;
        let (mut sum, mut big, mut sl, mut model, mut msum) = (0u64, 0u64, 0.0f64, 0u64, 0u64);
        let bg = [rest[0], rest[1], rest[2]];
        for (a, b) in moving.chunks_exact(4).zip(rest.chunks_exact(4)) {
            let d: u64 = (0..3).map(|c| a[c].abs_diff(b[c]) as u64).sum();
            sum += d;
            big += ((0..3).map(|c| a[c].abs_diff(b[c])).max().unwrap() > 24) as u64;
            sl += lum(a) - lum(b);
            if b[..3] != bg || a[..3] != bg {
                model += 1;
                msum += d;
            }
        }
        let n = (w * h) as f64;
        let res = json!({"mean": sum as f64 / (3.0 * n), "mean_on_model": msum as f64 / (3.0 * model.max(1) as f64), "model_share": model as f64 / n, "changed_share": big as f64 / n, "lum_bias": sl / n, "spf": spf, "size": [w, h]});
        self.resume(sn.id, &res.to_string());
        // (the tracer's buffers now hold the resting picture, the screen the moving one: drawn again)
        self.touch(true);
        if let Some(g) = self.gfx.as_ref() {
            g.window.request_redraw();
        }
    }

    /// The page's status line: said only when it changes, so a picture at rest costs nothing here either.
    fn push_stats(&mut self) {
        let el = self.stat_t.elapsed().as_secs_f64();
        if el < 0.25 {
            return;
        }
        let Some(g) = self.gfx.as_ref() else { return };
        let n = self.stat_frames.max(1) as f64;
        let state = if !g.r.has_scene() {
            if self.loading > 0 { "loading the model" } else { "no model" }
        } else if g.r.n >= gpu::MAX_SPP {
            "at rest"
        } else {
            "refining"
        };
        // (at rest nothing is being drawn: no frame time to give)
        let rest = g.r.n >= gpu::MAX_SPP || !g.r.has_scene();
        let js = format!("window.viewer&&viewer.native&&viewer.native.stats({{spp:{},state:'{}',fps:{:.0},gpu_ms:{:.1},w:{},h:{}}})", g.r.n, state, if rest { 0.0 } else { self.stat_frames as f64 / el }, if rest { 0.0 } else { self.stat_gpu / n }, g.config.width, g.config.height);
        self.stat_t = Instant::now();
        self.stat_frames = 0;
        self.stat_gpu = 0.0;
        if js != self.stat_last {
            let _ = g.webview.evaluate_script(&js);
            self.stat_last = js;
            self.stat_sent += 1;
        }
    }

    fn on_ipc(&mut self, body: &str) {
        let Ok(v) = serde_json::from_str::<Value>(body) else { return };
        let t = v["t"].as_str().unwrap_or("");
        if t == "view" {
            return self.on_view(&v);
        }
        if !self.args.selftest {
            return;
        }
        let id = v["id"].as_u64().unwrap_or(0);
        match t {
            "Tlog" => self.say(v["s"].as_str().unwrap_or("").to_string()),
            "Tmouse" => self.t_mouse(id, &v),
            "Tshot" => self.t.shot = Some(Shot { id, name: v["name"].as_str().unwrap_or("").to_string(), req: v, t0: Instant::now() }),
            "Tresize" => {
                let (w, h) = (v["w"].as_u64().unwrap_or(1280) as u32, v["h"].as_u64().unwrap_or(800) as u32);
                if let Some(g) = self.gfx.as_ref() {
                    let _ = g.window.request_inner_size(PhysicalSize::new(w, h));
                }
                self.t.resize = Some((id, w, h, Instant::now()));
            }
            "Tmeas" => {
                if v["on"].as_bool().unwrap_or(false) {
                    self.meas = Meas { on: true, ..Default::default() };
                    self.resume(id, "null");
                } else {
                    let m = std::mem::take(&mut self.meas);
                    let el = match (m.t_first, m.t_last) {
                        (Some(a), Some(b)) => (b - a).as_secs_f64(),
                        _ => 0.0,
                    };
                    let fps = if el > 0.0 { (m.gpu.len().max(1) - 1) as f64 / el } else { 0.0 };
                    let s = format!("  view messages {}, frames traced and presented {} in {el:.2} s = {fps:.1} fps\n  GPU ms a frame (submit -> done, trace + denoise + blit): {}\n  whole native frame ms (acquire -> present returned):   {}\n  samples a pixel in each moving frame:                  {}", m.msgs, m.gpu.len(), summ(&m.gpu), summ(&m.frame), summ(&m.spf));
                    self.resume(id, &json!(s).to_string());
                }
            }
            "Tquality" => self.t_quality(id, &v),
            "Tkey" => self.t_key(id, &v),
            "Tsize" => self.t_size(id, &v),
            "Tdbl" => {
                // a double-click by the pointer itself (the desktop's input queue): the pointer is taken to
                // the place, clicked twice, and put back. Only while this window is in front.
                if let Some(g) = self.gfx.as_ref() {
                    let (hwnd, proxy) = (g.hwnd, self.proxy.clone());
                    let at = cap::client_to_screen(hwnd, v["x"].as_f64().unwrap_or(0.0) as i32, v["y"].as_f64().unwrap_or(0.0) as i32);
                    std::thread::spawn(move || {
                        let ok = cap::foreground() == hwnd;
                        if ok {
                            let was = cap::cursor();
                            cap::set_cursor(at);
                            std::thread::sleep(Duration::from_millis(60));
                            for down in [true, false, true, false] {
                                cap::type_button(down);
                                std::thread::sleep(Duration::from_millis(40));
                            }
                            std::thread::sleep(Duration::from_millis(60));
                            cap::set_cursor(was);
                        }
                        let _ = proxy.send_event(Ev::Done(id, json!(ok).to_string()));
                    });
                }
            }
            "Tsnap" => self.t.snap = Some(Snap { id, name: v["name"].as_str().unwrap_or("snap").to_string(), left: v["after"].as_u64().unwrap_or(1).max(1) as u32 }),
            "Twin" => {
                let r = self.win_info();
                self.resume(id, &r.to_string());
            }
            "Tmin" => {
                if let Some(g) = self.gfx.as_ref() {
                    g.window.set_minimized(v["on"].as_bool().unwrap_or(false));
                }
                self.resume(id, "null");
            }
            "Tplace" => {
                if let Some(g) = self.gfx.as_ref() {
                    g.window.set_outer_position(PhysicalPosition::new(v["x"].as_i64().unwrap_or(60) as i32, v["y"].as_i64().unwrap_or(60) as i32));
                    let _ = g.window.request_inner_size(PhysicalSize::new(v["w"].as_u64().unwrap_or(1280) as u32, v["h"].as_u64().unwrap_or(800) as u32));
                }
                self.resume(id, "null");
            }
            "Tfocus" => {
                if let Some(g) = self.gfx.as_ref() {
                    let _ = if v["who"].as_str() == Some("shell") { g.webview.focus_parent() } else { g.webview.focus() };
                }
                self.resume(id, "null");
            }
            "Trecopy" => {
                // the served model folder written again, as a rebuild writes it: every file, the stamp last and new
                let r = match &self.args.recopy {
                    None => json!("no --recopy <from> <to> given"),
                    Some((from, to)) => {
                        let mut n = 0;
                        let mut err = String::new();
                        for name in ["assembly.glb", "assembly.geo.json", "rig.json", "colors.json"] {
                            match std::fs::copy(from.join(name), to.join(name)) {
                                Ok(_) => n += 1,
                                Err(e) => err += &format!("{name}: {e}; "),
                            }
                        }
                        let stamp = std::fs::read_to_string(from.join("stamp.json")).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok());
                        if let Some(mut st) = stamp {
                            st["t"] = json!(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0));
                            match std::fs::write(to.join("stamp.json"), st.to_string()) {
                                Ok(_) => n += 1,
                                Err(e) => err += &format!("stamp.json: {e}"),
                            }
                        }
                        json!(format!("{n} files written again into {}{}", to.display(), if err.is_empty() { String::new() } else { format!(" ({err})") }))
                    }
                };
                self.resume(id, &r.to_string());
            }
            "Tdone" => self.t.done = true,
            _ => {}
        }
    }

    /// Real mouse messages to the WebView2 input window (not the user's cursor): [msg, wparam, x, y, ms to wait after].
    fn t_mouse(&mut self, id: u64, v: &Value) {
        let Some(g) = self.gfx.as_ref() else { return };
        if self.t.chrome == 0 {
            self.t.chrome = cap::children(g.hwnd).iter().find(|k| k.1 == "Chrome_RenderWidgetHostHWND").map(|k| k.0).unwrap_or(0);
        }
        let (chrome, hwnd, proxy) = (self.t.chrome, g.hwnd, self.proxy.clone());
        let ops: Vec<(u32, usize, i32, i32, u64)> = v["ops"].as_array().map(|a| a.iter().map(|o| (o[0].as_u64().unwrap_or(0) as u32, o[1].as_u64().unwrap_or(0) as usize, o[2].as_f64().unwrap_or(0.0) as i32, o[3].as_f64().unwrap_or(0.0) as i32, o[4].as_u64().unwrap_or(0))).collect()).unwrap_or_default();
        std::thread::spawn(move || {
            for (msg, wp, x, y, wait) in ops {
                // the wheel message alone carries SCREEN coordinates
                let (x, y) = if msg == 0x020A { cap::client_to_screen(hwnd, x, y) } else { (x, y) };
                if chrome != 0 {
                    cap::post_mouse(chrome, msg, wp, x, y);
                }
                std::thread::sleep(Duration::from_millis(wait));
            }
            let _ = proxy.send_event(Ev::Done(id, json!(chrome != 0).to_string()));
        });
    }

    fn quiet(&self) -> bool {
        let Some(g) = self.gfx.as_ref() else { return false };
        let conv = !g.r.has_scene() || self.view.cam.is_none() || g.r.n >= gpu::MAX_SPP;
        conv && !self.dirty && self.loading == 0 && self.last_msg.elapsed() > Duration::from_millis(500) && self.last_present.elapsed() > Duration::from_millis(250)
    }

    /// The picture has come to rest: capture the window as the desktop shows it and the native image, and
    /// answer what the page asked about them.
    fn t_shot(&mut self, s: Shot) {
        let timed_out = !self.quiet();
        let converge_ms = self.converge_ms;
        let part_names = &self.part_names;
        let Some(g) = self.gfx.as_mut() else { return };
        let (rw, rh) = g.r.size();
        let native = g.r.read_pixels();
        let guide = g.r.read_guide();
        let green = nums::<4>(&s.req["green"]).map(|r| r.map(|x| x as f64));
        let (dw, dh, dda, dda_err) = match dda::capture(g.hwnd, green) {
            Ok((w, h, px)) => (w, h, px, String::new()),
            Err(e) => (0, 0, vec![], e),
        };
        if !s.name.is_empty() {
            if !native.is_empty() {
                save_png(&self.args.out.join(format!("{}_native.png", s.name)), rw, rh, &native);
            }
            if !dda.is_empty() {
                save_png(&self.args.out.join(format!("{}_dda.png", s.name)), dw, dh, &dda);
            }
        }
        let bgc = g.r.look.bg.map(|v| (gpu::linear_to_srgb(v) * 255.0).round() as u8);
        let at = |px: &[u8], w: u32, h: u32, x: i64, y: i64| -> Option<[u8; 3]> {
            if x < 0 || y < 0 || x >= w as i64 || y >= h as i64 || px.is_empty() {
                return None;
            }
            let i = ((y as u32 * w + x as u32) * 4) as usize;
            Some([px[i], px[i + 1], px[i + 2]])
        };
        // the page's own picks against the first hit of the native picture, pixel by pixel
        let (mut agree, mut page_only, mut native_only, mut skipped, mut far, mut other) = (0, 0, 0, 0, 0, 0);
        let mut worst: Vec<Value> = vec![];
        let probes = s.req["probe"].as_array().cloned().unwrap_or_default();
        for p in &probes {
            let (x, y, d) = (p[0].as_u64().unwrap_or(0) as u32, p[1].as_u64().unwrap_or(0) as u32, p[2].as_f64().unwrap_or(-1.0) as f32);
            if p[3].as_u64().unwrap_or(0) != 0 || x >= rw || y >= rh || guide.is_empty() {
                skipped += 1;
                continue;
            }
            let (gd, gi) = guide[(y * rw + x) as usize];
            let gname = part_names.get(gi as usize).map(|s| s.as_str()).unwrap_or("");
            let ok = match (d >= 0.0, gd >= 0.0) {
                (false, false) => true,
                (true, false) => {
                    page_only += 1;
                    false
                }
                (false, true) => {
                    native_only += 1;
                    false
                }
                (true, true) => {
                    let near = (gd - d).abs() <= 0.05 + 2e-3 * d;
                    if !near {
                        far += 1;
                    } else if p[4].as_str().unwrap_or("") != gname {
                        other += 1; // two parts face to face at the same depth
                    }
                    near
                }
            };
            agree += ok as u32;
            if !ok && worst.len() < 4 {
                worst.push(json!([x, y, d, p[4], gd, gname]));
            }
        }
        let depth: Vec<Value> = s.req["depth"]
            .as_array()
            .map(|a| {
                a.iter()
                    .map(|p| {
                        let (x, y) = (p[0].as_f64().unwrap_or(0.0) as i64, p[1].as_f64().unwrap_or(0.0) as i64);
                        let mut o = vec![];
                        for dy in -1..=1 {
                            for dx in -1..=1 {
                                let (xx, yy) = (x + dx, y + dy);
                                if xx >= 0 && yy >= 0 && xx < rw as i64 && yy < rh as i64 && !guide.is_empty() {
                                    o.push(guide[(yy as u32 * rw + xx as u32) as usize].0);
                                }
                            }
                        }
                        json!(o)
                    })
                    .collect()
            })
            .unwrap_or_default();
        let sample: Vec<Value> = s.req["sample"].as_array().map(|a| a.iter().map(|p| {
            let (x, y) = (p[0].as_f64().unwrap_or(0.0) as i64, p[1].as_f64().unwrap_or(0.0) as i64);
            json!({"native": at(&native, rw, rh, x, y), "dda": at(&dda, dw, dh, x, y)})
        }).collect()).unwrap_or_default();
        // marks the page drew: the centre of the pixels near a colour, round where the page says it put one
        let found: Vec<Value> = s.req["find"].as_array().map(|a| a.iter().map(|f| {
            let (rgb, c, r, tol) = (nums::<3>(&f["rgb"]).unwrap_or([0.0; 3]), nums::<2>(&f["at"]).unwrap_or([0.0; 2]), f["r"].as_f64().unwrap_or(30.0) as i64, f["tol"].as_f64().unwrap_or(40.0) as f32);
            let (mut sx, mut sy, mut n) = (0.0f64, 0.0f64, 0.0f64);
            for y in c[1] as i64 - r..=c[1] as i64 + r {
                for x in c[0] as i64 - r..=c[0] as i64 + r {
                    if let Some(p) = at(&dda, dw, dh, x, y) {
                        if (0..3).all(|k| (p[k] as f32 - rgb[k]).abs() <= tol) {
                            sx += x as f64 + 0.5;
                            sy += y as f64 + 0.5;
                            n += 1.0;
                        }
                    }
                }
            }
            if n > 0.0 { json!([sx / n, sy / n, n]) } else { json!(null) }
        }).collect()).unwrap_or_default();
        let diff = s.req["diff"].as_str().and_then(|k| self.t.kept.get(k)).filter(|o| o.len() == native.len() && !native.is_empty()).map(|o| {
            let (mut sum, mut big) = (0u64, 0u64);
            for (a, b) in o.chunks_exact(4).zip(native.chunks_exact(4)) {
                let d = (0..3).map(|c| a[c].abs_diff(b[c]) as u64).max().unwrap();
                sum += d;
                big += (d > 24) as u64;
            }
            let n = (native.len() / 4) as f64;
            json!({"mean": sum as f64 / n, "changed_share": big as f64 / n})
        });
        let (hid, posed, sel) = g.r.counts();
        let res = json!({
            "spp": g.r.n, "timed_out": timed_out, "converge_ms": converge_ms, "native": [rw, rh], "dda": [dw, dh], "dda_err": dda_err,
            "probe": {"n": probes.len(), "agree": agree, "page_only": page_only, "native_only": native_only, "far": far, "other_part": other, "skipped": skipped, "worst": worst},
            "depth": depth, "sample": sample, "found": found, "diff": diff,
            "bbox_native": if native.is_empty() { None } else { bbox(&native, rw, rh, bgc) },
            // the desktop may show the native picture at another brightness: its backdrop is read off a corner
            "bbox_dda": at(&dda, dw, dh, 24, 24).and_then(|c| bbox(&dda, dw, dh, c)),
            "counts": {"hidden": hid, "posed": posed, "sel": sel, "clip": g.r.look.clip},
            "bg": bgc,
        });
        if !s.name.is_empty() {
            self.t.kept.insert(s.name.clone(), native);
        }
        self.resume(s.id, &res.to_string());
    }

    /// One view for the quality comparison: the native picture at a fixed size, off screen, and the Blender
    /// tracer's picture of the same request from the page's server.
    fn t_quality(&mut self, id: u64, v: &Value) {
        let (name, req) = (v["name"].as_str().unwrap_or("q").to_string(), v["req"].clone());
        let (w, h) = (req["w"].as_u64().unwrap_or(1920) as u32, req["h"].as_u64().unwrap_or(1200) as u32);
        let dir = self.args.out.join("quality");
        let _ = std::fs::create_dir_all(&dir);
        let mut line = String::new();
        if let (Some(g), Some(m)) = (self.gfx.as_mut(), nums::<16>(&req["cam"])) {
            let cam = Camera::from_page(&m, req["fov"].as_f64().unwrap_or(40.0) as f32, req["near"].as_f64().unwrap_or(1.0) as f32);
            let (keep, vs, still) = (g.r.size(), g.r.look.vsize, g.r.settings.spf_still);
            g.r.look.vsize = None;
            g.r.resize(w, h);
            g.r.settings.spf_still = 16;
            let t0 = Instant::now();
            let mut first = true;
            while let Some(i) = g.r.render(&cam, first, false, None) {
                g.r.wait(i);
                first = false;
            }
            let ms = t0.elapsed().as_secs_f64() * 1e3;
            let px = g.r.read_pixels();
            save_png(&dir.join(format!("{name}_native.png")), w, h, &px);
            let _ = std::fs::write(dir.join(format!("{name}_req.json")), req.to_string());
            line = format!("native {w}x{h}, {} spp in {ms:.0} ms", g.r.n);
            g.r.look.vsize = vs;
            g.r.settings.spf_still = still;
            g.r.resize(keep.0, keep.1);
        }
        self.touch(false);
        let (proxy, url) = (self.proxy.clone(), format!("{}trace", self.base()));
        let body = req.to_string();
        let blender = v["blender"].as_bool().unwrap_or(true);
        std::thread::spawn(move || {
            let t0 = Instant::now();
            let r = if !blender {
                "Blender not asked".to_string()
            } else {
                match http::request(&url, Some(body.as_bytes()), 300) {
                    Ok((200, b)) => match std::fs::write(dir.join(format!("{name}_blender.jpg")), &b) {
                        Ok(_) => format!("Blender {} bytes of JPEG in {:.2} s", b.len(), t0.elapsed().as_secs_f64()),
                        Err(e) => format!("Blender picture not saved: {e}"),
                    },
                    Ok((c, b)) => format!("Blender: HTTP {c} {}", String::from_utf8_lossy(&b[..b.len().min(200)])),
                    Err(e) => format!("Blender: {e}"),
                }
            };
            let _ = proxy.send_event(Ev::Done(id, json!(format!("{line}; {r}")).to_string()));
        });
    }

    /// The folder the page came from, with its slash.
    fn base(&self) -> String {
        let u = self.args.url.split(['?', '#']).next().unwrap_or("");
        match u.rfind('/') {
            Some(i) if i > 7 => u[..=i].to_string(),
            _ => format!("{u}/"),
        }
    }

    /// The window, and the work done so far, as the selftest asks after them.
    fn win_info(&self) -> Value {
        let Some(g) = self.gfx.as_ref() else { return json!(null) };
        let (s, p) = (g.window.inner_size(), g.window.outer_position().unwrap_or_default());
        if self.t.chrome == 0 {
            // (found on first use by t_mouse / t_key)
        }
        let chrome = cap::children(g.hwnd).iter().find(|k| k.1 == "Chrome_RenderWidgetHostHWND").map(|k| k.0).unwrap_or(0);
        let focus = cap::focus_of(if chrome != 0 { chrome } else { g.hwnd });
        json!({
            "title": g.window.title(), "client": [s.width, s.height], "outer": [p.x, p.y],
            "minimized": g.window.is_minimized(), "maximized": g.window.is_maximized(),
            "renders": g.r.n_renders, "dispatches": g.r.n_dispatches, "presents": self.presents, "status_lines": self.stat_sent, "resizes": self.resizes,
            "foreground": cap::foreground() == g.hwnd, "focus_class": cap::class_name(focus), "focus_is_shell": focus == g.hwnd,
            "backend": g.backend, "spf_moving": g.r.settings.spf_moving, "spf_still": g.r.settings.spf_still, "budget_ms": g.r.settings.budget_ms,
            "spp": g.r.n, "cap": gpu::MAX_SPP,
        })
    }

    /// Real key messages: [where, virtual key, down?, ms to wait after].
    /// where 0: posted to the window that HAS the keyboard in the webview (as the desktop delivers a key
    ///          when the page has focus); 1: posted to the shell's own window (as when it has focus);
    ///          2: typed, through the desktop's own input queue (SendInput), only while this window is in front.
    fn t_key(&mut self, id: u64, v: &Value) {
        let Some(g) = self.gfx.as_ref() else { return };
        if self.t.chrome == 0 {
            self.t.chrome = cap::children(g.hwnd).iter().find(|k| k.1 == "Chrome_RenderWidgetHostHWND").map(|k| k.0).unwrap_or(0);
        }
        let (chrome, hwnd, proxy) = (self.t.chrome, g.hwnd, self.proxy.clone());
        let ops: Vec<(u64, u32, bool, u64)> = v["ops"].as_array().map(|a| a.iter().map(|o| (o[0].as_u64().unwrap_or(0), o[1].as_u64().unwrap_or(0) as u32, o[2].as_u64().unwrap_or(0) != 0, o[3].as_u64().unwrap_or(0))).collect()).unwrap_or_default();
        std::thread::spawn(move || {
            let (mut sent, mut skipped, mut class) = (0, 0, String::new());
            for (mode, vk, down, wait) in ops {
                match mode {
                    2 => {
                        if cap::foreground() == hwnd {
                            cap::type_key(vk, down);
                            sent += 1;
                        } else {
                            skipped += 1;
                        }
                    }
                    _ => {
                        let mut to = hwnd;
                        if mode == 0 {
                            to = cap::focus_of(chrome);
                            if to == 0 || to == hwnd {
                                to = chrome;
                            }
                        }
                        class = cap::class_name(to);
                        cap::post_key(to, vk, down);
                        sent += 1;
                    }
                }
                std::thread::sleep(Duration::from_millis(wait));
            }
            let _ = proxy.send_event(Ev::Done(id, json!({"sent": sent, "skipped": skipped, "to": class}).to_string()));
        });
    }

    /// The window sized as a person sizes it: the desktop's own sizing loop (the one a drag of the border
    /// runs: WM_ENTERSIZEMOVE, WM_SIZING and WM_SIZE as it goes, WM_EXITSIZEMOVE), entered by the system
    /// command and steered with arrow keys, which it takes as it takes the mouse. `keys`: [virtual key, ms].
    fn t_size(&mut self, id: u64, v: &Value) {
        let Some(g) = self.gfx.as_ref() else { return };
        let (hwnd, proxy) = (g.hwnd, self.proxy.clone());
        let keys: Vec<(u32, u64)> = v["keys"].as_array().map(|a| a.iter().map(|o| (o[0].as_u64().unwrap_or(0) as u32, o[1].as_u64().unwrap_or(30))).collect()).unwrap_or_default();
        std::thread::spawn(move || {
            let cur = cap::cursor();
            cap::post(hwnd, 0x0112, 0xF000, 0); // WM_SYSCOMMAND, SC_SIZE
            std::thread::sleep(Duration::from_millis(250));
            for (vk, wait) in keys {
                cap::post_key(hwnd, vk, true);
                cap::post_key(hwnd, vk, false);
                std::thread::sleep(Duration::from_millis(wait));
            }
            cap::post_key(hwnd, 0x0D, true); // Enter: done
            cap::post_key(hwnd, 0x0D, false);
            std::thread::sleep(Duration::from_millis(250));
            cap::set_cursor(cur); // (the sizing loop takes the pointer to the border: put back)
            let _ = proxy.send_event(Ev::Done(id, "true".into()));
        });
    }

    fn note_place(&mut self) {
        let Some(g) = self.gfx.as_ref() else { return };
        if g.window.is_maximized() || g.window.is_minimized() == Some(true) {
            return;
        }
        if let (Ok(p), s) = (g.window.outer_position(), g.window.inner_size()) {
            if s.width > 0 && s.height > 0 {
                self.place = [p.x, p.y, s.width as i32, s.height as i32];
            }
        }
    }

    /// The window's place, kept for the next run.
    fn save_place(&self) {
        let (Some(f), Some(g)) = (state_file(&self.args), self.gfx.as_ref()) else { return };
        let p = self.place;
        if p[2] > 0 {
            let _ = std::fs::write(f, json!({"x": p[0], "y": p[1], "w": p[2], "h": p[3], "max": g.window.is_maximized()}).to_string());
        }
    }

    fn selftest(&mut self) {
        if self.start.elapsed() > Duration::from_secs(900) {
            self.say("TIMEOUT: the selftest did not finish".into());
            self.t.done = true;
        }
        if self.t.shot.as_ref().is_some_and(|s| self.quiet() || s.t0.elapsed() > Duration::from_secs(25)) {
            let s = self.t.shot.take().unwrap();
            self.t_shot(s);
        }
        if let Some((id, w, h, t0)) = self.t.resize {
            let now = self.gfx.as_ref().map(|g| (g.config.width, g.config.height)).unwrap_or((0, 0));
            if (now == (w, h) && t0.elapsed() > Duration::from_millis(500)) || t0.elapsed() > Duration::from_secs(4) {
                self.t.resize = None;
                self.resume(id, &json!([now.0, now.1]).to_string());
            }
        }
        if self.t.done {
            let _ = std::fs::write(self.args.out.join(if self.args.only.is_empty() { "selftest.txt".to_string() } else { format!("selftest_{}.txt", self.args.only.replace(',', "_")) }), &self.t.log);
            self.quit = true;
        }
    }
}

impl ApplicationHandler<Ev> for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.gfx.is_some() {
            return;
        }
        let (g, said) = init_gfx(event_loop, &self.args, self.proxy.clone());
        g.window.request_redraw();
        if let (Ok(p), s) = (g.window.outer_position(), g.window.inner_size()) {
            self.place = [p.x, p.y, s.width as i32, s.height as i32];
        }
        self.gfx = Some(g);
        self.say(said);
        self.start = Instant::now();
    }

    fn user_event(&mut self, _: &ActiveEventLoop, ev: Ev) {
        match ev {
            Ev::Ipc(body) => self.on_ipc(&body),
            Ev::Model(url, r, ms) => self.on_model(url, r, ms),
            Ev::Done(id, r) => self.resume(id, &r),
            Ev::Title(t) => {
                if let Some(g) = self.gfx.as_ref() {
                    g.window.set_title(if t.is_empty() { "cadkit desk" } else { &t });
                }
            }
        }
    }

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if self.gfx.is_none() {
            return;
        }
        self.push_stats();
        // a change that could not be drawn when it came (the window was minimised): drawn once it can be
        if self.dirty && self.gfx.as_ref().is_some_and(|g| g.window.is_minimized() != Some(true)) && self.last_present.elapsed() > Duration::from_millis(100) {
            self.redraw();
        }
        if self.args.selftest && !self.quit {
            self.selftest();
            if self.quit {
                event_loop.exit();
            }
        }
        event_loop.set_control_flow(ControlFlow::WaitUntil(Instant::now() + Duration::from_millis(if self.args.selftest { 5 } else { 100 })));
    }

    fn window_event(&mut self, event_loop: &ActiveEventLoop, id: WindowId, event: WindowEvent) {
        let Some(g) = self.gfx.as_mut() else { return };
        if id != g.window.id() {
            return;
        }
        match event {
            WindowEvent::CloseRequested => {
                self.save_place();
                event_loop.exit()
            }
            WindowEvent::Resized(s) => {
                // (0 x 0: minimised. Nothing is resized for that, and nothing drawn until it is back.)
                if s.width > 0 && s.height > 0 {
                    if (g.config.width, g.config.height) != (s.width, s.height) {
                        g.config.width = s.width;
                        g.config.height = s.height;
                        g.surface.configure(&g.r.device, &g.config);
                        g.r.resize(s.width, s.height);
                        let _ = g.webview.set_bounds(wv_rect(s.width, s.height));
                        self.resizes += 1;
                    }
                    self.touch(false);
                    self.note_place();
                    self.redraw();
                }
            }
            WindowEvent::Moved(_) => self.note_place(),
            // the keys are the page's: when the window is given the keyboard it passes it on
            WindowEvent::Focused(true) => {
                let _ = g.webview.focus();
            }
            WindowEvent::ModifiersChanged(m) => {
                self.ctrl = m.state().control_key();
                self.shift = m.state().shift_key();
            }
            // a key that reached the shell's own window all the same (the page had not yet taken the keyboard):
            // it is handed to the page as the key it was, and the keyboard with it
            WindowEvent::KeyboardInput { event, .. } => {
                use winit::keyboard::{Key, NamedKey, PhysicalKey};
                use winit::platform::modifier_supplement::KeyEventExtModifierSupplement;
                let key = match event.key_without_modifiers() {
                    Key::Character(c) => Some(c.to_string()),
                    Key::Named(NamedKey::Space) => Some(" ".to_string()),
                    Key::Named(NamedKey::Escape) => Some("Escape".to_string()),
                    _ => None,
                };
                if let Some(k) = key {
                    let code = match event.physical_key {
                        PhysicalKey::Code(c) => format!("{c:?}"),
                        _ => String::new(),
                    };
                    let js = format!(
                        "window.dispatchEvent(new KeyboardEvent('{}',{{key:{},code:{},ctrlKey:{},shiftKey:{},repeat:{},bubbles:true,cancelable:true}}))",
                        if event.state.is_pressed() { "keydown" } else { "keyup" },
                        json!(k),
                        json!(code),
                        self.ctrl,
                        self.shift,
                        event.repeat
                    );
                    let _ = g.webview.evaluate_script(&js);
                }
                let _ = g.webview.focus();
            }
            WindowEvent::RedrawRequested => self.redraw(),
            _ => {}
        }
    }
}

fn main() {
    let mut a = std::env::args().skip(1);
    let mut args = Args { url: "http://127.0.0.1:8161/".into(), selftest: false, only: String::new(), out: PathBuf::from("out"), backend: None, dxc: None, state: None, data: None, recopy: None };
    while let Some(x) = a.next() {
        match x.as_str() {
            "--selftest" => args.selftest = true,
            "--out" => args.out = PathBuf::from(a.next().expect("--out <dir>")),
            "--backend" => args.backend = Some(a.next().expect("--backend dx12|vulkan")),
            "--dxc" => args.dxc = a.next(),
            "--state" => args.state = a.next().map(PathBuf::from),
            "--data" => args.data = a.next().map(PathBuf::from),
            "--recopy" => args.recopy = Some((PathBuf::from(a.next().expect("--recopy <from> <to>")), PathBuf::from(a.next().expect("--recopy <from> <to>")))),
            "-h" | "--help" => {
                eprintln!("usage: desk [url] [--selftest[=parts]] [--out <dir>] [--backend dx12|vulkan] [--dxc <dxcompiler.dll>] [--state <file>] [--data <dir>]     (url defaults to http://127.0.0.1:8161/)");
                return;
            }
            _ if x.starts_with("--selftest=") => {
                args.selftest = true;
                args.only = x["--selftest=".len()..].to_string();
            }
            _ => args.url = x,
        }
    }
    if args.selftest {
        std::fs::create_dir_all(&args.out).unwrap();
        cap::keep_display_awake();
    }
    let event_loop = EventLoop::<Ev>::with_user_event().build().unwrap();
    let now = Instant::now();
    let mut app = App {
        args,
        proxy: event_loop.create_proxy(),
        gfx: None,
        view: View::default(),
        names: HashMap::new(),
        part_names: vec![],
        glb_want: String::new(),
        glb_have: String::new(),
        loading: 0,
        dirty: true,
        rigid: false,
        start: now,
        last_msg: now,
        last_present: now,
        t_dirty: now,
        converge_ms: 0.0,
        stat_t: now,
        stat_frames: 0,
        stat_gpu: 0.0,
        stat_last: String::new(),
        meas: Meas::default(),
        t: Test::default(),
        quit: false,
        presents: 0,
        stat_sent: 0,
        resizes: 0,
        ctrl: false,
        shift: false,
        place: [0; 4],
    };
    event_loop.run_app(&mut app).unwrap();
    app.save_place();
    // drop the webview (and its browser processes) before the window goes away
    drop(app.gfx.take());
    println!("closed");
    use std::io::Write;
    let _ = std::io::stdout().flush();
    // Left to unwind by itself the process came out with exit code 122 although everything had gone well
    // (something in the teardown of the webview's or the card's DLLs: not tracked down). It is ended here,
    // with the code that is true.
    cap::end_process(0);
}
