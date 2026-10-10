//! Win32 helpers for the selftest: window capture, child-window lookup, posted mouse input.
use std::ptr::null_mut;
use windows_sys::Win32::Foundation::{BOOL, HWND, LPARAM, POINT, RECT};
use windows_sys::Win32::Graphics::Gdi::*;
use windows_sys::Win32::Storage::Xps::PrintWindow;
use windows_sys::Win32::UI::WindowsAndMessaging::*;

pub fn hwnd(h: isize) -> HWND {
    h as HWND
}

pub fn client_size(h: isize) -> (u32, u32) {
    unsafe {
        let mut rc: RECT = std::mem::zeroed();
        GetClientRect(hwnd(h), &mut rc);
        ((rc.right - rc.left) as u32, (rc.bottom - rc.top) as u32)
    }
}

/// Capture the client area as RGBA. `screen`: copy the pixels DWM put on the desktop at the window's
/// position (what the user sees, provided nothing covers the window); else PrintWindow with
/// PW_CLIENTONLY | PW_RENDERFULLCONTENT.
pub fn capture(h: isize, screen: bool) -> (u32, u32, Vec<u8>, bool) {
    unsafe {
        let (w, hh) = client_size(h);
        let sdc = GetDC(null_mut());
        let mem = CreateCompatibleDC(sdc);
        let bmp = CreateCompatibleBitmap(sdc, w as i32, hh as i32);
        let old = SelectObject(mem, bmp);
        let ok = if screen {
            let mut p = POINT { x: 0, y: 0 };
            ClientToScreen(hwnd(h), &mut p);
            BitBlt(mem, 0, 0, w as i32, hh as i32, sdc, p.x, p.y, SRCCOPY) != 0
        } else {
            PrintWindow(hwnd(h), mem, 1 | 2) != 0
        };
        let mut bi: BITMAPINFO = std::mem::zeroed();
        bi.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        bi.bmiHeader.biWidth = w as i32;
        bi.bmiHeader.biHeight = -(hh as i32);
        bi.bmiHeader.biPlanes = 1;
        bi.bmiHeader.biBitCount = 32;
        let mut buf = vec![0u8; (w * hh * 4) as usize];
        GetDIBits(mem, bmp, 0, hh, buf.as_mut_ptr() as *mut _, &mut bi, DIB_RGB_COLORS);
        for px in buf.chunks_exact_mut(4) {
            px.swap(0, 2);
            px[3] = 255;
        }
        SelectObject(mem, old);
        DeleteObject(bmp);
        DeleteDC(mem);
        ReleaseDC(null_mut(), sdc);
        (w, hh, buf, ok)
    }
}

fn class_of(h: HWND) -> String {
    let mut b = [0u16; 128];
    let n = unsafe { GetClassNameW(h, b.as_mut_ptr(), 128) };
    String::from_utf16_lossy(&b[..n.max(0) as usize])
}

unsafe extern "system" fn enum_cb(h: HWND, l: LPARAM) -> BOOL {
    let v = unsafe { &mut *(l as *mut Vec<(isize, String)>) };
    v.push((h as isize, class_of(h)));
    1
}

/// All descendant windows (handle, class name).
pub fn children(h: isize) -> Vec<(isize, String)> {
    let mut v: Vec<(isize, String)> = vec![];
    unsafe { EnumChildWindows(hwnd(h), Some(enum_cb), &mut v as *mut _ as LPARAM) };
    v
}

/// Which window would receive a real mouse event at this client position of `top`?
/// Returns (class name, belongs to `top`).
pub fn hit_test(top: isize, x: i32, y: i32) -> (String, bool) {
    unsafe {
        let mut p = POINT { x, y };
        ClientToScreen(hwnd(top), &mut p);
        let hit = WindowFromPoint(p);
        (class_of(hit), GetAncestor(hit, GA_ROOT) == hwnd(top))
    }
}

pub fn post_mouse(h: isize, msg: u32, wparam: usize, x: i32, y: i32) {
    unsafe { PostMessageW(hwnd(h), msg, wparam, (((y as u16 as u32) << 16) | (x as u16 as u32)) as isize) };
}

pub fn client_to_screen(h: isize, x: i32, y: i32) -> (i32, i32) {
    unsafe {
        let mut p = POINT { x, y };
        ClientToScreen(hwnd(h), &mut p);
        (p.x, p.y)
    }
}

/// Selftest only: captures of the real desktop need the monitor awake. Hold the display on for the life of
/// this process and nudge the mouse by one pixel and back (injected input is what wakes a sleeping display).
pub fn keep_display_awake() {
    use windows_sys::Win32::System::Power::*;
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::*;
    unsafe {
        SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED);
        for dx in [1, -1] {
            let mut i: INPUT = std::mem::zeroed();
            i.r#type = INPUT_MOUSE;
            i.Anonymous.mi.dx = dx;
            i.Anonymous.mi.dwFlags = MOUSEEVENTF_MOVE;
            SendInput(1, &i, std::mem::size_of::<INPUT>() as i32);
        }
    }
}

pub fn class_name(h: isize) -> String {
    if h == 0 { String::new() } else { class_of(hwnd(h)) }
}

/// The window that has the keyboard in the thread that owns `h` (0: none there).
pub fn focus_of(h: isize) -> isize {
    unsafe {
        let tid = GetWindowThreadProcessId(hwnd(h), null_mut());
        let mut gi: GUITHREADINFO = std::mem::zeroed();
        gi.cbSize = std::mem::size_of::<GUITHREADINFO>() as u32;
        if tid == 0 || GetGUIThreadInfo(tid, &mut gi) == 0 {
            return 0;
        }
        gi.hwndFocus as isize
    }
}

pub fn foreground() -> isize {
    unsafe { GetForegroundWindow() as isize }
}

pub fn post(h: isize, msg: u32, wparam: usize, lparam: isize) {
    unsafe { PostMessageW(hwnd(h), msg, wparam, lparam) };
}

/// WM_KEYDOWN / WM_KEYUP as the keyboard driver words them (scan code, repeat count, transition bits).
pub fn post_key(h: isize, vk: u32, down: bool) {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{MAPVK_VK_TO_VSC, MapVirtualKeyW};
    let scan = unsafe { MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) } as isize;
    let l = 1 | (scan << 16) | if down { 0 } else { 0xC000_0000u32 as i32 as isize };
    post(h, if down { 0x0100 } else { 0x0101 }, vk as usize, l);
}

/// One key down or up through the desktop's input queue: it goes to whatever has the keyboard.
pub fn type_key(vk: u32, down: bool) {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::*;
    unsafe {
        let mut i: INPUT = std::mem::zeroed();
        i.r#type = INPUT_KEYBOARD;
        i.Anonymous.ki.wVk = vk as u16;
        i.Anonymous.ki.dwFlags = if down { 0 } else { KEYEVENTF_KEYUP };
        SendInput(1, &i, std::mem::size_of::<INPUT>() as i32);
    }
}

pub fn cursor() -> (i32, i32) {
    unsafe {
        let mut p = POINT { x: 0, y: 0 };
        GetCursorPos(&mut p);
        (p.x, p.y)
    }
}

pub fn set_cursor(p: (i32, i32)) {
    unsafe { SetCursorPos(p.0, p.1) };
}

/// End this process now with this exit code (no DLL gets to run an exit handler and choose another).
pub fn end_process(code: u32) -> ! {
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, TerminateProcess};
    unsafe { TerminateProcess(GetCurrentProcess(), code) };
    std::process::exit(code as i32)
}

/// The left mouse button, down or up, through the desktop's input queue, where the pointer is.
pub fn type_button(down: bool) {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::*;
    unsafe {
        let mut i: INPUT = std::mem::zeroed();
        i.r#type = INPUT_MOUSE;
        i.Anonymous.mi.dwFlags = if down { MOUSEEVENTF_LEFTDOWN } else { MOUSEEVENTF_LEFTUP };
        SendInput(1, &i, std::mem::size_of::<INPUT>() as i32);
    }
}
