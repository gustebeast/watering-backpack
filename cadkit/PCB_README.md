# PCBs in a printed assembly

How to design a circuit board that lives inside a 3D-printed product, so that the board
KiCad sends to the fab and the board the CAD builds its housing around are **the same
board**. Three parts: **making** a board from code (§0), the tooling that keeps KiCad and
the CAD agreeing on it (§1), and the design guidance that no tool can enforce (§2–5).

> **Starting a board in a new project? Do §0 top to bottom.** You do not need to write a
> generator pipeline and you do not need to hand-route: copy `pcbflow/example/blinky.py`,
> change the circuit and the placements, run two commands.

Everything here was learned on a real instrument with fourteen boards. Where a rule has a
story, the story is the one-line reason next to it.

---

## 0. Making a board

A board is **one Python file** in your project. It states the circuit and where every part
goes; `cadkit/pcbflow` places, autoroutes, checks, labels and exports it.

```
  elec/<board>.py            you write this          (your CAD Python + SKiDL)
        │  py -3.12 elec/<board>.py
        ▼
  elec/out/<board>.net  +  elec/out/<board>.board.json
        │  <KiCad python> cadkit/pcbflow/finish.py elec/out/<board>
        ▼
  elec/out/<board>.kicad_pcb      placed, routed, DRC-clean, labelled   (open it in KiCad)
  elec/geom/<board>.geom.json     what the CAD builds the board from    (commit this)
        │  <KiCad python> elec/fab.py <board>
        ▼
  elec/out/fab/<board>.zip        gerbers, drill, BOM, CPL, ORDER.txt, ROTATION-CHECK.txt
```

### One-time machine setup

| needs | where |
|---|---|
| KiCad 10 | its `bin/python.exe` (has `pcbnew`) and `bin/kicad-cli.exe` |
| SKiDL | `py -3.12 -m pip install skidl` — in your CAD Python, not KiCad's |
| Java 25 runtime | e.g. Temurin JRE 25; found under `%LOCALAPPDATA%\Programs\temurin\`, on `PATH`, or via `$JAVA` |
| freerouting 2.x | `freerouting.jar` at `%LOCALAPPDATA%\Programs\freerouting\`, or `$FREEROUTING_JAR`. ~64 MB, deliberately not in any repo — and never in a temp folder |

### The first board

```bash
mkdir elec
cp cadkit/pcbflow/example/blinky.py elec/blinky.py
cp cadkit/pcbflow/example/fab.py    elec/fab.py
cp cadkit/pcbflow/example/cad_geom_check.py elec/cad_geom_check.py   # then point its _cad() at your assembly
py -3.12 elec/blinky.py
"C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/pcbflow/finish.py elec/out/blinky
```

The last line must end `blinky: 0 unconnected, 0 violation(s)`. Then in the CAD:
`Boards("elec/geom").solid("blinky")`. Git-ignore `elec/out/`; commit `elec/geom/`.

### What a board file contains

1. **The circuit**, in SKiDL. `gen.part(ref, value, footprint, pins)` defines a part inline
   with exactly the pins you give it — no symbol library, so the file is complete in
   itself. Connect with `net += part[pin], …`. `value` is what the BOM orders by: a value
   for a passive, the manufacturer part number for everything else.
2. **`BOARD_NOTES`** — the board (table below). In a real project its numbers are
   *derived from the mechanical model*: import your dimensions module and compute the
   outline and connector positions from the pocket the board sits in. That is the point
   of generating a board — the placements come from the product's geometry.
3. **Assertions** for everything DRC cannot see (§2, §4): parts clear of printed walls,
   tails over their support, courtyard gaps, the outline equal to the CAD's pocket. A bad
   placement should stop the generator, not surface an hour later.
4. `gen.emit(board, OUT_DIR, BOARD_NOTES)` — runs ERC and the netlist checks (return nets
   that never meet; a pin alone on its net), then writes the two files.

**Edit → regenerate → finish.** `finish.py` does not run the generator; it refuses to
route if `<board>.py` is newer than its netlist, because routing stale placements returns
a believable answer to a question nobody asked.

### `BOARD_NOTES`

Millimetres, **board-centred, +Y up** (the CAD's frame — `layout.py` flips to KiCad's).

| key | meaning |
|---|---|
| `outline_mm` | `(w, l)` — required. The layout region; also the outline unless `outline_poly` is given |
| `outline_poly` | `[(x, y), …]` the real outline when it is not a rectangle (a mounting ear makes an L) |
| `cutouts` | `[{"xy": (x, y), "d": 4.5}]` round holes through the board (mounting holes) |
| `outline_slots` | `[{"poly": [...]}]` non-round cutouts |
| `layers`, `thickness_mm` | `2` or `4`; `1.6` |
| `placements` | `{ref: (x, y, rot)}` — required, one per part. **The part's PAD CENTROID**, not its footprint origin; `rot` is KiCad's, degrees |
| `back_refs` | refs mounted on the back. `single_sided: True` records that all parts share one face (one assembly setup) |
| `zones` | `[(net, layer, inset)]` copper pours, pulled `inset` in from the edge |
| `plane_layers` | inner layers that are planes: the router is kept off them |
| `stitch_nets` | nets whose pads get a via straight down to their pour (usually `("GND",)`) |
| `track_mm`, `via_mm` | default track width (0.25) and via `(diameter, drill)` (0.6, 0.3) |
| `net_widths` | `{net pattern: width}` for supply nets — sized from current, not left at the default |
| `tracks`, `vias` | copper laid **before** routing: `(net, layer, width, [(x, y), …])`, `(net, x, y)`. A last resort (§4) |
| `frozen_nets` | nets whose pre-laid copper the router may not touch |
| `pin_escapes` | `("U1.27", …)` fine-pitch pins given a stub + via before routing |
| `edge_escape` | `("J5",)` board-edge headers whose edge-side row is fanned round the other row's ends |
| `match` | length-matched groups for `verify.py`: `{"name", "nets", "max_skew_mm", "same_layer", "max_vias", "why"}` |
| `router_passes`, `finish_rounds` | autorouter passes (10) and route-retry rounds (1). Raise only with evidence |
| `refs_on_fab`, `ref_pos` | move designators to F.Fab on a dense board; or place one by hand |
| `strip_silk` | ref prefixes of parts no ink may come near (optical sensors) |
| `quality` | the board's quality record: supply paths and currents, decoupling limits, pinout citations, manual sign-offs, waivers. **Every key is in `PCB_QUALITY.md`** |
| `order_options` | `{key: text}` extra order-form settings for this board's `ORDER.txt` |
| `qty_per_instrument` | how many the product uses (for totals) |

`layout.py` reads a few more, each documented where it is used (`diff_pairs`,
`local_nets`, `corridors`, `via_keepouts`, `land_resize`, `post_route_*`,
`repair_tracks`/`repair_vias`, `stitch_exceptions`). Reach for those only when a route
shows you need one.

### Footprints

KiCad's libraries are found automatically (`"Resistor_SMD:R_0603_1608Metric"`). For a
part KiCad has no land for, draw `elec/footprints/<Lib>.pretty/<Name>.kicad_mod` from the
maker's recommended land pattern and name it `"<Lib>:<Name>"`. **Give it an F.Fab outline
of the real body** — that outline is what the CAD draws — and add its `HEIGHT` / `TAIL`.

### What a project may add (all optional, all in `elec/`)

| file | job |
|---|---|
| `cad_geom_check.py` | `<cad python> elec/cad_geom_check.py <board>`: hands `cadkit.board_check.check` the solid your assembly places. `finish.py` runs it last; without it the run says **the CAD is UNCHECKED** |
| `pcb_declared.py` | `declared(board, vtype, refs) -> bool`: DRC violations the design accepts on purpose, **by shape**. A count is not a check |
| `silk.py`, `export_geom.py` | replace the default labeller / exporter (e.g. to pass a revision) |
| `fab.py` | the board list and the value → part-number table, handed to `pcbflow/fab_package.py`; see `pcbflow/example/fab.py` |

### Reading a result

* **`0 unconnected, 0 violation(s)`** with no `FAIL` line from verify is the only clean
  ROUTE. The same line ends `| quality: N FAIL, M OPEN`: the standard validation pass
  (`PCB_QUALITY.md`). A board may be ordered only at `0 FAIL, 0 OPEN`.
* `N unconnected`: read *which* nets and *where* in `<board>.finish.drc.json` before
  touching anything. If they cluster at one part, it is a placement problem (§4), not a
  router problem.
* The pipeline closes the last net or two itself (`close_last.py`, a maze search on the
  routed board, kept only if DRC is strictly better). If it reports "no path", the
  placement really is blocked.
* An autorouter at its limit gives a different answer every run. Revert and re-run before
  concluding anything from one result.
* Open `elec/out/<board>.kicad_pcb` in KiCad to look. Never hand-edit it: the next run
  replaces it. Change the generator.

### Routing by hand instead

Allowed, and the rest of the loop is identical: produce any routed `.kicad_pcb`, run
`kicad_silk.py` and `kicad_geom.py` on it, and gate with `board_check`. You lose
regeneration — when the housing moves a connector, someone re-routes — so prefer the
generator for any board whose geometry comes from the mechanical design.

---

## 1. The loop: one board, two programs

```
  KiCad (.kicad_pcb, routed)
        │   cadkit/kicad_silk.py     labels the board (optional)        ┐ KiCad's
        │   cadkit/kicad_geom.py     reads the ROUTED board back        ┘ own Python
        ▼
  <project>/elec/geom/<board>.geom.json        ← COMMIT THIS
        │   cadkit.board_geom.Boards           laminate + bodies + tails ┐ CadQuery
        ▼                                                                │
  your assembly places Boards.solid(board) ──► STEP ──► the viewer       │
        │   cadkit.board_check.check           is the CAD's board the    │
        ▼                                      routed one?               ┘
  a gate: 0 disagreements, or the build is red
```

| module | runs under | what it does |
|---|---|---|
| `cadkit/kicad_geom.py` | KiCad's Python (`pcbnew`) | routed `.kicad_pcb` → `<board>.geom.json`: outline polygon, cutouts, thickness, every footprint's position / rotation / side / **F.Fab body box** / through-hole pad extent, and board-level silkscreen text |
| `cadkit/kicad_silk.py` | KiCad's Python | prints the board's name + revision, test-pad nets and connector pinouts, each only where it fits; cannot move copper |
| `cadkit/board_geom.py` | your CAD Python (CadQuery) | `Boards(geom_dir)`: `solid()`, `solid(mated=True)`, `plate()`, `bodies()`, `silk()`, `mouth()`, `lead_exit()`, `tails()`, `holes()`; plus the shared part tables `HEIGHT`, `TAIL`, `THT_LEGS`, `PANEL` |
| `cadkit/board_check.py` | your CAD Python | `check(name, solid, geom)`: every routed part present, not mirrored, cutouts match |
| `cadkit/pcbflow/` | both (see §0) | **makes** the board: generator helpers, layout, autoroute, DRC, repair, verify, fab package |
| `cadkit/pcb.py` | your CAD Python | the plastic: `pcb_cradle` (one-screw drop-in mount), drawing-accurate JST XH / PH headers with tails and mated plugs |

### Setting a project up

(`pcbflow/finish.py` does steps 1–2 for a generated board; this is the by-hand version.)

1. **Export after every route**, as the last step of whatever produces the board:

   ```bash
   "C:/Program Files/KiCad/10.0/bin/python.exe" cadkit/kicad_geom.py --out elec/geom elec/out/controller
   ```

   The two KiCad-side scripts import nothing but `pcbnew`, so they run in KiCad's bundled
   interpreter with no install step. They work on any routed board — hand-routed in the
   GUI or generated.

2. **Commit `elec/geom/`.** The CAD builds from it; a checkout without KiCad must still
   build. Routed boards and fab output can stay git-ignored.

3. **One instance per project**, in a module the rest of your CAD imports:

   ```python
   from cadkit.board_geom import Boards
   BOARDS = Boards("elec/geom", height={"MyOddPart_Footprint": 4.2})   # overrides lay OVER the shared tables
   pcb = BOARDS.solid("controller").translate(WHERE_IT_SITS)
   ```

4. **Gate it.** For each board, hand `board_check.check` the solid your assembly actually
   places (any frame, any orientation — it finds the pose) and fail the build on a
   non-zero return. Run it in the board pipeline too, right after the export.

### What KiCad does not carry

A footprint has no Z. So four tables in `board_geom.py`, **keyed by footprint name**,
hold what is a fact about the *part* and the same on every board:

* `HEIGHT` — body height above the board. **Required**: a footprint with no entry raises,
  because a part with no height is a part the CAD silently leaves out. `0.0` = bare
  copper (test pad, solder jumper).
* `TAIL` — how far through-hole legs hang below the board; `0.0` = SMD. Required by
  `tails()`, so a new part forces the decision.
* `THT_LEGS` — one box per leg, for a part whose legs are far apart (a barrel jack).
* `PANEL` — a panel connector's mouth direction, axis height, nose, and the opening its
  panel needs.

**Every number says where it came from** — a maker's drawing, their STEP model, a
catalogue line, or `ESTIMATE`. An estimate is allowed; an unlabelled one is not. Add a
project-only part through `Boards(height=…)`; promote it into cadkit's table (canonical
repo, then propagate) once it has a source worth citing.

### The rules the tooling exists to enforce

* **Model from the routed board, never from the placement table.** A hand-typed copy of
  the placements can only be checked against itself, and it always agrees. It agreed
  while two connectors sat 0.54 mm short of the board edge and a panel hole was cut
  7.85 mm above its receptacle.
* **The F.Fab outline is the part; the courtyard is the keep-out.** Size plastic to
  F.Fab (plus clearance). A footprint with no F.Fab body gets `fab: null` and has to be
  dealt with on purpose.
* **A stale geom file looks exactly like a real disagreement.** If the CAD and the board
  disagree, check the file's age first. Export in the same step that routes.
* **Draw the mated envelope, not the bare header.** `solid(mated=True)` stands a
  top-entry JST at its plugged height and pushes a side-entry one out past the board
  edge. A housing sized off the bare socket is sized for a board nobody can plug in.
* **Through-hole tails are geometry.** An untrimmed 2.54 / 2.00 post hangs ~1.8 mm below
  a 1.6 mm board. `solid()` draws them; anything the board sits against has to clear
  them.
* **Check tails along the INSTALL STROKE, not at rest.** A board that slides into place
  drags its tails along a line. Translate the board back along its install axis and
  re-run the overlap check; or stand the connector so all pins share one coordinate; or
  use the SMT variant and delete the problem.
* **Compare cutouts, not just parts.** A part probe cannot see a wrong cutout, because a
  cutout is exactly where no part is. Ten slots once went to the fab as one rectangle
  with every other check green.

---

## 2. Mechanical: the board as a printed-assembly part

* **Rigid capture, one screw.** Plastic locates the board in every direction but its
  install direction; one screw closes that. No snap-fits or flexures holding a board.
* **Your own board: put the mounting hole THROUGH it** and grow the outline to make room.
  A head clamping the laminate round a hole holds in every direction; a screw beside the
  board laps a millimetre of edge. Use the project's one screw size.
* **A purchased board** (holes too small, or none): `pcb_cradle(hold_edge=…)` — the screw
  passes the edge and only its head reaches over the board.
* **Seat on pads, not on parts.** The board rests on corner pads / posts clear of
  bottom-side components. `standoff = seat_z − base_z` exactly; a fudge factor there is
  an interference.
* **A cradle fused into a larger part must have its anchor re-bored after the fuse** —
  the union refills the hole.
* **Decide the install direction first**, then check the cable can still be plugged with
  the board in place and that the board comes out without removing anything unrelated.
* **Connectors on the board edge face out of it.** A side-entry header's plastic belongs
  AT the edge with the pins or mouth overhanging, or the plug sinks into the laminate.
  Tell the fab which edges cannot carry panel rails.
* **Printed walls over a board are a keep-out DRC cannot see.** If plastic comes down
  onto the board face (a light baffle, a clamp, a rib), test every part's F.Fab body
  against those walls in the board generator, before routing — not an hour later in the
  overlap gate. Plastic may stand over copper; it may not stand over a part.
* **Panel connectors: cut each hole at that part's own axis height** (`mouth()`), and
  size a recessed receptacle's opening for the plug's overmold, not its shell.

---

## 3. Choosing connectors

* **Check that BOTH halves are in stock before comparing anything else.** Assembly
  houses stock sockets far better than headers (their customers mate to a module that
  already carries the other half). A joint where you supply both halves is the case the
  catalogue is worst at.
* **When both ends are your boards, use the SAME part at both ends** and hold the pin
  order in one shared constant that both board generators assert against.
* **Ask the mating axis before opening the catalogue.** Nearly every stocked
  board-to-board part mates along Z. If the joinery only lets the parts slide in X, a
  Z-mating connector is sheared, not unplugged. Coplanar X-axis mates are rare; plan for
  pogo pins or a cable.
* **For a blind mate, read the CONTACT AXIS HEIGHT off the maker's drawing.** A
  parametric table gives pitch, stroke and current; it does not say what surface, at what
  Z, the contact lands on. "Right-angle" in a catalogue does not mean the pin fires along
  the board.
* **Joinery engages before contacts touch.** The mechanical guide must be engaged and
  oriented before any contact meets its pad.
* **Plain 2.54 mm header + socket and single pogo pins are the dependable answers** for
  a roomy joint: both halves stocked, amps per pin, no gender problem. Do not rank
  fine-pitch mezzanine virtues on a joint that has 20 mm of width and no height limit.
* **An unshrouded header can be plugged in reversed.** Mark pin 1 in silk at both ends
  and put the check in the assembly notes — or pick a pin order that survives reversal.
* **Solder only on PCBs.** Leads are crimped; anything that would need a hand-soldered
  joint in the harness becomes a small board or a different connector.

---

## 4. Layout and routing (generated or by hand)

* **Placement is the design; the router only confirms it.** A board that needs fifty
  autorouter passes is a bad placement being brute-forced. When a net fails, find what
  physically blocks it — the via parked in front of the pin, the part in the lane — and
  move that.
* **Density is a line, not an area.** Average copper density hides a wall: a row of SMD
  parts is a barrier on *every* layer, because their escape vias pierce all of them.
  Measure across the cut a net has to cross.
* **Parts with a value but no required position get stranded.** Dividers, strap
  resistors, RC parts: place each beside the pin it serves, as a rigid cluster with its
  IC, or the router carries a net across the board for nothing.
* **Check courtyard GAPS, not just overlaps**, before routing (0.30 mm is a workable
  floor). A legal placement is not a routable one. Read land sizes from the footprint,
  not from memory of the part number.
* **Declaring copper before routing usually makes the board worse.** Empty-before-routing
  is not free-to-occupy: a pre-laid path is a permanent claim on the layer the router
  needs most. Prefer moving a part; prefer the smallest intervention; fix leftovers with
  a repair searched *after* routing, on the routed board.
* **A post-route repair is pinned to that one routing.** Coordinates pasted into a config
  go stale the moment anything re-routes. Search again every run, and accept a repair
  only if DRC afterwards is strictly better.
* **Give a boxed-in fine-pitch pin an escape** (a short stub and via, pre-laid) rather
  than hoping the router goes back for it; escape the edge-side row of a board-edge
  header round the ends of the other row.
* **After a failed experiment, revert and re-route to confirm the baseline** before
  drawing conclusions. An autorouter at its limit gives a different answer every run.
* **Clean means 0 unconnected AND 0 violations**, with length-matched groups inside
  budget and on one layer set. Compare violations first: a violation is a board that
  cannot be made; an open net is one that is not finished.
* **One pipeline run at a time**, and never write into its working folder mid-run.
* **Verify the artefact, not the log.** A pipeline whose generator died can still print a
  success line from a later stage.

---

## 5. Before ordering

**Run the quality pass to `0 FAIL, 0 OPEN`.** `PCB_QUALITY.md` is the standard validation
list every board is held to — automated rules (`pcbflow/quality.py`, run by `finish.py`)
and a manual checklist signed with evidence in the board's generator. It is also **where
a lesson from an ordered board goes**, so the next board is checked for it. What follows
here is guidance; that file is the gate.

**On the board**

* A **name and a revision** in silk on every board; bump the revision whenever copper
  changes on a re-order. Mirror-image boards must be distinguishable by reading them.
* **Test pads labelled with their net**; connector **pinouts** printed where they fit.
  The harness is crimped by hand against those pins.
* **Programming and bring-up access** on every MCU board: debug pads, reset, boot strap.
  A debug affordance is worth adding whenever it costs no board area — but nothing that
  switches in a signal band, and indicators on the digital rail, never the analog one.
* **ESD / surge protection** on every connector a hand or a long cable reaches.
* **Supply track widths sized from the current**, not left at the signal default.
* A designator beside every passive is *not* required: on a dense board it is ink on
  pads. Keep designators on the Fab layer; the assembly house places from the position
  file.
* Do not add your own fiducials or tooling holes to small boards for an assembly service
  that adds its own on the panel rails.

**On the order**

* **No hand soldering as a design assumption**: every part is either assembled by the
  fab or plugs in. A part the fab cannot place is a redesign, not a bodge.
* **Stock-check every line the same day**, both the part and anything it mates with.
* **Check placement rotations in the fab's previewer** for every polarised or
  multi-pin part; position-file conventions differ per footprint.
* Tell the fab where its **order number / date code** may be printed (or to omit it) —
  never beside an optical sensor.
* State which **edges carry overhanging parts** so panel rails go elsewhere.
* A part on the second face costs a second setup; decide deliberately.

**After ordering**

* Write the **bring-up order** before the boards arrive: power rails first with nothing
  else fitted, then programming access, then each interface in the order a fault would
  hide the next.
* Record every assembly-affecting decision (which way a cable goes on, which screw, what
  must be plugged before what is closed) in the project's install notes at the moment the
  design implies it.
