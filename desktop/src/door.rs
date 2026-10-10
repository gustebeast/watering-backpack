//! The app's control door: a few tiny HTTP GETs on loopback, by which a second start of the program, and
//! cadkit's Python, find the one that is running and tell it which project to show.
//!   /ping                          -> {app, version, pid, exe, data}
//!   /open?dir=<folder>&focus=0|1   -> the project's tab opened, or told to look for a new model
//!   /quit                          -> the session saved, the program ended
//! Nothing else is answered (but /test/..., and that only in a program started with --probe).
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::sync::mpsc;
use std::time::Duration;

pub const PORT: u16 = 8136;

/// The port the door is on: CADKIT_DESKTOP_PORT, else 8136.
pub fn port() -> u16 {
    std::env::var("CADKIT_DESKTOP_PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(PORT)
}

/// One request through the door: its path, and its query's pairs, decoded.
pub struct Req {
    pub path: String,
    pub query: Vec<(String, String)>,
    /// where the answer (a JSON document) goes
    pub answer: mpsc::Sender<String>,
}

impl Req {
    pub fn get(&self, k: &str) -> Option<&str> {
        self.query.iter().find(|(n, _)| n == k).map(|(_, v)| v.as_str())
    }
}

/// %XX and + in a query's value.
pub fn decode(s: &str) -> String {
    let b = s.as_bytes();
    let mut o = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        let hex = if b[i] == b'%' { b.get(i + 1..i + 3).and_then(|h| std::str::from_utf8(h).ok()).and_then(|h| u8::from_str_radix(h, 16).ok()) } else { None };
        match (b[i], hex) {
            (_, Some(x)) => {
                o.push(x);
                i += 3;
            }
            (b'+', _) => {
                o.push(b' ');
                i += 1;
            }
            (c, _) => {
                o.push(c);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&o).to_string()
}

/// A query's value, made safe to put in one.
pub fn encode(s: &str) -> String {
    let mut o = String::new();
    for &c in s.as_bytes() {
        if c.is_ascii_alphanumeric() || b"-_.~/:".contains(&c) {
            o.push(c as char);
        } else {
            o += &format!("%{c:02X}");
        }
    }
    o
}

fn reply(s: &mut TcpStream, code: u16, body: &str) {
    let what = match code {
        200 => "OK",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        _ => "Error",
    };
    let _ = s.write_all(format!("HTTP/1.0 {code} {what}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n{body}", body.len()).as_bytes());
}

fn serve(mut s: TcpStream, ping: &str, probe: bool, send: &dyn Fn(Req) -> bool) {
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = s.set_write_timeout(Some(Duration::from_secs(5)));
    let mut head = String::new();
    {
        // the request's head and no more of it than a few kilobytes: nothing here has a body
        let mut r = BufReader::new((&mut s).take(8192));
        loop {
            let mut line = String::new();
            match r.read_line(&mut line) {
                Ok(n) if n > 0 && line != "\r\n" && line != "\n" => head += &line,
                _ => break,
            }
        }
    }
    let mut lines = head.lines();
    let mut first = lines.next().unwrap_or("").split_whitespace();
    let (method, target) = (first.next().unwrap_or(""), first.next().unwrap_or(""));
    if method != "GET" {
        return reply(&mut s, 405, "{\"error\":\"only GET\"}");
    }
    // NOT FOR WEB PAGES. A page in a browser can make this machine's browser send a GET here (an image's
    // address is enough). Every browser says so in the request (where it comes from, what kind it is);
    // cadkit's own callers say nothing of the kind, and only they are answered.
    for l in lines {
        let l = l.to_ascii_lowercase();
        if l.starts_with("origin:") || l.starts_with("referer:") || l.starts_with("sec-fetch-") {
            return reply(&mut s, 403, "{\"error\":\"not for web pages\"}");
        }
        if let Some(h) = l.strip_prefix("host:") {
            let h = h.trim();
            if !(h.starts_with("127.0.0.1") || h.starts_with("localhost")) {
                return reply(&mut s, 403, "{\"error\":\"loopback only\"}");
            }
        }
    }
    let (path, q) = target.split_once('?').unwrap_or((target, ""));
    if path == "/ping" {
        return reply(&mut s, 200, ping);
    }
    if !(path == "/open" || path == "/quit" || (probe && path.starts_with("/test/"))) {
        return reply(&mut s, 404, "{\"error\":\"no such thing\"}");
    }
    let query = q.split('&').filter(|p| !p.is_empty()).map(|p| p.split_once('=').unwrap_or((p, ""))).map(|(k, v)| (decode(k), decode(v))).collect();
    let (tx, rx) = mpsc::channel();
    if !send(Req { path: path.to_string(), query, answer: tx }) {
        return reply(&mut s, 500, "{\"error\":\"the window is gone\"}");
    }
    // (a probe's capture waits for the picture to come to rest: that may take a while)
    match rx.recv_timeout(Duration::from_secs(if probe { 60 } else { 10 })) {
        Ok(body) => reply(&mut s, 200, &body),
        Err(_) => reply(&mut s, 500, "{\"error\":\"no answer\"}"),
    }
}

/// Open the door. Err: the port is taken (by another of these, or by something else).
/// `ping`: the answer to /ping, which is given from here, so that it is given even while the window's
/// thread is busy. `send`: hands a request to the window's thread; false if there is none any more.
pub fn listen(port: u16, ping: String, probe: bool, send: impl Fn(Req) -> bool + Send + 'static) -> Result<(), String> {
    let l = TcpListener::bind(SocketAddr::from((Ipv4Addr::LOCALHOST, port))).map_err(|e| format!("127.0.0.1:{port}: {e}"))?;
    std::thread::spawn(move || {
        // one at a time: these are a few a build, and each is answered in a moment
        for s in l.incoming().flatten() {
            serve(s, &ping, probe, &send);
        }
    });
    Ok(())
}

/// A GET through the door of a program that is running: its answer, or None if nothing of ours answers.
pub fn ask(port: u16, path: &str, timeout: Duration) -> Option<String> {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let mut s = TcpStream::connect_timeout(&addr, Duration::from_millis(300)).ok()?;
    s.set_read_timeout(Some(timeout)).ok()?;
    s.write_all(format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n").as_bytes()).ok()?;
    let mut all = String::new();
    s.read_to_string(&mut all).ok()?;
    let (head, body) = all.split_once("\r\n\r\n")?;
    head.starts_with("HTTP/1.0 200").then(|| body.to_string())
}
