//! The tabbed app's half of the program: its tabs, what it remembers of them, and what it does when it is
//! told something through the tab strip, the keyboard or the control door. (What a tab's page says about
//! the picture goes the way it always did: App::on_ipc.)
use super::*;

pub const APP_TITLE: &str = "CADkit Viewer";

fn add_tab(s: &mut Shell, dir: PathBuf) -> usize {
    s.next_id += 1;
    let title = s.title(&dir);
    s.tabs.push(Tab { id: s.next_id, dir, title, webview: None, shown: false, dot: false, seen: 0, held: Held::default(), used: Instant::now() });
    s.tabs.len() - 1
}

impl App {
    /// The window is up: the tabs of last time are brought back (their pages only when each is first
    /// shown), and the project this start was asked to open, if any, is opened in front.
    pub fn app_start(&mut self) {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_mut()) else { return };
        s.top = g.r.top;
        s.projects = tabs::load_projects(&s.data);
        let was = std::fs::read_to_string(s.data.join("session.json")).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok()).unwrap_or(Value::Null);
        let mut active = None;
        for t in was["tabs"].as_array().into_iter().flatten() {
            // (a project whose model is gone does not come back as a tab: it stays in the list, greyed)
            let Some(Ok(dir)) = t["dir"].as_str().map(tabs::model_dir) else { continue };
            if s.tabs.iter().any(|x| tabs::same(&x.dir, &dir)) {
                continue;
            }
            if was["active"].as_str() == t["dir"].as_str() {
                active = Some(s.tabs.len());
            }
            let i = add_tab(s, dir);
            // built again while the program was not running: it says so, as if it had been
            let seen = t["seen"].as_str().and_then(|x| x.parse().ok()).unwrap_or(0);
            s.tabs[i].seen = seen;
            s.tabs[i].dot = seen != tabs::stamp(&s.tabs[i].dir);
        }
        let first = active.or(if s.tabs.is_empty() { None } else { Some(0) });
        match self.args.open.clone() {
            Some(d) => {
                let r = self.open_project(&d, true);
                if let (Some(e), Some(s)) = (r["error"].as_str(), self.shell.as_mut()) {
                    s.note = e.to_string();
                }
                if self.shell.as_ref().is_some_and(|s| s.active.is_none()) {
                    if let Some(i) = first {
                        self.activate(i);
                    }
                }
            }
            None => {
                if let Some(i) = first {
                    self.activate(i);
                }
            }
        }
        self.strip_push();
    }

    /// The strip is told what there is to show (only when that is not what it was last told).
    pub fn strip_push(&mut self) {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_mut()) else { return };
        if !s.ready {
            return;
        }
        let projects = if s.list {
            s.projects = tabs::load_projects(&s.data);
            let (list, open): (Vec<Value>, Vec<PathBuf>) = (s.projects.clone(), s.tabs.iter().map(|t| t.dir.clone()).collect());
            tabs::projects_for_page(&list, &open, &mut |d| s.title(d))
        } else {
            json!([])
        };
        let tabs: Vec<Value> = s.tabs.iter().enumerate().map(|(i, t)| json!({"id": t.id, "title": t.title, "dir": t.dir.to_string_lossy(), "dot": t.dot, "active": s.active == Some(i)})).collect();
        let js = format!("window.setState&&setState({})", json!({"tabs": tabs, "list": s.list, "projects": projects, "note": s.note}));
        if js != s.pushed {
            if let Some(strip) = &g.strip {
                let _ = strip.evaluate_script(&js);
            }
            s.pushed = js;
        }
    }

    fn set_title(&self) {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_ref()) else { return };
        match s.active {
            Some(i) => g.window.set_title(&format!("{APP_TITLE} - {}", s.tabs[i].title)),
            None => g.window.set_title(APP_TITLE),
        }
    }

    /// The keyboard goes to what is shown: the active tab's page, or the list.
    pub fn focus_ui(&self) {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_ref()) else { return };
        let _ = match page_of(g, &self.shell).filter(|_| !s.list) {
            Some(wv) => wv.focus(),
            None => g.strip.as_ref().map(|w| w.focus()).unwrap_or(Ok(())),
        };
    }

    /// The tabs that are open and the one shown, kept for the next start.
    pub fn save_session(&self) {
        let Some(s) = self.shell.as_ref() else { return };
        let tabs: Vec<Value> = s.tabs.iter().map(|t| json!({"dir": t.dir.to_string_lossy(), "seen": t.seen.to_string()})).collect();
        tabs::write(&s.data.join("session.json"), &json!({"tabs": tabs, "active": s.active.map(|i| s.tabs[i].dir.to_string_lossy().to_string())}));
    }

    /// The tab shown is left: what its page has said and its model go with it (the model stays on the
    /// card), and the renderer has nothing.
    fn park_active(&mut self) {
        let (Some(g), Some(s)) = (self.gfx.as_mut(), self.shell.as_mut()) else { return };
        let Some(i) = s.active.take() else { return };
        let t = &mut s.tabs[i];
        t.held = Held { view: std::mem::take(&mut self.view), names: std::mem::take(&mut self.names), part_names: std::mem::take(&mut self.part_names), glb_have: std::mem::take(&mut self.glb_have), look: Some(g.r.look), scene: g.r.park() };
        // (a model still being read for it is forgotten with this: it is asked for again when the tab is back)
        self.glb_want.clear();
        t.used = Instant::now();
        // no more models kept than KEEP_SCENES: the one left longest ago is let go
        loop {
            let kept: Vec<usize> = (0..s.tabs.len()).filter(|&k| s.tabs[k].held.scene.is_some()).collect();
            if kept.len() <= KEEP_SCENES {
                break;
            }
            let old = kept.into_iter().min_by_key(|&k| s.tabs[k].used).unwrap();
            let h = &mut s.tabs[old].held;
            (h.scene, h.glb_have) = (None, String::new());
            h.names.clear();
            h.part_names.clear();
        }
    }

    /// Show tab `i`.
    pub fn activate(&mut self, i: usize) {
        let Some(s) = self.shell.as_ref() else { return };
        if i >= s.tabs.len() {
            return;
        }
        if s.active == Some(i) {
            if s.list {
                self.show_list(false);
            }
            return;
        }
        let t0 = Instant::now();
        self.park_active();
        let page = self.args.page.clone();
        let (Some(g), Some(s)) = (self.gfx.as_mut(), self.shell.as_mut()) else { return };
        (s.active, s.list) = (Some(i), false);
        let (w, h, top) = (g.config.width, g.config.height, s.top);
        let t = &mut s.tabs[i];
        (t.used, t.dot, t.seen) = (Instant::now(), false, tabs::stamp(&t.dir));
        let held = std::mem::take(&mut t.held);
        (self.view, self.names, self.part_names) = (held.view, held.names, held.part_names);
        self.glb_want = held.glb_have.clone();
        self.glb_have = held.glb_have;
        g.r.look = held.look.unwrap_or_default();
        let (kept, unpark_ms) = match held.scene {
            Some(p) => (true, g.r.unpark(p)),
            None => (false, 0.0),
        };
        let mut said = None;
        match &t.webview {
            // its page is as it was left: it says everything again, and looks for a newer model now
            Some(wv) => {
                let _ = wv.evaluate_script("window.viewer&&viewer.native&&(viewer.native.all=true,viewer.native.check&&viewer.native.check())");
            }
            None => match tab_view(g, &self.proxy, t.id, &t.dir, page.as_deref(), rect(0, top, w, h.saturating_sub(top))) {
                Ok(wv) => (t.webview, t.shown) = (Some(wv), true),
                Err(e) => said = Some(format!("tab {}: no page: {e}", t.id)),
            },
        }
        s.switch = Some(Switch { to: t.id, t0, kept, unpark_ms, first_ms: None, rest_ms: None });
        layout(g, s);
        if let Some(e) = said {
            self.say(e);
        }
        // the model is read at once, beside the page's own reading of it (a kept one is there already)
        self.fetch_model(String::new());
        self.last_msg = Instant::now();
        self.touch(false);
        if let Some(g) = self.gfx.as_ref() {
            g.window.request_redraw();
        }
        self.focus_ui();
        self.set_title();
        self.strip_push();
        self.save_session();
    }

    pub fn close_tab(&mut self, i: usize) {
        let Some(s) = self.shell.as_ref() else { return };
        if i >= s.tabs.len() {
            return;
        }
        let was_active = s.active == Some(i);
        if was_active {
            self.park_active();
        }
        let Some(s) = self.shell.as_mut() else { return };
        drop(s.tabs.remove(i)); // its page, and its model on the card, go with it
        if let Some(a) = s.active.as_mut().filter(|a| **a > i) {
            *a -= 1;
        }
        let n = s.tabs.len();
        if was_active && n > 0 {
            self.activate(i.min(n - 1));
        } else if n == 0 {
            // nothing open: the list, and behind it the bare backdrop
            (s.list, s.switch) = (true, None);
            if let Some(g) = self.gfx.as_ref() {
                layout(g, self.shell.as_mut().unwrap());
                g.window.request_redraw();
            }
            self.touch(false);
            self.focus_ui();
        }
        self.set_title();
        self.strip_push();
        self.save_session();
    }

    /// The projects list, up or down (it stays up while no tab is open).
    pub fn show_list(&mut self, on: bool) {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_mut()) else { return };
        s.list = on || s.active.is_none();
        layout(g, s);
        if !s.list {
            // the picture was not drawn while the list covered it: it is now, and the page says where it stands
            if let Some(wv) = page_of(g, &self.shell) {
                let _ = wv.evaluate_script("window.viewer&&viewer.native&&(viewer.native.all=true)");
            }
            g.window.request_redraw();
            self.touch(false);
        }
        self.strip_push();
        self.focus_ui();
    }

    /// Ctrl+Tab, Ctrl+Shift+Tab, Ctrl+W, wherever they were pressed.
    pub fn app_key(&mut self, k: &str) {
        let Some(s) = self.shell.as_ref() else { return };
        let n = s.tabs.len() as i64;
        match (k, s.active) {
            ("close", Some(a)) => self.close_tab(a),
            ("next" | "prev", _) if n > 0 => {
                let a = s.active.map(|a| a as i64).unwrap_or(-1);
                self.activate((a + if k == "next" { 1 } else { -1 }).rem_euclid(n) as usize);
            }
            _ => {}
        }
    }

    /// A project's tab, opened or told there is a new model. `focus`: shown, and the window brought in
    /// front; without it nothing that is on screen changes but the tab's dot (a build must not take the
    /// window from whoever is working in it).
    pub fn open_project(&mut self, dir: &str, focus: bool) -> Value {
        let dir = match tabs::model_dir(dir) {
            Ok(d) => d,
            Err(e) => return json!({"ok": false, "error": e}),
        };
        let Some(s) = self.shell.as_mut() else { return json!({"ok": false, "error": "not the app"}) };
        let name = s.title(&dir);
        s.projects = tabs::load_projects(&s.data); // (as it is NOW: cadkit's web server writes it too)
        tabs::note_project(&mut s.projects, &dir, &name);
        tabs::write(&s.data.join("projects.json"), &Value::Array(s.projects.clone()));
        let (i, opened) = match s.tabs.iter().position(|t| tabs::same(&t.dir, &dir)) {
            Some(i) => (i, false),
            None => (add_tab(s, dir.clone()), true),
        };
        s.tabs[i].title = name;
        // (with nothing shown there is nothing to take the window from: the first tab is shown)
        let show = focus || s.active.is_none();
        if show {
            if s.active == Some(i) {
                if let Some(wv) = &s.tabs[i].webview {
                    let _ = wv.evaluate_script("window.viewer&&viewer.native&&viewer.native.check&&viewer.native.check()");
                }
            }
            self.activate(i);
            if focus {
                self.come_forward();
            }
        } else {
            let t = &mut s.tabs[i];
            let now = tabs::stamp(&t.dir);
            if s.active == Some(i) {
                t.seen = now;
            } else if now != t.seen {
                t.dot = true;
            }
            // its page, if it has one, looks for the new model now and not at its next look
            if let Some(wv) = &t.webview {
                let _ = wv.evaluate_script("window.viewer&&viewer.native&&viewer.native.check&&viewer.native.check()");
            }
        }
        self.set_title();
        self.strip_push();
        self.save_session();
        let s = self.shell.as_ref().unwrap();
        json!({"ok": true, "tab": s.tabs[i].id, "title": s.tabs[i].title, "opened": opened, "active": s.active == Some(i), "dot": s.tabs[i].dot})
    }

    pub fn come_forward(&self) {
        let Some(g) = self.gfx.as_ref() else { return };
        if g.window.is_minimized() == Some(true) {
            g.window.set_minimized(false);
        }
        g.window.focus_window();
    }

    /// Once a second: has a project been built again? A tab that is not the one shown gets its dot; the
    /// one shown has its page look now. (A file's time each: nothing of the card's, nothing of the pages'.)
    pub fn poll_projects(&mut self) {
        let Some(s) = self.shell.as_mut() else { return };
        s.poll_t = Instant::now();
        let mut changed = None;
        for i in 0..s.tabs.len() {
            let now = tabs::stamp(&s.tabs[i].dir);
            if now == s.tabs[i].seen || now == 0 {
                continue;
            }
            let title = { let d = s.tabs[i].dir.clone(); s.title(&d) };
            let t = &mut s.tabs[i];
            t.title = title;
            if s.active == Some(i) {
                t.seen = now;
                changed = Some(i);
                if let Some(wv) = &t.webview {
                    let _ = wv.evaluate_script("window.viewer&&viewer.native&&viewer.native.check&&viewer.native.check()");
                }
            } else {
                t.dot = true;
            }
        }
        if changed.is_some() {
            self.set_title();
            self.save_session();
        }
        self.strip_push();
    }

    pub fn on_strip(&mut self, body: &str) {
        let Ok(v) = serde_json::from_str::<Value>(body) else { return };
        let Some(s) = self.shell.as_mut() else { return };
        let at = |s: &Shell| s.tabs.iter().position(|t| Some(t.id) == v["id"].as_u64());
        match v["t"].as_str().unwrap_or("") {
            "ready" => {
                (s.ready, s.pushed) = (true, String::new());
                self.strip_push();
            }
            "tab" => {
                if let Some(i) = at(s) {
                    self.activate(i);
                }
            }
            "close" => {
                if let Some(i) = at(s) {
                    self.close_tab(i);
                }
            }
            "order" => {
                // the tabs, dragged into another order: the one shown stays the one shown
                let ids: Vec<u64> = v["ids"].as_array().map(|a| a.iter().filter_map(|x| x.as_u64()).collect()).unwrap_or_default();
                let shown = s.active.map(|i| s.tabs[i].id);
                s.tabs.sort_by_key(|t| ids.iter().position(|&i| i == t.id as u64).unwrap_or(usize::MAX));
                s.active = shown.and_then(|a| s.tabs.iter().position(|t| t.id == a));
                s.pushed = String::new();
                self.strip_push();
                self.save_session();
            }
            "plus" => {
                let on = !s.list;
                self.show_list(on);
            }
            "open" => {
                if let Some(d) = v["dir"].as_str() {
                    let r = self.open_project(d, true);
                    if let (Some(e), Some(s)) = (r["error"].as_str(), self.shell.as_mut()) {
                        s.note = e.to_string();
                        self.strip_push();
                    }
                }
            }
            "key" => self.app_key(v["k"].as_str().unwrap_or("")),
            _ => {}
        }
    }

    /// A message from a tab's page. ONLY THE TAB THAT IS SHOWN SPEAKS TO THE PICTURE; any tab may hand
    /// over one of the app's own keys.
    pub fn on_tab_ipc(&mut self, id: u64, body: &str) {
        let Some(s) = self.shell.as_ref() else { return };
        if body.contains("\"Akey\"") {
            if let Ok(v) = serde_json::from_str::<Value>(body) {
                if v["t"] == "Akey" {
                    return self.app_key(v["k"].as_str().unwrap_or(""));
                }
            }
        }
        if s.active.map(|i| s.tabs[i].id) == Some(id) && !s.list {
            self.on_ipc(body);
        }
    }

    /// A request through the control door (door.rs).
    pub fn on_door(&mut self, event_loop: &ActiveEventLoop, r: door::Req) {
        let ans = match r.path.as_str() {
            "/open" => {
                let focus = r.get("focus") == Some("1");
                match r.get("dir") {
                    Some(d) => self.open_project(d, focus),
                    None => {
                        if focus {
                            self.come_forward();
                        }
                        json!({"ok": true})
                    }
                }
            }
            "/quit" => {
                self.save_session();
                self.save_place();
                self.quit = true;
                event_loop.exit();
                json!({"ok": true})
            }
            _ => return self.probe(r),
        };
        let _ = r.answer.send(ans.to_string());
    }

    // ── for the checks (--probe): what the app is doing, a capture of it, input to it ───────────────────
    fn probe_state(&self) -> Value {
        let (Some(g), Some(s)) = (self.gfx.as_ref(), self.shell.as_ref()) else { return json!(null) };
        let tabs: Vec<Value> = s.tabs.iter().enumerate().map(|(i, t)| json!({"id": t.id, "dir": t.dir.to_string_lossy(), "title": t.title, "dot": t.dot, "active": s.active == Some(i), "page": t.webview.is_some(), "shown": t.shown, "on_card": t.held.scene.is_some(), "card_bytes": t.held.scene.as_ref().map(|p| p.bytes())})).collect();
        let (hid, posed, sel) = g.r.counts();
        json!({
            "tabs": tabs, "list": s.list, "title": g.window.title(), "client": [g.config.width, g.config.height], "top": s.top, "picture": [g.r.size().0, g.r.size().1],
            "renders": g.r.n_renders, "dispatches": g.r.n_dispatches, "presents": self.presents, "status_lines": self.stat_sent,
            "spp": g.r.n, "cap": gpu::MAX_SPP, "model": g.r.has_scene(), "loading": self.loading, "quiet": self.quiet(),
            "hidden": hid, "posed": posed, "sel": sel, "clip": g.r.look.clip, "eye": self.view.cam.map(|c| c.eye.to_array()),
            "foreground": cap::foreground() == g.hwnd, "minimized": g.window.is_minimized(), "last_switch": s.last_switch, "backend": g.backend,
        })
    }

    fn probe(&mut self, r: door::Req) {
        let Some(g) = self.gfx.as_ref() else { return };
        let (hwnd, num) = (g.hwnd, |k: &str| r.get(k).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0) as i32);
        match r.path.as_str() {
            "/test/state" => {
                let _ = r.answer.send(self.probe_state().to_string());
            }
            "/test/front" => {
                self.come_forward();
                let _ = r.answer.send("{\"ok\":true}".into());
            }
            // the window as the desktop shows it, once the picture has come to rest (see probe_tick)
            "/test/shot" => {
                let name = r.get("name").unwrap_or("shot").to_string();
                if let Some(s) = self.shell.as_mut() {
                    s.pshot = Some((name, r, Instant::now()));
                }
            }
            // mouse messages to the webview under a place in the window (not the user's pointer):
            // a click at x,y; or, with x1,y1, a drag there in n steps (right=1: the right button)
            "/test/click" | "/test/drag" => {
                let (x0, y0) = (num("x"), num("y"));
                let drag = r.path == "/test/drag";
                let (x1, y1, n, right) = (num("x1"), num("y1"), num("n").max(1), num("right") != 0);
                std::thread::spawn(move || {
                    let hit = cap::child_at(hwnd, "Chrome_RenderWidgetHostHWND", x0, y0);
                    if let Some((h, cx, cy)) = hit {
                        let (dn, up, mk) = if right { (0x204, 0x205, 2) } else { (0x201, 0x202, 1) };
                        cap::post_mouse(h, 0x200, 0, cx, cy);
                        std::thread::sleep(Duration::from_millis(40));
                        cap::post_mouse(h, dn, mk, cx, cy);
                        std::thread::sleep(Duration::from_millis(40));
                        if drag {
                            for i in 1..=n {
                                cap::post_mouse(h, 0x200, mk, cx + (x1 - x0) * i / n, cy + (y1 - y0) * i / n);
                                std::thread::sleep(Duration::from_millis(6));
                            }
                        }
                        let (ex, ey) = if drag { (cx + x1 - x0, cy + y1 - y0) } else { (cx, cy) };
                        cap::post_mouse(h, up, 0, ex, ey);
                        std::thread::sleep(Duration::from_millis(120));
                    }
                    let _ = r.answer.send(json!({"ok": hit.is_some()}).to_string());
                });
            }
            // keys typed through the desktop's own input queue, as a hand types them (k=ctrl+shift+tab):
            // only while this window is in front, for they go to whatever has the keyboard
            "/test/keys" => {
                let keys: Vec<u32> = r
                    .get("k")
                    .unwrap_or("")
                    .split('+')
                    .filter_map(|k| match k.trim().to_ascii_lowercase().as_str() {
                        "ctrl" => Some(0x11),
                        "shift" => Some(0x10),
                        "tab" => Some(0x09),
                        "esc" => Some(0x1B),
                        k if k.len() == 1 => Some(k.to_ascii_uppercase().as_bytes()[0] as u32),
                        _ => None,
                    })
                    .collect();
                std::thread::spawn(move || {
                    let ok = cap::foreground() == hwnd;
                    if ok {
                        for &k in &keys {
                            cap::type_key(k, true);
                            std::thread::sleep(Duration::from_millis(30));
                        }
                        for &k in keys.iter().rev() {
                            cap::type_key(k, false);
                            std::thread::sleep(Duration::from_millis(30));
                        }
                    }
                    let _ = r.answer.send(json!({"ok": ok, "typed": keys.len()}).to_string());
                });
            }
            // script run in a tab's page (tab=<id>), the shown one's (no tab), or the strip's (tab=strip)
            "/test/eval" => {
                let s = self.shell.as_ref().unwrap();
                let wv = match r.get("tab") {
                    Some("strip") => g.strip.as_ref(),
                    Some(id) => s.tabs.iter().find(|t| t.id.to_string() == id).and_then(|t| t.webview.as_ref()),
                    None => page_of(g, &self.shell),
                };
                let js = r.get("js").unwrap_or("null").to_string();
                match wv {
                    Some(wv) => {
                        let tx = r.answer.clone();
                        let _ = wv.evaluate_script_with_callback(&js, move |res| {
                            let _ = tx.send(if res.is_empty() { "null".into() } else { res });
                        });
                    }
                    None => {
                        let _ = r.answer.send("{\"error\":\"no such page\"}".into());
                    }
                }
            }
            _ => {
                let _ = r.answer.send("{\"error\":\"no such probe\"}".into());
            }
        }
    }

    pub fn probe_tick(&mut self) {
        let due = self.shell.as_ref().and_then(|s| s.pshot.as_ref()).is_some_and(|p| self.quiet() || p.2.elapsed() > Duration::from_secs(25));
        if !due {
            return;
        }
        let timed_out = !self.quiet();
        let (name, r, _) = self.shell.as_mut().unwrap().pshot.take().unwrap();
        let Some(g) = self.gfx.as_ref() else { return };
        let ans = match dda::capture(g.hwnd, None) {
            Ok((w, h, px)) => {
                let _ = std::fs::create_dir_all(&self.args.out);
                let f = self.args.out.join(format!("{name}.png"));
                save_png(&f, w, h, &px);
                json!({"file": f.to_string_lossy(), "size": [w, h], "spp": g.r.n, "timed_out": timed_out, "foreground": cap::foreground() == g.hwnd})
            }
            Err(e) => json!({"error": e}),
        };
        let _ = r.answer.send(ans.to_string());
    }
}
