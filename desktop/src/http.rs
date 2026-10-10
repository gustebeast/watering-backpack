//! The little HTTP this needs: one request to the local server that serves the page, the whole reply read.
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

/// `http://host[:port]/path` -> (host:port, /path)
fn split(url: &str) -> Result<(String, String), String> {
    let rest = url.strip_prefix("http://").ok_or_else(|| format!("only http:// is spoken here: {url}"))?;
    let (host, path) = match rest.find('/') {
        Some(i) => (&rest[..i], &rest[i..]),
        None => (rest, "/"),
    };
    let host = if host.contains(':') { host.to_string() } else { format!("{host}:80") };
    Ok((host, path.split('#').next().unwrap_or("/").to_string()))
}

/// Returns (status, body). `body`: a JSON document to POST; None for a GET.
pub fn request(url: &str, body: Option<&[u8]>, timeout_s: u64) -> Result<(u16, Vec<u8>), String> {
    let (host, path) = split(url)?;
    let e = |x: std::io::Error| format!("{url}: {x}");
    let mut s = TcpStream::connect(&host).map_err(e)?;
    s.set_read_timeout(Some(Duration::from_secs(timeout_s))).map_err(e)?;
    let mut head = format!("{} {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n", if body.is_some() { "POST" } else { "GET" });
    if let Some(b) = body {
        head += &format!("Content-Type: application/json\r\nContent-Length: {}\r\n", b.len());
    }
    head += "\r\n";
    s.write_all(head.as_bytes()).map_err(e)?;
    if let Some(b) = body {
        s.write_all(b).map_err(e)?;
    }
    let mut all = Vec::new();
    s.read_to_end(&mut all).map_err(e)?;
    let cut = all.windows(4).position(|w| w == b"\r\n\r\n").ok_or_else(|| format!("{url}: no reply"))?;
    let head = String::from_utf8_lossy(&all[..cut]).to_string();
    let status: u16 = head.split_whitespace().nth(1).and_then(|c| c.parse().ok()).ok_or_else(|| format!("{url}: bad reply"))?;
    if head.to_ascii_lowercase().contains("transfer-encoding: chunked") {
        return Err(format!("{url}: a chunked reply, which this does not read"));
    }
    Ok((status, all[cut + 4..].to_vec()))
}

pub fn get(url: &str) -> Result<Vec<u8>, String> {
    match request(url, None, 60)? {
        (200, b) => Ok(b),
        (c, _) => Err(format!("{url}: HTTP {c}")),
    }
}
