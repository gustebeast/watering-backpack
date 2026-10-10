//! The tabbed app's projects: where a project's model folder is, what it is called, when it was last built,
//! what is kept of them between runs, and the answers its page is given in place of a server's.
use serde_json::{Value, json};
use std::borrow::Cow;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;
use wry::http::{Request, Response};

/// The viewer page, AS IT WAS WHEN THIS PROGRAM WAS BUILT: the program and the page it lays over its
/// picture are always of one version, and the app needs no cadkit, no Python and no server to show it.
pub const PAGE: &str = include_str!("../../web/viewer/index.html");
/// The tab strip and the projects list.
pub const STRIP: &str = include_str!("tabs.html");
/// The strip's height, in the page's (CSS) pixels: tabs.html lays itself out to this.
pub const STRIP_CSS_PX: f64 = 34.0;

/// A folder as it is told apart from another: the real path, without Windows' long-path prefix.
fn plain(p: PathBuf) -> PathBuf {
    let s = p.to_string_lossy();
    match s.strip_prefix(r"\\?\") {
        Some(rest) if !rest.starts_with("UNC") => PathBuf::from(rest),
        _ => p,
    }
}

/// The model folder a caller named, if it is one: an existing folder with a model in it.
pub fn model_dir(dir: &str) -> Result<PathBuf, String> {
    let p = Path::new(dir);
    if dir.is_empty() || !p.is_absolute() {
        return Err(format!("not an absolute folder: {dir}"));
    }
    let p = plain(std::fs::canonicalize(p).map_err(|e| format!("{dir}: {e}"))?);
    if !p.is_dir() {
        return Err(format!("not a folder: {dir}"));
    }
    if !p.join("assembly.glb").is_file() {
        return Err(format!("no model (assembly.glb) in {dir}"));
    }
    Ok(p)
}

pub fn same(a: &Path, b: &Path) -> bool {
    a.to_string_lossy().to_lowercase() == b.to_string_lossy().to_lowercase()
}

/// A PROJECT'S OWN ORIGIN. The page keeps its view (camera, hidden parts, section) in the browser's
/// storage, which is kept per origin: so each project's page is served from a host of its own, made of the
/// folder's path, the same in every run. Two projects never share a saved view; one project always finds its own.
pub fn key(dir: &Path) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in dir.to_string_lossy().to_lowercase().bytes() {
        h = (h ^ b as u64).wrapping_mul(0x100000001b3);
    }
    format!("p{h:016x}")
}

/// The address a project's page is loaded from (wry hands it to WebView2 as http://cadkit.<key>.localhost/).
pub fn url(dir: &Path) -> String {
    format!("cadkit://{}.localhost/", key(dir))
}

/// The project's folder name: a model folder is <project>/.webview.
pub fn folder_name(dir: &Path) -> String {
    let own = dir.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    if own.starts_with('.') {
        if let Some(n) = dir.parent().and_then(|p| p.file_name()) {
            return n.to_string_lossy().to_string();
        }
    }
    own
}

/// The title the model's own file gives it (asset.extras.title), if it gives one.
fn glb_title(dir: &Path) -> Option<String> {
    use std::io::Read;
    let mut f = std::fs::File::open(dir.join("assembly.glb")).ok()?;
    let mut head = [0u8; 20];
    f.read_exact(&mut head).ok()?;
    if &head[0..4] != b"glTF" {
        return None;
    }
    let n = u32::from_le_bytes([head[12], head[13], head[14], head[15]]) as usize;
    if n > 64 << 20 {
        return None;
    }
    let mut j = vec![0u8; n];
    f.read_exact(&mut j).ok()?;
    let v: Value = serde_json::from_slice(&j).ok()?;
    v["asset"]["extras"]["title"].as_str().map(str::trim).filter(|t| !t.is_empty()).map(String::from)
}

/// A COPY OF A PROJECT IN A FOLDER OF ITS OWN (a worktree: public-steel-guitar-bronner beside
/// public-steel-guitar) builds a model with the same title, so its tab says whose it is: what the folder's
/// name has after the title ("Public Steel Guitar · bronner").
pub fn title(dir: &Path) -> String {
    let folder = folder_name(dir);
    let Some(t) = glb_title(dir) else { return folder };
    let slug = |s: &str| s.chars().filter(|c| c.is_alphanumeric()).flat_map(char::to_lowercase).collect::<String>();
    let (mut want, mut at) = (slug(&t).len(), 0);
    if want > 0 && slug(&folder).starts_with(&slug(&t)) {
        for (i, c) in folder.char_indices() {
            if want == 0 { at = i; break; }
            if c.is_alphanumeric() { want -= 1; }
        }
        let rest = if at > 0 { folder[at..].trim_matches(|c: char| !c.is_alphanumeric()) } else { "" };
        if !rest.is_empty() { return format!("{t} · {rest}"); }
    }
    t
}

fn mtime_ns(p: &Path) -> Option<u128> {
    std::fs::metadata(p).ok()?.modified().ok()?.duration_since(UNIX_EPOCH).ok().map(|d| d.as_nanos())
}

/// When the model in a folder was last written, as a build ends writing it: its stamp's time, else the
/// model file's. 0: there is none.
pub fn stamp(dir: &Path) -> u128 {
    mtime_ns(&dir.join("stamp.json")).or_else(|| mtime_ns(&dir.join("assembly.glb"))).unwrap_or(0)
}

/// The model file's time alone (what the picture's own copy of it is told apart by).
pub fn glb_time(dir: &Path) -> u128 {
    mtime_ns(&dir.join("assembly.glb")).unwrap_or(0)
}

// ── what is kept between runs: <data>/projects.json, <data>/session.json ───────────
/// Every project ever opened: [{dir, name, opened}], `opened` in seconds since 1970.
pub fn load_projects(data: &Path) -> Vec<Value> {
    std::fs::read_to_string(data.join("projects.json")).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok()).and_then(|v| v.as_array().cloned()).unwrap_or_default()
}

/// Written beside, then put in place: a file half written is never read back.
pub fn write(path: &Path, v: &Value) {
    let tmp = path.with_extension("tmp");
    if std::fs::write(&tmp, serde_json::to_string_pretty(v).unwrap_or_default()).is_ok() {
        let _ = std::fs::rename(&tmp, path);
    }
}

pub fn now() -> f64 {
    std::time::SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

/// `dir` has been opened: noted in the list (made if this is its first time).
pub fn note_project(list: &mut Vec<Value>, dir: &Path, name: &str) {
    let d = dir.to_string_lossy().to_string();
    // (cadkit's web server keeps the same list, and gives each project a `key`: its address there. Kept.)
    let was = list.iter().position(|p| p["dir"].as_str().is_some_and(|x| same(Path::new(x), dir))).map(|i| list.remove(i));
    let mut row = json!({"dir": d, "name": name, "opened": now()});
    if let Some(k) = was.as_ref().and_then(|w| w.get("key")) {
        row["key"] = k.clone();
    }
    list.push(row);
}

/// The list as the page shows it: the model's time found now, newest built first, the ones whose folder
/// or model is gone last.
pub fn projects_for_page(list: &[Value], open: &[PathBuf], title: &mut dyn FnMut(&Path) -> String) -> Value {
    let mut rows: Vec<(f64, Value)> = list
        .iter()
        .filter_map(|p| {
            let dir = PathBuf::from(p["dir"].as_str()?);
            let built = mtime_ns(&dir.join("assembly.glb")).map(|n| n as f64 / 1e9);
            // (the name as it is now, if the model can be read; else as it was when last opened)
            let name = if built.is_some() { title(&dir) } else { p["name"].as_str().unwrap_or("").to_string() };
            let name = if name.is_empty() { folder_name(&dir) } else { name };
            Some((built.unwrap_or(-1.0), json!({"dir": p["dir"], "name": name, "folder": folder_name(&dir), "built": built, "missing": built.is_none(), "open": open.iter().any(|o| same(o, &dir))})))
        })
        .collect();
    rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    Value::Array(rows.into_iter().map(|r| r.1).collect())
}

// ── the page's server, without a server ────────────────────────────────────────────
fn kind(name: &str) -> &'static str {
    match name.rsplit('.').next().unwrap_or("").to_ascii_lowercase().as_str() {
        "html" | "htm" => "text/html; charset=utf-8",
        "json" => "application/json",
        "js" | "mjs" => "text/javascript",
        "css" => "text/css",
        "glb" => "model/gltf-binary",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "svg" => "image/svg+xml",
        "txt" => "text/plain; charset=utf-8",
        _ => "application/octet-stream",
    }
}

fn answer(code: u16, kind: &str, body: Vec<u8>) -> Response<Cow<'static, [u8]>> {
    // (never cached: a model built again is read again, as from cadkit's own server)
    Response::builder().status(code).header("Content-Type", kind).header("Cache-Control", "no-store").body(Cow::Owned(body)).unwrap()
}

/// What cadkit.web.view's server answers, answered from here: the page (the one built into this program,
/// or `page`, a file, for working on the page itself), the model folder's files as they are on disk now,
/// and the three small questions the page asks its server.
pub fn respond(dir: &Path, page: Option<&Path>, req: &Request<Vec<u8>>) -> Response<Cow<'static, [u8]>> {
    let name = req.uri().path().trim_start_matches('/');
    if req.method() != "GET" {
        // (the one thing the page posts is a view for cadkit's Blender tracer: there is none here)
        return answer(404, "text/plain; charset=utf-8", b"not here".to_vec());
    }
    match name {
        "" | "index.html" => match page {
            Some(f) => match std::fs::read(f) {
                Ok(b) => answer(200, kind("x.html"), b),
                Err(e) => answer(500, "text/plain; charset=utf-8", format!("{}: {e}", f.display()).into_bytes()),
            },
            None => answer(200, kind("x.html"), PAGE.as_bytes().to_vec()),
        },
        // when the page was last edited: the built-in one never is; a file's reloads itself as from the server
        "page.json" => answer(200, kind(name), json!({"t": page.and_then(mtime_ns).map(|n| n as f64).unwrap_or(0.0)}).to_string().into_bytes()),
        "where.json" => answer(200, kind(name), json!({"dir": dir.to_string_lossy(), "page": page.map(|p| p.to_string_lossy().to_string()).unwrap_or_else(|| "built in".into())}).to_string().into_bytes()),
        "trace.json" => answer(200, kind(name), b"{\"available\": false}".to_vec()),
        _ => {
            // a file of the model folder, and of nowhere else
            let rel = Path::new(name);
            let inside = rel.components().all(|c| matches!(c, std::path::Component::Normal(_)));
            match inside.then(|| std::fs::read(dir.join(rel))) {
                Some(Ok(b)) => answer(200, kind(name), b),
                _ => answer(404, "text/plain; charset=utf-8", b"not found".to_vec()),
            }
        }
    }
}
