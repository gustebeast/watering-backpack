# PCBs in a printed assembly

How to design a circuit board that lives inside a 3D-printed product, so that the board
KiCad sends to the fab and the board the CAD builds its housing around are **the same
board**. Two parts: the tooling that keeps them the same, and the design guidance that no
tool can enforce.

Everything here was learned on a real instrument with fourteen boards. Where a rule has a
story, the story is the one-line reason next to it.

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
| `cadkit/pcb.py` | your CAD Python | the plastic: `pcb_cradle` (one-screw drop-in mount), drawing-accurate JST XH / PH headers with tails and mated plugs |

### Setting a project up

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
