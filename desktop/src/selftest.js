// The selftest's half that runs IN THE PAGE (desk.exe --selftest puts it there before the page's own script).
// It works the real page through its own controls, and asks the shell for what a page cannot do: real mouse
// messages (Tmouse), a capture of the window once the picture is at rest (Tshot), a resize, frame times.
// Mouse positions and every pixel figure are in DEVICE pixels of the window's client area.
(() => {
  if (window.__t || window.top !== window) return;
  const post = o => window.ipc.postMessage(JSON.stringify(o));
  const waiting = new Map();
  let seq = 0;
  const call = (t, o = {}) => new Promise(res => { const id = ++seq; waiting.set(id, res); post({ t, id, ...o }); });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = s => post({ t: 'Tlog', s: String(s) });
  window.__t = { resume(id, r) { const f = waiting.get(id); waiting.delete(id); if (f) f(r); } };
  addEventListener('error', e => log('PAGE ERROR: ' + e.message + ' @' + e.lineno));
  addEventListener('unhandledrejection', e => log('PAGE REJECTION: ' + (e.reason && e.reason.stack || e.reason)));
  for (const k of ['error', 'warn']) {
    const o = console[k].bind(console);
    console[k] = (...a) => { log('console.' + k + ': ' + a.map(String).join(' ').slice(0, 300)); o(...a); };
  }

  const $ = id => document.getElementById(id);
  const J = o => JSON.stringify(o, (k, x) => typeof x === 'number' ? Math.round(x * 100) / 100 : x);
  const key = (k, type = 'keydown', o = {}) => dispatchEvent(new KeyboardEvent(type,
    { key: k, code: k === ' ' ? 'Space' : 'Key' + k.toUpperCase(), bubbles: true, cancelable: true, ...o }));
  const tap = async (k, o) => { key(k, 'keydown', o); await sleep(40); key(k, 'keyup', o); await sleep(40); };
  const WM = { move: 0x200, ldown: 0x201, lup: 0x202, rdown: 0x204, rup: 0x205, wheel: 0x20A };
  const click = (x, y) => call('Tmouse', { ops: [[WM.move, 0, x, y, 40], [WM.ldown, 1, x, y, 40], [WM.lup, 0, x, y, 120]] });
  function drag(x0, y0, x1, y1, n, right) {
    const [dn, up, mk] = right ? [WM.rdown, WM.rup, 2] : [WM.ldown, WM.lup, 1];
    const ops = [[WM.move, 0, x0, y0, 40], [dn, mk, x0, y0, 20]];
    for (let i = 1; i <= n; i++) ops.push([WM.move, mk, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, 4]);
    ops.push([up, 0, x1, y1, 120]);
    return call('Tmouse', { ops });
  }
  const wheel = (x, y, notches) => call('Tmouse', { ops: Array.from({ length: Math.abs(notches) },
    () => [WM.wheel, ((notches > 0 ? 120 : -120) & 0xffff) * 65536, x, y, 60]) });

  let v, M, THREE;
  const dpr = () => devicePixelRatio;
  const px = p => { const a = v.toPx(p); return [a[0] * dpr(), a[1] * dpr(), a[2]]; };      // a CAD point, in device px
  const hiddenN = () => M.list.filter(p => p.hidden).length;
  const selUnits = () => [...new Set(v.selection.map(p => p.unit))];
  // the page's own pick through the centre of a grid of pixels: [x, y, distance or -1, seen-through, part]
  function probe(nx = 20, ny = 12) {
    const out = [], d = dpr(), W = innerWidth * d, H = innerHeight * d;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const x = Math.floor((0.06 + 0.88 * i / (nx - 1)) * W), y = Math.floor((0.08 + 0.84 * j / (ny - 1)) * H);
      const h = v.pickAt((x + 0.5) / d, (y + 0.5) / d);
      out.push([x, y, h ? h.world.distanceTo(v.camera.position) : -1, h && h.part.mat.transparent ? 1 : 0, h ? h.part.name : '']);
    }
    return out;
  }
  const rest = () => call('Tshot', { name: '' });                 // wait for the picture to come to rest
  async function shot(name, extra = {}) {
    await sleep(120);                                             // the page's next frame sends what changed
    await rest();
    const r = await call('Tshot', { name, probe: probe(), ...extra });
    const p = r.probe;
    log(`[${name}] native ${r.native.join('x')} at ${r.spp} spp${r.timed_out ? ' (NOT AT REST: timed out)' : ''}, ` +
        `${Math.round(r.converge_ms)} ms from last change to rest; capture ${r.dda.join('x')}${r.dda_err ? ' FAILED ' + r.dda_err : ''}`);
    log(`    page: ${hiddenN()} hidden, selected ${J(selUnits().slice(0, 4))}, status line "${$('fps').textContent}"`);
    log(`    native: ${J(r.counts)}`);
    log(`    page picks vs native first hits at ${p.n} pixels: ${p.agree} agree, ${p.page_only} page-only, ${p.native_only} native-only, ` +
        `${p.far} at another depth, ${p.skipped} skipped (clear part under the cursor)` + (p.other_part ? `, ${p.other_part} same depth but another part` : '') +
        (p.worst.length ? `; e.g. ${J(p.worst)}` : ''));
    if (r.diff) log(`    against ${extra.diff}: mean |difference| ${r.diff.mean.toFixed(2)}/255, ${(100 * r.diff.changed_share).toFixed(2)}% of pixels changed`);
    return r;
  }
  // the hit of the page's own pick nearest a place in the window, off the page's panels, and not on a sliver:
  // the same part is under the cursor a few pixels to every side (a real click lands on whole device pixels)
  function hitNear(fx, fy, not) {
    const d = dpr(), W = innerWidth * d, H = innerHeight * d, c = [];
    for (const h of probe(40, 24)) {
      if (h[2] < 0 || h[3] || (not && not.includes(M.byName.get(h[4]).unit))) continue;
      if (document.elementFromPoint(h[0] / d, h[1] / d) !== v.renderer.domElement) continue;
      c.push({ e: Math.hypot(h[0] - fx * W, h[1] - fy * H), x: h[0] + 0.5, y: h[1] + 0.5, name: h[4], unit: M.byName.get(h[4]).unit });
    }
    c.sort((a, b) => a.e - b.e);
    return c.find(h => [[-4, 0], [4, 0], [0, -4], [0, 4]].every(([dx, dy]) => { const q = v.pickAt((h.x + dx) / d, (h.y + dy) / d); return q && q.part.name === h.name; })) || c[0];
  }
  const partVerts = function* (p) {
    const a = p.mesh ? p.mesh.geometry.attributes.position.array : p.pos, m = p.mesh ? p.mesh.matrix : null, q = new THREE.Vector3();
    for (let i = 0; i < a.length; i += 3) { q.set(a[i], a[i + 1], a[i + 2]); if (m) q.applyMatrix4(m); yield q; }
  };
  let uiOff = null;
  function ui(on) {
    if (on && uiOff) { uiOff.remove(); uiOff = null; }
    if (!on && !uiOff) { uiOff = document.createElement('style'); uiOff.textContent = 'body > div:not(#view) { visibility: hidden !important; }'; document.head.appendChild(uiOff); }
  }

  // OVERLAY AGAINST PICTURE. One unit alone against the backdrop, zoomed to, the page's panels out of the way.
  // (a) the box round its pixels in the NATIVE picture against the box of its vertices as THE PAGE projects them;
  // (b) the same box in the composited window (the desktop's own frame);
  // (c) two of the page's measure marks, put on its leftmost and rightmost vertices, found in the composited
  //     window against where the page projects those vertices.
  async function align(tag, names, note) {
    v.showAll(); v.select(names); v.selAction('isolate'); v.selAction('zoom'); v.select([]);
    ui(false);
    await sleep(200); await rest();
    const shown = M.list.filter(p => !p.hidden);
    const box = [Infinity, Infinity, -Infinity, -Infinity];
    let L = null, R = null;
    for (const p of shown) for (const q of partVerts(p)) {
      const [x, y] = px(q);
      if (x < box[0]) { box[0] = x; L = q.clone(); }
      if (x > box[2]) { box[2] = x; R = q.clone(); }
      box[1] = Math.min(box[1], y); box[3] = Math.max(box[3], y);
    }
    const r = await shot(tag);
    const err = b => b ? b.map((x, i) => x - box[i]) : null;
    log(`    ALIGN ${note}: ${shown.length} part(s) shown (${names[0]}), page-projected box of the vertices ${J(box)} device px`);
    log(`      (a) native picture's box ${J(r.bbox_native)}: edges off by ${J(err(r.bbox_native))} px (left, top, right, bottom)`);
    log(`      (b) composited window's box ${J(r.bbox_dda)}: edges off by ${J(err(r.bbox_dda))} px`);
    v.setMode('measure');
    const A = { kind: 'point', p: L, part: shown[0], pick: L }, B = { kind: 'point', p: R, part: shown[0], pick: R };
    v.measureClick(A); v.measureClick(B);
    await sleep(150);
    const pa = px(L), pb = px(R), mid = [(pa[0] * 3 + pb[0]) / 4, (pa[1] * 3 + pb[1]) / 4];
    const r2 = await shot(tag + '_marks', { find: [{ rgb: [111, 211, 255], at: pa, r: 26 }, { rgb: [255, 143, 208], at: pb, r: 26 }, { rgb: [255, 224, 138], at: mid, r: 5 }] });
    const f = r2.found, off = (g, p) => g ? [g[0] - p[0], g[1] - p[1]] : null;
    log(`      (c) mark A projected at ${J(pa.slice(0, 2))}, found in the window at ${J(f[0])} -> off by ${J(off(f[0], pa))} px; ` +
        `mark B at ${J(pb.slice(0, 2))}, found at ${J(f[1])} -> off by ${J(off(f[1], pb))} px; dimension line a quarter along: ${f[2] ? f[2][2] + ' yellow px' : 'NOT FOUND'}; label "${$('dimlabel').textContent}"`);
    v.setMode('select');
    ui(true);
    return { box, r };
  }

  async function quality(tag, eye, target, prefixes, blender = true) {
    v.showAll();
    v.setHidden(M.list.filter(p => prefixes.some(x => p.name.startsWith(x))), true);
    v.camera.position.set(eye[0], eye[2], -eye[1]);               // CAD (Z up) -> the page (Y up)
    v.controls.target.set(target[0], target[2], -target[1]);
    v.controls.update(); v.camera.updateMatrixWorld();
    await sleep(200); await rest();
    v.camera.updateMatrixWorld();
    const poses = {};
    for (const p of M.list) if (p.mesh) poses[p.name] = new THREE.Matrix4().multiplyMatrices(M.parts.matrixWorld, p.mesh.matrix).toArray();
    const req = { w: 1920, h: 1200, samples: 256, cam: v.camera.matrixWorld.toArray(), fov: v.camera.fov, near: v.camera.near, far: v.camera.far,
                  hidden: M.list.filter(p => p.hidden).map(p => p.name), poses, ...v.native.env };
    log(`[quality ${tag}] eye ${eye} target ${target} (CAD), ${req.hidden.length} hidden, ${Object.keys(poses).length} posed: ` + await call('Tquality', { name: tag, req, blender }));
  }

  // ── the parts of the selftest (desk.exe --selftest=keys,rows runs those alone) ───────────────────────────
  const only = (window.__tOnly || '').split(',').filter(Boolean);
  const want = name => !only.length || only.includes(name);
  const VK = { x: 0x58, u: 0x55, i: 0x49, z: 0x5A, y: 0x59, c: 0x43, m: 0x4D, p: 0x50, l: 0x4C, 1: 0x31, space: 0x20, esc: 0x1B, ctrl: 0x11, shift: 0x10,
               left: 0x25, up: 0x26, right: 0x27, down: 0x28 };
  // a real key, down and up: where 0 = to the window that has the keyboard in the webview, 1 = to the shell's
  // own window, 2 = typed through the desktop's input queue
  const realKey = (where, k, hold = 60) => call('Tkey', { ops: [[where, VK[k], 1, hold], [where, VK[k], 0, 80]] });
  const win = () => call('Twin');
  const keysSeen = [];
  let W, H, cx, cy, d, rig;

  async function base() {
    let r = await shot('01_default');

    // ── orbit, zoom, pan: real mouse messages through the page's own OrbitControls
    const c0 = v.camera.position.clone(), t0 = v.controls.target.clone();
    await call('Tmeas', { on: true });
    await drag(cx, cy + 40, cx - 240, cy - 30, 150);
    await sleep(700);
    log('orbit: left-drag of 150 mouse moves 4 ms apart, and the glide after it:\n' + await call('Tmeas', { on: false }));
    const c1 = v.camera.position.clone();
    await wheel(cx, cy, 3); await sleep(300);
    const c2 = v.camera.position.clone();
    await drag(cx, cy, cx + 60, cy + 40, 30, true); await sleep(300);
    log(`orbit moved the eye ${c0.distanceTo(c1).toFixed(1)} mm, wheel ${c1.distanceTo(c2).toFixed(1)} mm, right-drag moved the target ${t0.distanceTo(v.controls.target).toFixed(1)} mm`);
    r = await shot('02_orbit', { diff: '01_default' });

    // ── select: a real click on a part
    let h = hitNear(0.5, 0.5);
    let before = await call('Tshot', { name: '', sample: [[h.x, h.y]] });
    const seen = [];
    const note = e => seen.push(`${e.type}@${Math.round(e.clientX * d)},${Math.round(e.clientY * d)} b${e.button}/${e.buttons} ${e.isTrusted ? 'real' : 'synthetic'} on ${e.target.tagName}`);
    for (const t of ['pointerdown', 'pointerup', 'pointercancel', 'contextmenu', 'click']) addEventListener(t, note, { capture: true });
    await click(h.x, h.y); await sleep(200);
    for (const t of ['pointerdown', 'pointerup', 'pointercancel', 'contextmenu', 'click']) removeEventListener(t, note, { capture: true });
    log(`    events the page saw for that click: ${seen.join('; ')}`);
    log(`select: clicked ${J([h.x, h.y])} on ${h.name}; the page's selection is now ${J(selUnits())} (${v.selection.length} piece(s)); selected panel "${$('sel').innerText.replace(/\s+/g, ' ').slice(0, 80)}"`);
    r = await shot('03_select', { sample: [[h.x, h.y]], diff: '02_orbit' });
    log(`    the clicked pixel: native ${J(before.sample[0].native)} -> ${J(r.sample[0].native)}, in the window ${J(before.sample[0].dda)} -> ${J(r.sample[0].dda)}`);
    const firstUnit = h.unit;

    // ── hide it: the page's own key
    await tap('x');
    log(`hide (x): ${hiddenN()} hidden on the page; "${$('bShowAll').textContent}"`);
    r = await shot('04_hide', { sample: [[h.x, h.y]], diff: '02_orbit' });
    log(`    the clicked pixel is now native ${J(r.sample[0].native)}`);

    // ── isolate another
    h = hitNear(0.5, 0.5, [firstUnit]);
    await click(h.x, h.y); await sleep(200);
    const picked = selUnits();
    await tap('i');
    log(`isolate (i): clicked ${h.name}, selection ${J(picked)}; ${hiddenN()} of ${M.list.length} hidden`);
    r = await shot('05_isolate');

    // ── undo / redo
    key('z', 'keydown', { ctrlKey: true }); await sleep(100); const u1 = hiddenN();
    key('y', 'keydown', { ctrlKey: true }); await sleep(100); const u2 = hiddenN();
    key('z', 'keydown', { ctrlKey: true }); await sleep(100);
    log(`undo / redo / undo (ctrl+z, ctrl+y, ctrl+z): hidden ${u1} -> ${u2} -> ${hiddenN()}`);
    r = await shot('06_undo', { diff: '04_hide' });

    // ── show all
    key('Escape'); await tap('u');
    log(`show all (u), selection cleared (esc): ${hiddenN()} hidden`);
    r = await shot('07_showall', { diff: '02_orbit' });

    // ── the rig: a pedal held by its key, a knee lever latched by its button
    const node = rig.pedals[0].swing_nodes[0];
    key('1', 'keydown');
    document.querySelector('.pedal[data-name="LKL"]').click();
    await sleep(300);
    r = await shot('08_rig', { diff: '07_showall' });
    log(`rig: key 1 held, LKL latched; ${node} matrix ${J(M.byName.get(node).mesh.matrix.elements.slice(0, 12))}; buttons lit: ${[...document.querySelectorAll('.pedal.on')].map(e => e.dataset.name)}`);
    const keepP = v.camera.position.clone(), keepT = v.controls.target.clone();
    await align('09_align_rig', [node], 'a part the rig has swung (pedal 1 down)');
    key('1', 'keyup');
    document.querySelector('.pedal[data-name="LKL"]').click();
    v.showAll();
    v.camera.position.copy(keepP); v.controls.target.copy(keepT); v.controls.update();

    // ── space: the deck off
    await tap(' ');
    log(`deck (space): ${hiddenN()} hidden; "${$('deckstate').textContent}"`);
    r = await shot('10_deck');
    await tap(' ');

    // ── section cut
    await tap('c');
    log(`section (c): ${J({ on: v.sec.on, axis: v.sec.axis, v: v.sec.v, flip: v.sec.flip })}`);
    r = await shot('11_section');
    document.querySelector('#secPanel .ax[data-a="1"]').click();
    $('bFlip').click();
    const sl = $('secSlide'); sl.value = String(v.sec.v + 30); sl.dispatchEvent(new Event('input'));
    log(`section: Y, flipped, slider moved: ${J({ on: v.sec.on, axis: v.sec.axis, v: v.sec.v, flip: v.sec.flip })}`);
    r = await shot('12_section_y');
    await tap('c');

    // ── measure: two real clicks
    await tap('m');
    for (let i = 0; i < 100 && !M.geo; i++) await sleep(100);
    const a = hitNear(0.35, 0.5), bb = hitNear(0.65, 0.55);
    await click(a.x, a.y); await sleep(250);
    await click(bb.x, bb.y); await sleep(250);
    const eye = v.camera.position, world = p => M.parts.localToWorld(p.clone());
    const mA = v.meas.A, mB = v.meas.B;
    if (mA && mB) {
      const pa = px(mA.pick), pb = px(mB.pick);
      r = await shot('13_measure', { depth: [pa, pb] });
      const near = (ds, want) => ds.length ? Math.min(...ds.map(x => Math.abs(x - want))) : NaN;
      log(`measure: A ${mA.kind} on ${mA.part.name} at ${J(pa.slice(0, 2))}, B ${mB.kind} on ${mB.part.name} at ${J(pb.slice(0, 2))}; label "${$('dimlabel').textContent}" shown ${$('dimlabel').style.display}; ` +
          `readout "${$('readout').innerText.replace(/\s+/g, ' ').slice(0, 120)}"`);
      log(`    do the picked points lie on the native picture's surface? eye to A ${eye.distanceTo(world(mA.pick)).toFixed(2)} mm, native first hit there within ${near(r.depth[0], eye.distanceTo(world(mA.pick))).toFixed(3)} mm; ` +
          `B ${eye.distanceTo(world(mB.pick)).toFixed(2)} mm, within ${near(r.depth[1], eye.distanceTo(world(mB.pick))).toFixed(3)} mm`);
    } else log(`measure: FAILED, the clicks picked A=${mA && mA.kind} B=${mB && mB.kind}`);
    await tap('m');

    // ── axis views
    document.querySelector('#views .vw[data-d="0,0,1"]').click(); await sleep(100);
    r = await shot('14_view_top');
    document.querySelector('#views .vw[data-d="0.55,-1,0.5"]').click(); await sleep(100);
    r = await shot('15_view_iso');

    // ── the parts list: its eye hides a family
    await tap('p');
    const fam = [...$('plist').children].find(e => e._parts.length > 3 && e._parts.length < 40);
    fam.querySelector('.eye').click();
    log(`parts list (p): ${$('plist').children.length} families listed; the eye of "${fam.dataset.f}" clicked: ${hiddenN()} hidden`);
    r = await shot('16_parts_list');
    await tap('u'); await tap('p');

    // ── the lighting level: none in the shell (the key does nothing, the button is gone, the hint does not offer it)
    const q0 = v.quality; await tap('l');
    log(`lighting (l): level ${q0} -> ${v.quality}; button display "${$('bLight').style.display}"; hint: "${$('hint').textContent.slice(-60)}"`);

    // ── overlay against picture
    const part = M.list.find(p => { if (p.mesh || p.col || p.mat.transparent || p.iCount < 3000) return false;
      const bx = new THREE.Box3(); for (const q of partVerts(p)) bx.expandByPoint(q);
      const s = bx.getSize(new THREE.Vector3()).length(); return s > 60 && s < 300; });
    await align('17_align', [part.name], 'a part that stays put');

    // ── resize the window
    const got = await call('Tresize', { w: 1000, h: 640 });
    await sleep(300);
    log(`resize: client ${got.join('x')}, page ${innerWidth}x${innerHeight} css px @ ${dpr()} = ${innerWidth * dpr()}x${innerHeight * dpr()} device px`);
    v.showAll();
    r = await shot('18_resized');
    log('    ' + overlap());
    await align('19_align_resized', [part.name], 'the same part after the resize');
    v.showAll();

    // the model again: as when the page has reloaded one (here the same file under another address)
    v.native.glb += '&again=1'; v.native.all = true;
    await sleep(1500);
    log(`model asked for again as ${v.native.glb}`);
    r = await shot('20_model_again');
    await call('Tresize', { w: 1280, h: 800 }); await sleep(400);
    $('views').querySelector('.vw[data-d="0.55,-1,0.5"]').click(); await sleep(200);
  }

  // does the status line (top right) run into the title's lines (top left)?
  function overlap() {
    const f = $('fps').getBoundingClientRect(), rg = document.createRange();
    rg.selectNodeContents(document.querySelector('.label'));
    const hit = [...rg.getClientRects()].filter(r => r.width > 0 && r.right > f.left && r.left < f.right && r.bottom > f.top && r.top < f.bottom);
    return `status line "${$('fps').textContent}" box ${J([f.left, f.top, f.right, f.bottom])} css px at window ${innerWidth}x${innerHeight}: ` +
           (f.width === 0 ? 'not shown (no room)' : hit.length ? `OVERLAPS ${hit.length} line box(es) of the title, e.g. ${J([hit[0].left, hit[0].top, hit[0].right, hit[0].bottom])}` : 'clear of every line of the title');
  }

  // ── REAL KEYS: key messages as the desktop delivers them, not KeyboardEvents made in the page
  async function keys() {
    const note = e => keysSeen.push(`${e.type} ${JSON.stringify(e.key)}${e.ctrlKey ? '+ctrl' : ''} ${e.isTrusted ? 'real' : 'made-up'}`);
    addEventListener('keydown', note, true); addEventListener('keyup', note, true);
    const seen = () => { const s = keysSeen.join(', '); keysSeen.length = 0; return s || 'NONE'; };
    let w = await win();
    log(`keys: at this point the keyboard is with "${w.focus_class}"${w.focus_is_shell ? ' (the shell\'s own window)' : ''}; this window in front: ${w.foreground}`);

    // (a) the page has the keyboard
    await call('Tfocus', { who: 'page' }); await sleep(200);
    w = await win();
    const part = M.list.find(p => !p.mesh && !p.col && p.iCount > 3000).name;
    v.select([part]); await sleep(100);
    let r = await realKey(0, 'x'); await sleep(200);
    log(`  (a) the page has the keyboard ("${w.focus_class}"): WM_KEYDOWN/UP "x" posted to "${r.to}" -> page saw [${seen()}]; ${hiddenN()} hidden (a part was selected: want >= 1)`);
    r = await realKey(0, 'u'); await sleep(200);
    log(`      "u" -> [${seen()}]; ${hiddenN()} hidden (want 0)`);
    await call('Tkey', { ops: [[0, VK[1], 1, 400]] });
    const lit = [...document.querySelectorAll('.pedal.on')].map(e => e.dataset.name);
    await call('Tkey', { ops: [[0, VK[1], 0, 300]] });
    log(`      "1" held -> [${seen()}]; pedals lit while down ${J(lit)}, after up ${J([...document.querySelectorAll('.pedal.on')].map(e => e.dataset.name))}`);
    await realKey(0, 'space'); await sleep(200); const h1 = hiddenN();
    await realKey(0, 'space'); await sleep(200);
    log(`      space twice -> [${seen()}]; hidden ${h1} then ${hiddenN()} (deck off, on)`);
    await realKey(0, 'c'); await sleep(150); const s1 = v.sec.on; await realKey(0, 'c'); await sleep(150);
    log(`      "c" twice -> [${seen()}]; section ${s1} then ${v.sec.on}`);
    await realKey(0, 'p'); await sleep(150); const p1 = $('partsPanel').style.display; await realKey(0, 'p'); await sleep(150);
    log(`      "p" twice -> [${seen()}]; parts panel "${p1}" then "${$('partsPanel').style.display}"`);
    await realKey(0, 'm'); await sleep(150); const m1 = $('bMeasure').classList.contains('on'); await realKey(0, 'm'); await sleep(150);
    log(`      "m" twice -> [${seen()}]; measure ${m1} then ${$('bMeasure').classList.contains('on')}`);
    await realKey(0, 'l'); await sleep(150);
    log(`      "l" -> [${seen()}]; lighting level ${v.quality} (stays 0 in the shell)`);
    v.select([part]); await sleep(50); await realKey(0, 'i'); await sleep(200); const i1 = hiddenN();
    await realKey(0, 'esc'); await sleep(100);
    log(`      "i" then esc -> [${seen()}]; ${i1} hidden, selection ${v.selection.length}`);
    // ctrl+z needs the desktop's own idea of which keys are down: typed (SendInput), and only if this window is in front
    r = await call('Tkey', { ops: [[2, VK.ctrl, 1, 40], [2, VK.z, 1, 60], [2, VK.z, 0, 40], [2, VK.ctrl, 0, 120]] });
    await sleep(200);
    log(`      ctrl+z typed (${r.sent} of 4 key events sent, ${r.skipped} withheld: window not in front) -> [${seen()}]; ${hiddenN()} hidden (want 0: the isolate undone)`);
    if (hiddenN()) v.showAll();

    // (b) the shell's own window has the keyboard (as at start-up, or after alt-tab back to the title bar)
    v.select([part]); await sleep(100);
    await call('Tfocus', { who: 'shell' }); await sleep(250);
    w = await win();
    r = await realKey(1, 'x'); await sleep(250);
    const w2 = await win();
    log(`  (b) the keyboard given to the shell's own window: 0.25 s later it is with "${w.focus_class}" (the shell: ${w.focus_is_shell}; it hands the keyboard to the page whenever it gets it). ` +
        `A key that does reach the shell's window ("x" posted to "${r.to}") is passed on -> page saw [${seen()}]; ${hiddenN()} hidden (want >= 1); the keyboard is then with "${w2.focus_class}" (the shell: ${w2.focus_is_shell})`);
    r = await realKey(0, 'u'); await sleep(200);
    log(`      next key "u", to where the keyboard now is ("${r.to}") -> [${seen()}]; ${hiddenN()} hidden (want 0)`);
    // an input box takes its own keys
    await realKey(0, 'p'); await sleep(150); $('pfilter').focus(); await sleep(100);
    await realKey(0, 'x'); await sleep(150);
    log(`      with the parts filter box focused, "x" -> [${seen()}]; box holds "${$('pfilter').value}", ${hiddenN()} hidden (want "x", 0)`);
    $('pfilter').value = ''; $('pfilter').dispatchEvent(new Event('input')); $('pfilter').blur();
    await realKey(0, 'p'); await sleep(150);
    removeEventListener('keydown', note, true); removeEventListener('keyup', note, true);
    v.showAll(); v.select([]);
  }

  // ── the rows of the controls table not yet tried
  async function rows() {
    let r;
    // section: Z axis, and the number box
    await tap('c');
    document.querySelector('#secPanel .ax[data-a="2"]').click(); await sleep(100);
    const box = $('secVal'); box.value = '-40.5'; box.dispatchEvent(new Event('change')); await sleep(100);
    r = await shot('21_section_z');
    log(`section: Z, number box set to -40.5: page ${J({ axis: v.sec.axis, v: v.sec.v, flip: v.sec.flip })}, slider at ${$('secSlide').value}; native clip ${J(r.counts.clip)} (want [0,0,-1,-40.5])`);
    await tap('c');

    // shift-click adds to the selection (real clicks; shift held through the desktop's input queue, as a hand holds it)
    const a = hitNear(0.42, 0.45), b = hitNear(0.6, 0.5, [a.unit]);
    await click(a.x, a.y); await sleep(200);
    const s1 = selUnits();
    let seenShift = null;
    const note = e => { seenShift = e.shiftKey; };
    addEventListener('pointerdown', note, true);
    const kd = await call('Tkey', { ops: [[2, VK.shift, 1, 80]] });
    await call('Tmouse', { ops: [[WM.move, 4, b.x, b.y, 40], [WM.ldown, 5, b.x, b.y, 40], [WM.lup, 4, b.x, b.y, 120]] });
    await call('Tkey', { ops: [[2, VK.shift, 0, 80]] });
    removeEventListener('pointerdown', note, true);
    await sleep(200);
    r = await shot('22_shift_click');
    log(`shift-click: clicked ${a.name}, then ${b.name} with shift ${kd.sent ? 'held (typed)' : 'NOT typed (window not in front): MK_SHIFT in the mouse message only'}; the page saw shiftKey=${seenShift}; ` +
        `selection ${J(s1)} -> ${J(selUnits())} (${selUnits().length} units, want 2); native ${r.counts.sel} parts selected, page ${v.selection.length}`);
    await click(b.x, b.y); await sleep(150);                    // a plain click: that one alone
    log(`    a plain click on ${b.name}: selection ${J(selUnits())}`);

    // "select all N alike"
    const famPart = M.list.find(p => !p.mesh && !p.hidden && M.list.filter(q => q.family === p.family).length > 3 && M.list.filter(q => q.family === p.family).length < 30);
    v.select([famPart.name]); await sleep(100);
    const btn = [...$('sel').querySelectorAll('.btn')].find(e => e.dataset.a === 'fam');
    const label = btn ? btn.textContent : 'NO BUTTON';
    if (btn) btn.click();
    await sleep(150);
    r = await shot('23_all_alike');
    log(`select all alike: one ${famPart.family} selected, button "${label}" clicked: ${v.selection.length} parts selected on the page, ${r.counts.sel} in the native picture (family of ${M.list.filter(q => q.family === famPart.family).length})`);
    key('Escape');

    // parts list: the filter box, and a double-click on a row
    await tap('p');
    const pf = $('pfilter'); pf.value = 'belt'; pf.dispatchEvent(new Event('input')); await sleep(100);
    const shown = [...$('plist').children].filter(e => e.style.display !== 'none');
    const c0 = v.camera.position.clone();
    const row = shown[0];
    // (with nothing selected, the first click of a double-click opens the "selected" panel above the list and
    // the row moves from under the pointer, in a browser as here: so the family is selected first, as that click leaves it)
    v.select(row._parts.map(p => p.name)); await sleep(150);
    const rb = row.getBoundingClientRect(), rx = Math.round((rb.left + rb.width / 2) * d), ry = Math.round((rb.top + rb.height / 2) * d);
    const evs = [];
    const noteE = e => evs.push(e.type + (e.detail > 1 ? 'x' + e.detail : '') + ' on ' + (e.target.className || e.target.tagName) + (e.target.closest && e.target.closest('.fam') === row ? ' (the row)' : ''));
    for (const t of ['click', 'dblclick']) addEventListener(t, noteE, true);
    // (two posted clicks are two clicks to the browser, never a double-click: this one is the pointer's own)
    const dbl = await call('Tdbl', { x: rx, y: ry });
    await sleep(900);
    for (const t of ['click', 'dblclick']) removeEventListener(t, noteE, true);
    const stale = !row.isConnected;
    r = await shot('24_parts_filter');
    log(`parts list: filter "belt": ${shown.length} of ${$('plist').children.length} rows shown (${shown.slice(0, 4).map(e => e.dataset.f)}); real double-click on "${row.dataset.f}"${dbl ? '' : ' NOT MADE (window not in front)'} (the page saw ${evs.join(', ') || 'NOTHING'}): ` +
        `selection ${v.selection.length} parts (the row's ${row._parts.length}), the eye moved ${c0.distanceTo(v.camera.position).toFixed(1)} mm to frame them (the row's element ${stale ? 'was replaced by the first click' : 'is still the one clicked'}); native ${r.counts.sel} selected`);
    pf.value = ''; pf.dispatchEvent(new Event('input')); key('Escape'); await tap('p');
    $('views').querySelector('.vw[data-d="0.55,-1,0.5"]').click(); await sleep(300);

    // measure: the highlight under the pointer (a real mouse move, no click)
    await tap('m');
    for (let i = 0; i < 100 && !M.geo; i++) await sleep(100);
    const h = hitNear(0.5, 0.45);
    const b0 = await shot('25_hover_before');
    await call('Tmouse', { ops: [[WM.move, 0, h.x - 3, h.y, 60], [WM.move, 0, h.x, h.y, 300]] });
    await sleep(300);
    const hov = v.meas.hover;
    const b1 = await shot('25_hover');
    let changed = -1;
    {
      const q = await call('Tshot', { name: '', find: [{ rgb: [255, 224, 138], at: [h.x, h.y], r: 60, tol: 60 }] });
      changed = q.found[0] ? q.found[0][2] : 0;
    }
    log(`measure hover: pointer moved to ${J([h.x, h.y])} on ${h.name}: the page highlights ${hov ? hov.kind + ' on ' + hov.part.name : 'NOTHING'}; hover mark object ${v.meas.objs.hover ? 'present' : 'absent'}; ` +
        `pixels of the hover colour (#ffe08a) within 60 px of the pointer in the window: ${changed} (want > 0)`);
    await call('Tmouse', { ops: [[WM.move, 0, 5, Math.round(H / 2), 200]] });
    await tap('m');
  }

  // ── the window: sized by the desktop's own sizing loop, minimised and brought back, its title
  async function size() {
    let w0 = await win();
    log(`window title "${w0.title}"; the page's title "${document.title}"`);
    // the bottom-right corner, taken in and up, then out again a little
    const K = (k, n) => Array.from({ length: n }, () => [VK[k], 35]);
    const seenSizes = new Set();
    const onr = () => seenSizes.add(innerWidth + 'x' + innerHeight);
    addEventListener('resize', onr);
    await call('Tsize', { keys: [...K('right', 1), ...K('down', 1), ...K('left', 14), ...K('up', 9), ...K('right', 4)] });
    await sleep(500);
    removeEventListener('resize', onr);
    let w1 = await win();
    log(`drag-resize (the desktop's sizing loop, corner moved by 30 arrow steps): client ${w0.client.join('x')} -> ${w1.client.join('x')}; the shell resized its picture ${w1.resizes - w0.resizes} times on the way, ` +
        `the page saw ${seenSizes.size} sizes; page now ${innerWidth}x${innerHeight} css px @ ${dpr()} = ${innerWidth * dpr()}x${innerHeight * dpr()} device px`);
    const part = M.list.find(p => { if (p.mesh || p.col || p.mat.transparent || p.iCount < 3000) return false;
      const bx = new THREE.Box3(); for (const q of partVerts(p)) bx.expandByPoint(q);
      const s = bx.getSize(new THREE.Vector3()).length(); return s > 60 && s < 300; });
    await align('26_align_dragged', [part.name], 'after the drag-resize');
    v.showAll();
    $('views').querySelector('.vw[data-d="0.55,-1,0.5"]').click(); await sleep(200);
    await shot('27_dragged');
    log('    ' + overlap());

    // minimise; change the picture while it is away; bring it back
    await rest();
    w0 = await win();
    await call('Tmin', { on: true }); await sleep(900);
    w1 = await win();
    const unit = M.list.find(p => !p.mesh && !p.col && p.iCount > 3000);
    v.setHidden(M.units.get(unit.unit), true);
    await sleep(900);
    const w2 = await win();
    await call('Tmin', { on: false }); await sleep(700);
    const r = await shot('28_restored');
    const w3 = await win();
    log(`minimise: minimised ${w1.minimized}; frames traced while away ${w2.renders - w0.renders}, presents ${w2.presents - w0.presents} (a part was hidden on the page meanwhile); ` +
        `restored: minimised ${w3.minimized}, client ${w3.client.join('x')}, frames traced since ${w3.renders - w2.renders}; page ${hiddenN()} hidden, native ${r.counts.hidden} hidden`);
    v.showAll();
    await call('Tresize', { w: 1280, h: 800 }); await sleep(400);
    $('views').querySelector('.vw[data-d="0.55,-1,0.5"]').click(); await sleep(200);
  }

  // ── the model file changes under the page (a rebuild): the page's own watch reloads it, the shell follows
  async function reload() {
    const unit = M.list.find(p => !p.mesh && !p.col && p.iCount > 3000);
    v.setHidden(M.units.get(unit.unit), true);
    v.camera.position.multiplyScalar(0.8); v.controls.update();
    await shot('29_before_reload');
    const key0 = M.key, glb0 = v.native.glb, cam0 = v.camera.position.clone(), list0 = M.list;
    const t0 = performance.now();
    const said = await call('Trecopy');
    let waited = 0;
    while (M.key === key0 && waited < 15000) { await sleep(100); waited += 100; }
    while ((M.list === list0 || !M.list.length) && waited < 30000) { await sleep(100); waited += 100; }
    const t1 = performance.now();
    await sleep(1500);
    const r = await shot('30_after_reload', { diff: '29_before_reload' });
    log(`reload: ${said}. The page's watch saw the new stamp and loaded the model again ${((t1 - t0) / 1000).toFixed(1)} s later: key ${key0} -> ${M.key}; ` +
        `the shell was told ${glb0.split('?')[1]} -> ${v.native.glb.split('?')[1]}; camera kept (moved ${cam0.distanceTo(v.camera.position).toFixed(3)} mm); ` +
        `hidden kept: page ${hiddenN()}, native ${r.counts.hidden}; status "${$('status').textContent.slice(0, 50)}"`);
    v.showAll(); v.camera.position.multiplyScalar(1.25); v.controls.update();
  }

  // ── MOVING against AT REST: a frame from the middle of a movement, and the same view traced to rest
  async function motion() {
    const snap = async (name, after, go, what) => {
      await rest();
      await call('Tmeas', { on: true });
      const p = call('Tsnap', { name, after });
      await go();
      const r = await Promise.race([p, sleep(8000).then(() => null)]);
      await sleep(600);
      const m = await call('Tmeas', { on: false });
      if (!r) { log(`[motion ${name}] NO FRAME ${after} of the movement came`); return; }
      log(`[motion ${name}] ${what}: frame ${after} of the movement (${r.spf} samples a pixel in it) against the same view at rest, ${r.size.join('x')}: ` +
          `mean |difference| ${r.mean.toFixed(2)}/255 over the picture, ${r.mean_on_model.toFixed(2)}/255 over the model's pixels (${(100 * r.model_share).toFixed(0)}% of it); ` +
          `${(100 * r.changed_share).toFixed(2)}% of pixels off by more than 24; mean luminance moving - rest ${r.lum_bias.toFixed(2)}/255\n` + m);
    };
    const iso = () => { $('views').querySelector('.vw[data-d="0.55,-1,0.5"]').click(); };
    iso(); await sleep(300);
    await snap('orbit_whole', 90, () => drag(cx, cy + 40, cx - 240, cy - 30, 150), 'orbit, the whole instrument');
    // close in, the deck off: boards, wires, contact shadows (the quality view B)
    v.setHidden(M.list.filter(p => ['top_plate', 'fret_', 'pickup', 'ui_', 'wire_fret_led', 'wire_pickup', 'wire_ui'].some(x => p.name.startsWith(x))), true);
    v.camera.position.set(-260.1, 208.55, 240); v.controls.target.set(-387, -67, 28); v.controls.update();
    await sleep(300);
    await snap('orbit_close', 90, () => drag(cx, cy + 40, cx - 160, cy - 20, 150), 'orbit, close in under the deck');
    await snap('orbit_close_slow', 40, () => drag(cx, cy, cx - 30, cy - 6, 150), 'slow orbit (0.2 px a frame), close in');
    v.showAll(); iso(); await sleep(300);
    // strings and fret lines from above
    v.camera.position.set(-100, 420, 160); v.controls.target.set(-330, 20, 40); v.controls.update();
    await sleep(300);
    await snap('orbit_strings', 90, () => drag(cx, cy + 40, cx - 200, cy - 20, 150), 'orbit over the strings and fret lines');
    iso(); await sleep(300);
    // the rig easing: a pedal pressed, the camera still
    const node = rig.pedals[0].swing_nodes[0];
    v.select([node]); v.selAction('zoom'); v.select([]);
    v.camera.position.lerp(v.controls.target, -1.2); v.controls.update();     // back off: the pedals and what they sit on
    await sleep(400);
    await snap('rig_press', 14, async () => { key('1', 'keydown'); await sleep(700); }, 'pedal 1 going down (camera still)');
    await snap('rig_release', 14, async () => { key('1', 'keyup'); await sleep(700); }, 'pedal 1 coming back');
    iso(); await sleep(300);
    await snap('rig_whole', 14, async () => { key('1', 'keydown'); key('q', 'keydown'); await sleep(700); key('1', 'keyup'); key('q', 'keyup'); }, 'pedal 1 and LKL together, the whole instrument');
    await sleep(800);
  }

  // ── at rest nothing is drawn
  async function idle() {
    v.showAll(); await sleep(300); await rest(); await sleep(600);
    const a = await win();
    await sleep(2000);
    const b = await win();
    log(`idle: at rest (${b.spp} of ${b.cap} samples) for 2.0 s: frames traced ${b.renders - a.renders}, compute dispatches ${b.dispatches - a.dispatches}, presents ${b.presents - a.presents}, status lines sent to the page ${b.status_lines - a.status_lines}`);
    // and it wakes: one mouse move over nothing changes nothing; a wheel notch does
    await wheel(cx, cy, 1); await sleep(100);
    const c = await win();
    await rest(); await sleep(300);
    const e = await win();
    log(`    then one wheel notch: ${c.renders - b.renders} frames traced within 0.16 s; at rest again after ${e.renders - b.renders} frames in all (${e.spf_moving} samples a moving frame, budget ${e.budget_ms} ms)`);
    await wheel(cx, cy, -1); await sleep(300);
  }

  // ── how long a pedal keeps the card busy: from the key going down to the picture at rest
  async function settle() {
    v.showAll(); await sleep(300); await rest(); await sleep(300);
    for (const [what, ev] of [['pedal 1 pressed', 'keydown'], ['pedal 1 let go', 'keyup']]) {
      const a = await win(), t0 = performance.now();
      key('1', ev);
      await sleep(150); await rest();
      const b = await win();
      log(`settle: ${what}: at rest ${(performance.now() - t0).toFixed(0)} ms later, after ${b.renders - a.renders} frames traced (${b.spp} of ${b.cap} samples)`);
      await sleep(300);
    }
  }

  // ── the camera moved WHILE a pedal is down: what the page and the tracer each manage
  async function pedalcam() {
    v.showAll(); await sleep(300); await rest(); await sleep(300);
    async function orbit(what) {
      const gaps = []; let last = 0, on = true;
      const tick = t => { if (last) gaps.push(t - last); last = t; if (on) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
      const a = await win(), t0 = performance.now();
      await drag(cx - 150, cy, cx + 150, cy + 40, 200);
      const ms = performance.now() - t0, b = await win();
      on = false;
      gaps.sort((x, y) => x - y);
      log(`pedalcam: ${what}: ${b.renders - a.renders} frames traced in ${ms.toFixed(0)} ms (${((b.renders - a.renders) * 1000 / ms).toFixed(0)} a second); the page's own frames: ${gaps.length}, median ${gaps[gaps.length >> 1].toFixed(1)} ms apart, 95% within ${gaps[Math.floor(gaps.length * 0.95)].toFixed(1)}, worst ${gaps[gaps.length - 1].toFixed(1)}`);
      await rest(); await sleep(200);
    }
    await orbit('orbit, no pedal');
    key('1', 'keydown'); await sleep(2500);
    await orbit('orbit with pedal 1 held (settled)');
    key('1', 'keyup'); await sleep(2500);
    key('1', 'keydown');
    await orbit('orbit begun as pedal 1 goes down');
    key('1', 'keyup'); await sleep(50);
    await orbit('orbit begun as pedal 1 comes back');
    await sleep(1500);
    // ...and with a part selected, whose tint the page draws over the picture
    await click(cx, cy); await sleep(300);
    log(`pedalcam: selected ${J(selUnits())}`);
    await orbit('orbit, a part selected, no pedal');
    key('1', 'keydown'); await sleep(2500);
    await orbit('orbit, a part selected, pedal 1 held');
    key('1', 'keyup'); await sleep(100);
    await orbit('orbit, a part selected, as pedal 1 comes back');
    key('Escape'); await sleep(1500);
  }

  // ── the same with REAL messages: the mouse dragging while the key goes down, repeats and comes up
  // (where 2, "the hand": the pointer and the keys go through the desktop's own input queue, which is the
  // only way to see what a person gets: the page's input can be held up there by the shell and by nothing
  // a posted message meets. `wheel`: the wheel is turned, in and back out, instead of the drag.)
  async function realcam(where = 0, keys = ['1'], wheel = false) {
    if (where === 2 && !(await win()).foreground) { log(`hand (${keys.join(' and ')}${wheel ? ', wheel' : ''}): NOT RUN: this window is not in front, and typed keys go to whatever is (run --selftest=hand by itself)`); return; }
    v.showAll(); await sleep(300); await rest(); await sleep(300);
    const vk = { 1: 0x31, q: 0x51 };
    const evs = [], T = () => performance.timeOrigin + performance.now();   // the shell's clock
    let moves = 0, wheels = 0;
    const note = e => evs.push([T(), e.type, e.key || '', e.repeat ? 'r' : '', e.isTrusted ? 't' : 's']);
    const count = e => { if (e.type === 'wheel') wheels++; else moves++; };
    const heard = ['keydown', 'keyup', 'pointerdown', 'pointerup', 'pointercancel', 'lostpointercapture', 'blur', 'focus'];
    for (const t of heard) addEventListener(t, note, true);
    for (const t of ['pointermove', 'wheel']) addEventListener(t, count, true);
    // each page frame: how far the camera has gone so far (degrees round its target, mm towards or away
    // from it, each summed frame to frame), how many controls are lit, how many moves have come
    const cam = [], gaps = []; let last = 0, on = true, az = null, far = 0, turn = 0, dolly = 0, nf = 0;
    const tick = t => {
      if (last) gaps.push(t - last); last = t;
      const a = v.controls.getAzimuthalAngle() * 180 / Math.PI, f = v.camera.position.distanceTo(v.controls.target);
      if (az !== null) { const da = Math.abs(a - az); turn += Math.min(da, 360 - da); dolly += Math.abs(f - far); }
      az = a; far = f;
      cam.push([turn, dolly, document.querySelectorAll('.pedal.on:not(#deckbtn)').length, moves + wheels]);
      if (++nf % 8 === 0) post({ t: 'Tping', at: T() });
      if (on) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    await call('Tpings');
    const a = await win(), T0 = T();
    const d = wheel ? call('Tdrag', { x0: cx, y0: cy, x1: cx, y1: cy, n: 24, ms: 100, wheel: true })
            : where === 2 ? call('Tdrag', { x0: cx - 300, y0: cy, x1: cx + 300, y1: cy + 60, n: 300, ms: 8 })
            : drag(cx - 300, cy, cx + 300, cy + 60, 600);            // 2.4 s of it
    await sleep(600);
    // the keys down, held 0.8 s (repeating as a held key does), and up
    const ops = [];
    for (let i = 0; i < 24; i++) for (const k of keys) ops.push([where, vk[k], 1, i ? Math.round(33 / keys.length) : 5]);
    for (const k of keys) ops.push([where, vk[k], 0, 25]);
    const Tk = T(), kr = await call('Tkey', { ops }), Tu = T() - 25;   // (the last key-up is followed by a 25 ms wait)
    const dr = await d, Td = T();
    await sleep(300);
    const st = await win(), ms = T() - T0, lag = await call('Tpings');
    on = false;
    for (const t of heard) removeEventListener(t, note, true);
    for (const t of ['pointermove', 'wheel']) removeEventListener(t, count, true);
    gaps.sort((x, y) => x - y);
    const lit = cam.map((c, i) => c[2] > 0 ? i : -1).filter(i => i >= 0), k0 = lit.length ? lit[0] : -1, k1 = lit.length ? lit[lit.length - 1] : -1;
    const went = (i, j) => i < 0 || j < 0 ? '?' : (wheel ? (cam[j][1] - cam[i][1]).toFixed(1) + ' mm' : (cam[j][0] - cam[i][0]).toFixed(1) + ' deg') + ` (${cam[j][3] - cam[i][3]} ${wheel ? 'wheel events' : 'pointer moves'})`;
    const first = (type, k) => evs.find(e => e[1] === type && (k === undefined || e[2] === k) && e[3] !== 'r');
    const rel = (e, since) => e ? (e[0] - since).toFixed(0) + ' ms' : 'NEVER';
    const stuck = k1 === cam.length - 1;
    log(`hand (${['keys posted to the page', 'keys posted to the shell window', 'pointer and keys through the input queue, as a hand'][where]}): ${wheel ? 'the wheel turned for 2.4 s' : 'a 2.4 s drag'}, ${keys.join(' and ')} held 0.8 s inside it`);
    log(`    keys ${J(kr)}; ${wheel ? 'wheel' : 'drag'} ${J(dr)}; foreground ${st.foreground}, the keyboard with ${st.focus_class}${st.focus_is_shell ? ' (the shell)' : ''}`);
    log(`    ${st.renders - a.renders} frames traced in ${ms.toFixed(0)} ms; page frames ${gaps.length}, median ${gaps[gaps.length >> 1].toFixed(1)} ms apart, 95% within ${gaps[Math.floor(gaps.length * 0.95)].toFixed(1)}, worst ${gaps[gaps.length - 1].toFixed(1)}; a message from the page waits for the shell, ms: ${lag}`);
    log('    ' + keys.map(k => `keydown ${k} ${rel(first('keydown', k), Tk)} after it was asked for, keyup ${k} ${rel(first('keyup', k), Tu)} after the typing ended`).join('; ') +
        `; repeats ${evs.filter(e => e[3] === 'r').length} of ${23 * keys.length}` +
        (wheel ? `; wheel events ${wheels} of 24` : `; pointerdown ${rel(first('pointerdown'), T0)} after the drag was asked for, pointerup ${rel(first('pointerup'), Td)} after it was done (it is told 60 ms after the button comes up); pointer moves ${moves}`));
    log(`    controls lit from page frame ${k0} to ${k1} of ${cam.length}${stuck ? ' (STILL LIT at the end)' : ''}; the camera went ${went(0, k0)} before, ${went(k0, k1)} while lit, ${went(k1, cam.length - 1)} after`);
    const odd = evs.filter(e => !['keydown', 'keyup', 'pointerdown', 'pointerup', 'lostpointercapture'].includes(e[1]) || e[4] !== 't');
    if (odd.length) log(`    other events: ${J(odd.slice(0, 20).map(e => [e[0] - T0, ...e.slice(1)]))}`);
    const bad = [];
    for (const k of keys) {
      const dn = first('keydown', k), up = first('keyup', k);
      if (!dn || dn[0] - Tk > 60) bad.push(`keydown ${k} late or lost`);
      if (!up || up[0] - Tu > 60) bad.push(`keyup ${k} late or lost`);
    }
    if (!wheel && !first('pointerup')) bad.push('no pointerup');
    if (k0 < 0 || stuck) bad.push(k0 < 0 ? 'nothing lit' : 'a control stuck lit');
    const c = wheel ? 1 : 0;
    if (k0 >= 0 && !(cam[k0][c] > 1 && cam[k1][c] - cam[k0][c] > 1 && cam[cam.length - 1][c] - cam[k1][c] > 1)) bad.push('the camera stopped');
    log(`    ${bad.length ? 'FAILED: ' + bad.join(', ') : 'ok'}`);
    for (const k of keys) key(k, 'keyup');
    await sleep(1500);
  }

  async function main() {
    while (!(window.viewer && viewer.M.parts && viewer.M.list.length && !$('loading'))) await sleep(100);
    v = window.viewer; M = v.M; THREE = v.THREE;
    log(`page loaded: ${location.href}  NATIVE=${v.NATIVE}  ${innerWidth}x${innerHeight} css px @ dpr ${dpr()}  ${M.list.length} parts (${M.list.filter(p => p.mesh).length} the rig moves)`);
    log(`light button display "${$('bLight').style.display}", lighting level ${v.quality}; canvas alpha ${v.renderer.getContextAttributes().alpha}; html background "${getComputedStyle(document.documentElement).backgroundColor}"`);
    rig = await (await fetch('rig.json')).json();
    await sleep(2500);                                            // the pick trees, and the rig tuning up to open
    // the capture's white level, on an opaque green square (HDR desktop)
    const sw = document.createElement('div');
    sw.style.cssText = 'position:fixed;right:20px;top:120px;width:40px;height:40px;background:rgb(0,255,0);z-index:99';
    document.body.appendChild(sw);
    await sleep(300);
    const b = sw.getBoundingClientRect();
    await call('Tshot', { name: '', green: [b.x, b.y, b.width, b.height].map(x => x * dpr()) });
    sw.remove();
    const w = await win();
    log(`backend ${w.backend}; window title "${w.title}" (the page's: "${document.title}"); window ${w.client.join('x')} at ${w.outer}; the keyboard is with "${w.focus_class}"${w.focus_is_shell ? ' (the shell)' : ''}`);
    // how the desktop shows the native picture: its backdrop, as captured, under the page's canvas and with the canvas gone
    {
      const at = [[Math.round(innerWidth * dpr() * 0.9), Math.round(innerHeight * dpr() * 0.5)], [Math.round(innerWidth * dpr() * 0.3), Math.round(innerHeight * dpr() * 0.5)]];
      const s1 = await call('Tshot', { name: '', sample: at });
      $('view').style.display = 'none'; await sleep(400);
      const s2 = await call('Tshot', { name: '', sample: at });
      $('view').style.display = ''; await sleep(200);
      log(`backdrop pixels (right, left): native image ${J(s1.sample.map(x => x.native))}; in the window ${J(s1.sample.map(x => x.dda))}; with the page's canvas removed ${J(s2.sample.map(x => x.dda))}`);
    }
    d = dpr(); W = innerWidth * d; H = innerHeight * d; cx = Math.round(W / 2); cy = Math.round(H / 2);
    if (only.includes('place1')) { await call('Tplace', { x: 211, y: 133, w: 1111, h: 707 }); await sleep(600); const p = await win(); log(`place: window put at ${p.outer} with client ${p.client.join('x')}; closing now, to be found there next run`); }
    if (want('base')) await base();
    if (want('keys')) await keys();
    if (want('rows')) await rows();
    if (want('size')) await size();
    if (want('reload')) await reload();
    if (want('motion')) await motion();
    if (want('idle')) await idle();
    if (want('settle')) await settle();
    if (want('pedalcam')) await pedalcam();
    if (want('realcam')) { await realcam(0); await realcam(1); }
    if (want('hand') || only.includes('hand1')) await realcam(2);
    if (want('hand')) { await realcam(2, ['q']); await realcam(2, ['1', 'q']); await realcam(2, ['1'], true); }
    if (only.includes('handloop')) for (let i = 0; i < 3; i++) { await realcam(2); await realcam(2, ['1', 'q']); }
    // ── quality: the two fixed views, native against the page's Blender tracer
    if (want('quality') || only.includes('native')) {
      const blender = !only.includes('native');
      if (blender) await fetch('trace.json?warm=1');
      await quality('A', [300, -700, 500], [-330, -40, 0], [], blender);
      await quality('B', [-260.1, -240, 208.55], [-387, -28, -67], ['top_plate', 'fret_', 'pickup', 'ui_', 'wire_fret_led', 'wire_pickup', 'wire_ui'], blender);
    }
    log('selftest finished');
    post({ t: 'Tdone' });
  }
  main().catch(e => { log('SELFTEST FAILED: ' + (e && e.stack || e)); post({ t: 'Tdone' }); });
})();
