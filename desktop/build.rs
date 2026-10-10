//! Puts the program's icon and its name into the .exe (the Windows SDK's rc.exe does it), so that the file,
//! its window and its taskbar button all show them; and says when this copy was built, for /ping.
fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=icon.ico");
    // (the build's time is part of the version: said anew whenever the program or its page has changed)
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=../web/viewer/index.html");
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    println!("cargo:rustc-env=CADKIT_BUILT={now}");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut res = winresource::WindowsResource::new();
        // (resource 1: main.rs gives the window the same one)
        res.set_icon_with_id("icon.ico", "1");
        res.set("ProductName", "CADkit Viewer");
        res.set("FileDescription", "CADkit Viewer");
        if let Err(e) = res.compile() {
            // no rc.exe on this machine: the program is built all the same, without its icon
            println!("cargo:warning=no icon in the program: {e}");
        }
    }
}
