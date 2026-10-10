//! DXGI Desktop Duplication capture (selftest): the frame DWM actually sends to the monitor, cropped to the
//! window's client area. Unlike the GDI paths (BitBlt of the screen DC, PrintWindow) this sees every kind of
//! swapchain, and it is HDR-aware: scRGB float frames are scaled back by the SDR white level (calibrated on
//! an opaque pure-green page element) and sRGB-encoded. The window must not be covered by another window.
use crate::cap::{client_size, client_to_screen};
use std::cell::RefCell;
use windows::Win32::Foundation::HMODULE;
use windows::Win32::Graphics::Direct3D::D3D_DRIVER_TYPE_HARDWARE;
use windows::Win32::Graphics::Direct3D11::*;
use windows::Win32::Graphics::Dxgi::Common::*;
use windows::Win32::Graphics::Dxgi::*;
use windows::core::Interface;

struct Dda {
    device: ID3D11Device,
    ctx: ID3D11DeviceContext,
    dup: IDXGIOutputDuplication,
    staging: Option<ID3D11Texture2D>,
    org: (i32, i32),
    scale: f32,
    float: bool,
}

thread_local! { static DDA: RefCell<Option<Dda>> = const { RefCell::new(None) }; }

fn half(h: u16) -> f32 {
    let (s, e, m) = ((h >> 15) & 1, ((h >> 10) & 0x1f) as i32, (h & 0x3ff) as f32);
    let v = if e == 0 {
        m / 1024.0 * 2f32.powi(-14)
    } else if e == 31 {
        f32::MAX
    } else {
        (1.0 + m / 1024.0) * 2f32.powi(e - 15)
    };
    if s == 1 { -v } else { v }
}

fn srgb(v: f32) -> u8 {
    let v = v.clamp(0.0, 1.0);
    ((if v <= 0.0031308 { v * 12.92 } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 }) * 255.0).round() as u8
}

pub fn init(h: isize) -> Result<String, String> {
    let (w, hh) = client_size(h);
    let (sx, sy) = client_to_screen(h, 0, 0);
    let e = |s: &str, e: windows::core::Error| format!("desktop duplication unavailable: {s}: {e}");
    unsafe {
        let (mut device, mut ctx) = (None, None);
        D3D11CreateDevice(None, D3D_DRIVER_TYPE_HARDWARE, HMODULE::default(), D3D11_CREATE_DEVICE_BGRA_SUPPORT, None, D3D11_SDK_VERSION, Some(&mut device), None, Some(&mut ctx)).map_err(|x| e("D3D11CreateDevice", x))?;
        let (device, ctx) = (device.unwrap(), ctx.unwrap());
        let adapter = device.cast::<IDXGIDevice>().map_err(|x| e("IDXGIDevice", x))?.GetAdapter().map_err(|x| e("GetAdapter", x))?;
        let (cx, cy) = (sx + w as i32 / 2, sy + hh as i32 / 2);
        let mut i = 0;
        let (out, org) = loop {
            let out = adapter.EnumOutputs(i).map_err(|x| e("no output contains the window", x))?;
            let r = out.GetDesc().map_err(|x| e("GetDesc", x))?.DesktopCoordinates;
            if cx >= r.left && cx < r.right && cy >= r.top && cy < r.bottom {
                break (out, (r.left, r.top));
            }
            i += 1;
        };
        let dup = match out.cast::<IDXGIOutput5>() {
            Ok(o5) => o5.DuplicateOutput1(&device, 0, &[DXGI_FORMAT_R16G16B16A16_FLOAT, DXGI_FORMAT_B8G8R8A8_UNORM]).map_err(|x| e("DuplicateOutput1", x))?,
            Err(_) => out.cast::<IDXGIOutput1>().map_err(|x| e("IDXGIOutput1", x))?.DuplicateOutput(&device).map_err(|x| e("DuplicateOutput", x))?,
        };
        let d = dup.GetDesc();
        let float = d.ModeDesc.Format == DXGI_FORMAT_R16G16B16A16_FLOAT;
        let msg = format!("desktop duplication: output {}x{}, {}", d.ModeDesc.Width, d.ModeDesc.Height, if float { "HDR desktop (scRGB float frames)" } else { "SDR desktop (BGRA8 frames)" });
        DDA.with(|c| *c.borrow_mut() = Some(Dda { device, ctx, dup, staging: None, org, scale: std::env::var("APP_SDR_SCALE").ok().and_then(|v| v.parse().ok()).unwrap_or(1.0), float }));
        Ok(msg)
    }
}

/// `green`: client rect of an opaque rgb(0,255,0) element, used to calibrate the SDR white level on HDR desktops.
pub fn capture(h: isize, green: Option<[f64; 4]>) -> Result<(u32, u32, Vec<u8>), String> {
    let (w, hh) = client_size(h);
    let (sx, sy) = client_to_screen(h, 0, 0);
    DDA.with(|c| unsafe {
        let mut c = c.borrow_mut();
        let Some(dda) = c.as_mut() else { return Err("not initialised".to_string()) };
        // take the pending desktop updates (the newest image); with a static desktop keep the last one
        for k in 0..3 {
            let mut info = DXGI_OUTDUPL_FRAME_INFO::default();
            let mut res: Option<IDXGIResource> = None;
            if dda.dup.AcquireNextFrame(if k == 0 { 400 } else { 20 }, &mut info, &mut res).is_err() {
                break;
            }
            if let Some(tex) = res.and_then(|r| r.cast::<ID3D11Texture2D>().ok()) {
                if dda.staging.is_none() {
                    let mut d = D3D11_TEXTURE2D_DESC::default();
                    tex.GetDesc(&mut d);
                    d.Usage = D3D11_USAGE_STAGING;
                    d.BindFlags = 0;
                    d.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
                    d.MiscFlags = 0;
                    let mut st = None;
                    dda.device.CreateTexture2D(&d, None, Some(&mut st)).map_err(|x| format!("CreateTexture2D: {x}"))?;
                    dda.staging = st;
                }
                dda.ctx.CopyResource(dda.staging.as_ref().unwrap(), &tex);
            }
            let _ = dda.dup.ReleaseFrame();
        }
        let Some(st) = dda.staging.clone() else { return Err("no desktop frame arrived (display asleep?)".to_string()) };
        let mut d = D3D11_TEXTURE2D_DESC::default();
        st.GetDesc(&mut d);
        let mut m = D3D11_MAPPED_SUBRESOURCE::default();
        dda.ctx.Map(&st, 0, D3D11_MAP_READ, 0, Some(&mut m)).map_err(|x| format!("Map: {x}"))?;
        let (ox, oy) = (sx - dda.org.0, sy - dda.org.1);
        let bpp = if dda.float { 8 } else { 4 };
        let px = |x: i32, y: i32| -> Option<&[u8]> {
            let (xx, yy) = (x + ox, y + oy);
            if xx < 0 || yy < 0 || xx >= d.Width as i32 || yy >= d.Height as i32 {
                return None;
            }
            Some(std::slice::from_raw_parts((m.pData as *const u8).add(yy as usize * m.RowPitch as usize + xx as usize * bpp), bpp))
        };
        let h16 = |p: &[u8], i: usize| half(u16::from_le_bytes([p[i * 2], p[i * 2 + 1]]));
        if let (true, Some(r)) = (dda.float, green) {
            let (mut s, mut n) = (0.0f32, 0.0f32);
            for y in (r[1] + 6.0) as i32..(r[1] + r[3] - 6.0) as i32 {
                for x in (r[0] + 6.0) as i32..(r[0] + r[2] - 6.0) as i32 {
                    if let Some(p) = px(x, y) {
                        s += h16(p, 1);
                        n += 1.0;
                    }
                }
            }
            if n > 0.0 && s / n > 0.05 {
                dda.scale = s / n;
            }
        }
        let mut buf = vec![0u8; (w * hh * 4) as usize];
        for y in 0..hh as i32 {
            for x in 0..w as i32 {
                let Some(p) = px(x, y) else { continue };
                let t = ((y as u32 * w + x as u32) * 4) as usize;
                if dda.float {
                    for ch in 0..3 {
                        buf[t + ch] = srgb(h16(p, ch) / dda.scale);
                    }
                } else {
                    buf[t] = p[2];
                    buf[t + 1] = p[1];
                    buf[t + 2] = p[0];
                }
                buf[t + 3] = 255;
            }
        }
        dda.ctx.Unmap(&st, 0);
        Ok((w, hh, buf))
    })
}

/// (SDR white level in scRGB units, desktop is HDR)
pub fn scale() -> (f32, bool) {
    DDA.with(|c| c.borrow().as_ref().map(|d| (d.scale, d.float)).unwrap_or((1.0, false)))
}
