"""Checks a netlist must pass that nothing else in this pipeline can see.

⚠ EVERY CHECK IN HERE EXISTS BECAUSE A REAL FAULT GOT PAST EVERY OTHER ONE. DRC compares
copper against the netlist, so it is blind to anything wrong IN the netlist; ERC checks
pin drive types, so it is blind to topology; the router routes whatever it is handed.
A netlist that is internally consistent and describes a board that cannot work passes
all three in silence.
"""
import os
import re


def grounds_meet(path, declared_split=None):
    """Every return net must actually reach the others.

    ⚠ TWO GROUND NETS THAT NEVER MEET IS INVISIBLE TO THIS WHOLE PIPELINE. Each net is
    internally connected, so the ratsnest is empty and DRC is silent; the router routes
    both without complaint; ERC sees two power nets, each properly driven; the fab builds
    exactly what it was sent. The board does not work and the first evidence is a bench.

    Found on the OPTICAL board 2026-09-17: PWR_GND carried the buck, the 24 V inlet and
    the emitter switch; GND carried every load; no component in the netlist had a pin on
    both, so the buck's return path to its own loads was open. Then found again
    immediately on the OUTPUT PANEL, which is why this lives in a shared module instead
    of in the board that happened to be looked at first.

    A deliberate split PASSES, as long as it is finished: a net tie or a 0R is a
    component with a pin on each net, so the two land in one group. A split with nothing
    between them does not.

    ⚠ `declared_split` IS FOR A SPLIT THE BOARD MEANS AND CANNOT CLOSE ON ITS OWN, and
    it is deliberately awkward to use: it takes the reason, it must name the groups
    exactly, and it PRINTS on every run. The output panel is the case it exists for --
    its 24 V return is chopped by ten stepper drivers and it keeps that off the audio
    reference on purpose, intending the two to meet "at the instrument's star point".
    Turning that into a build failure would be wrong; letting it pass in silence would
    be worse, because a star point that is documented and does not exist is still an
    open return. The board states the claim, the check repeats it out loud, and whoever
    reads the build output can go and check that the star point is real.
    """
    txt = open(path, encoding="utf-8").read()
    of_net, by_part = {}, {}
    for blk in re.finditer(r'\(net\s+\(code \d+\)\s+\(name "([^"]+)"\).*?'
                           r'(?=\(net\s+\(code|\Z)', txt, re.S):
        for ref, _pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)',
                                    blk.group(0)):
            of_net.setdefault(blk.group(1), set()).add(ref)
            by_part.setdefault(ref, set()).add(blk.group(1))
    grounds = sorted(n for n in of_net
                     if re.fullmatch(r"(GND|VSS|[A-Z0-9]+_GND|[AD]GND)", n))
    if len(grounds) < 2:
        return len(grounds)
    par = {g: g for g in grounds}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for nets in by_part.values():
        touched = [n for n in nets if n in par]
        for other in touched[1:]:
            par[find(other)] = find(touched[0])
    groups = {}
    for g in grounds:
        groups.setdefault(find(g), []).append(g)
    if len(groups) != 1:
        shape = " | ".join("+".join(sorted(v)) for v in sorted(
            groups.values(), key=lambda v: sorted(v)))
        if declared_split and declared_split.get("shape") == shape:
            print("  !! %s: return nets DELIBERATELY SPLIT (%s) -- %s"
                  % (os.path.basename(path), shape, declared_split["why"]))
            return len(grounds)
        raise AssertionError(
            "%s: the return nets do not all meet -- %s. Each group is internally "
            "connected, so DRC, the router and the ratsnest will all be silent and the "
            "board will not work. Join them with a net tie or a 0R (a component with a "
            "pin on each), or make them one net."
            % (path, " | ".join("+".join(sorted(v)) for v in groups.values())))
    return len(grounds)


def classify_violations(drc_json, declared):
    """Split DRC violations into the ones a board DECLARES and the rest.

    ⚠ A COUNT IS NOT A CHECK, AND THIS EXISTS BECAUSE I PROVED THAT ON MYSELF. The
    optical board declares twenty courtyard overlaps -- an emitter between its own two
    photodiodes, ten times -- and for weeks the pipeline reported "20 violations" and
    everyone, including me, read that as "the expected ones". Then a hand placement put
    a capacitor across the MCU's courtyard and two test pads, the report said 23, and
    the only reason it was caught was that somebody happened to list them.

    THE DECLARATION IS BY SHAPE, NOT BY NUMBER. `declared` is a predicate taking the
    sorted pair of footprint references; a violation it accepts is expected however many
    there are, and a violation it rejects is a fault even if the total is unchanged. A
    twenty-first triplet overlap is fine; a first C112/U6 overlap is not, and counting
    cannot tell them apart.
    """
    import re as _re
    ok, bad = [], []
    for v in drc_json.get("violations", []):
        refs = tuple(sorted(_re.sub(r"^Footprint ", "", i.get("description", ""))
                            for i in v.get("items", [])))
        (ok if declared(v.get("type"), refs) else bad).append((v.get("type"), refs))
    return ok, bad


def no_orphan_pins(path):
    """A net with exactly ONE pin is a pin wired to nothing. Say so, unless it is
    explicitly named as a no-connect.

    ⚠ THIS CHECK HAS NOW FOUND THE SAME BOARD-KILLING FAULT ON TWO BOARDS, and the
    second time only because somebody thought to run it on the rest of the fleet.

    The optical board's SWDIO and SWCLK reached the MCU and stopped. So did the lever
    board's -- and that one had no USB, no USART and no BOOT0 either, so with only
    +24V/CAN_H/CAN_L/GND reaching a connector there was no way to get firmware onto it
    at all. Eight to ten of them, marked finished, with fab packages built.

    Layout DROPS a single-pad net as unplaceable, so it never reaches the board; DRC
    then has nothing to compare and reports a clean board. The intent survives in a
    comment or a BOM row while the implementation quietly does not exist. Only counting
    the pins finds it.

    The exemption is by NAME and deliberately narrow: a net whose name says NC, or
    SPARE, or matches <REF>_NC_<pin>, is a documented no-connect. Everything else with
    one pin is a fault.

    ⚠ AND IT WAS NOT AS NARROW AS THAT SENTENCE CLAIMED. The pattern carried a bare
    `NC_` alternative matching ANYWHERE in a name, so SYNC_OUT, ENC_A, FUNC_SEL and
    INC_PIN were all silently excused -- ordinary signal names, and the failure mode is
    a pin wired to nothing that this check reports as fine. Nothing on the fleet hit it:
    all 143 exempted nets today are genuine no-connects, so this is a latent hole rather
    than a bug that bit, which is exactly when it is cheap to close.

    Now NC/SPARE/NOT_CONNECTED must be a whole underscore-delimited TOKEN. Verified
    against every netlist in the fleet before and after: the same 143 nets are exempt,
    and the four names above are no longer. An exemption list that quietly grows is
    worse than no exemption, because the check keeps reporting success.
    """
    txt = open(path, encoding="utf-8").read()
    bad = []
    for blk in re.finditer(r'\(net\s+\(code \d+\)\s+\(name "([^"]+)"\).*?'
                           r'(?=\(net\s+\(code|\Z)', txt, re.S):
        nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk.group(0))
        name = blk.group(1)
        if len(nodes) == 1 and not re.search(r"(^|_)(NC|SPARE|NOT_CONNECTED)(_|$)",
                                             name, re.I):
            bad.append("%s (%s.%s)" % (name, nodes[0][0], nodes[0][1]))
    if bad:
        raise AssertionError(
            "%s: %d net(s) reach exactly one pin, i.e. a pin wired to nothing -- %s. "
            "Layout drops these as unplaceable and DRC then sees a clean board, so "
            "nothing downstream can find them. If a pin is meant to be unconnected, "
            "name the net so it says so."
            % (path, len(bad), ", ".join(bad)))
    return True

