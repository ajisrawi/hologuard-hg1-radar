"""Thin helper layer over KiCad 10 pcbnew for scripted board generation.

Coordinates passed to these helpers are in the radar frame: mm, origin at
the board centre, +y UP (elevation). They are mapped to KiCad's page frame
(+y down) with the board centre at (OX, OY).
"""
import math
import os

import pcbnew

FPLIB = os.environ.get("KICAD_FPLIB", r"C:/Program Files/KiCad/10.0/share/kicad/footprints")
OX, OY = 150.0, 130.0


def V(x, y):
    return pcbnew.VECTOR2I_MM(OX + x, OY - y)


def stackup_sexpr(stack, mask_t=0.01):
    """KiCad (stackup ...) block for a stack from hg1_params.STACKS: copper per layer plus the
    dielectric gaps between them (several materials in one gap become KiCad sub-layers)."""
    T3, T4 = "\t" * 3, "\t" * 4
    n = len(stack["cu"])
    cu_names = ["F.Cu"] + [f"In{k}.Cu" for k in range(1, n - 1)] + ["B.Cu"]
    out = ["\t\t(stackup"]

    def layer(name, typ, props=""):
        out.append(f'{T3}(layer "{name}"\n{T4}(type "{typ}"){props}\n{T3})')

    layer("F.SilkS", "Top Silk Screen")
    layer("F.Paste", "Top Solder Paste")
    layer("F.Mask", "Top Solder Mask", f"\n{T4}(thickness {mask_t})")
    for i, name in enumerate(cu_names):
        layer(name, "copper", f"\n{T4}(thickness {stack['cu'][i]})")
        if i < n - 1:
            typ, subs = stack["gaps"][i]
            parts = [f"\n{T4}(thickness {t})\n{T4}(material \"{m}\")\n{T4}(epsilon_r {er})\n{T4}(loss_tangent {td})"
                     for m, t, er, td in subs]
            layer(f"dielectric {i + 1}", typ, " addsublayer".join(parts))
    layer("B.Mask", "Bottom Solder Mask", f"\n{T4}(thickness {mask_t})")
    layer("B.Paste", "Bottom Solder Paste")
    layer("B.SilkS", "Bottom Silk Screen")
    out.append(f'{T3}(copper_finish "{stack["finish"]}")\n{T3}(dielectric_constraints yes)\n\t\t)')
    return "\n".join(out)


def inject_stackup(path, stack, mask_t=0.01):
    """Write the physical stack-up into a saved .kicad_pcb (replacing any existing one).
    The pcbnew Python API cannot build a BOARD_STACKUP, so this edits the file text."""
    import re
    txt = open(path, encoding="utf-8").read()
    txt = re.sub(r"\n\t\t\(stackup\n.*?\n\t\t\)(?=\n)", "", txt, flags=re.S)
    txt = txt.replace("\n\t(setup\n", "\n\t(setup\n" + stackup_sexpr(stack, mask_t) + "\n", 1)
    open(path, "w", encoding="utf-8").write(txt)


class Board:
    def __init__(self, copper_layers, thickness_mm):
        self.b = pcbnew.BOARD()
        self.b.SetCopperLayerCount(copper_layers)
        ds = self.b.GetDesignSettings()
        ds.SetBoardThickness(pcbnew.FromMM(thickness_mm))
        # HDI / RF fab rules (laser-drilled 0.2 mm vias, 75 um lines)
        ds.m_MinThroughDrill = pcbnew.FromMM(0.15)
        ds.m_ViasMinSize = pcbnew.FromMM(0.35)
        ds.m_TrackMinWidth = pcbnew.FromMM(0.075)
        ds.m_MinClearance = pcbnew.FromMM(0.075)
        ds.m_HoleClearance = pcbnew.FromMM(0.15)
        ds.m_HoleToHoleMin = pcbnew.FromMM(0.2)
        ds.m_SolderMaskMinWidth = 0
        try:
            nc = ds.m_NetSettings.GetDefaultNetclass()
            nc.SetClearance(pcbnew.FromMM(0.1))
            nc.SetTrackWidth(pcbnew.FromMM(0.15))
            nc.SetViaDiameter(pcbnew.FromMM(0.45))
            nc.SetViaDrill(pcbnew.FromMM(0.2))
        except Exception as exc:  # API differs between KiCad releases
            print("netclass defaults not set:", exc)
        self.nets = {}
        self.refcount = {}

    # ------------------------------------------------------------ basics
    def L(self, name):
        # KiCad 10 GetLayerID() no longer resolves legacy names (F.SilkS,
        # Dwgs.User ...); use the pcbnew layer constants instead.
        lid = getattr(pcbnew, name.replace(".", "_"), None)
        if lid is None:
            lid = self.b.GetLayerID(name)
        if lid < 0:
            raise ValueError(f"unknown layer {name}")
        return lid

    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            n.thisown = False
            self.nets[name] = n
        return self.nets[name]

    def ref(self, prefix):
        self.refcount[prefix] = self.refcount.get(prefix, 0) + 1
        return f"{prefix}{self.refcount[prefix]}"

    # ---------------------------------------------------------- graphics
    def rect(self, layer, cx, cy, w, h, filled=True, width=0.1, net=None):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_RECTANGLE)
        s.SetStart(V(cx - w / 2, cy + h / 2))
        s.SetEnd(V(cx + w / 2, cy - h / 2))
        s.SetFilled(filled)
        s.SetWidth(pcbnew.FromMM(0 if filled else width))
        s.SetLayer(self.L(layer) if isinstance(layer, str) else layer)
        if net:
            s.SetNet(self.net(net))
        self.b.Add(s)
        s.thisown = False
        return s

    def circle(self, layer, cx, cy, r, width=0.15, filled=False):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetCenter(V(cx, cy))
        s.SetEnd(V(cx + r, cy))
        s.SetFilled(filled)
        s.SetWidth(pcbnew.FromMM(width))
        s.SetLayer(self.L(layer))
        self.b.Add(s)
        s.thisown = False

    def polyline(self, layer, pts, width=0.15, closed=False):
        pts = list(pts) + ([pts[0]] if closed else [])
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            s = pcbnew.PCB_SHAPE(self.b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x1, y1))
            s.SetEnd(V(x2, y2))
            s.SetWidth(pcbnew.FromMM(width))
            s.SetLayer(self.L(layer))
            self.b.Add(s)
            s.thisown = False

    def text(self, layer, s, x, y, size=1.5, mirrored=False, thickness=0.2):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(V(x, y))
        t.SetLayer(self.L(layer))
        t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
        t.SetTextThickness(pcbnew.FromMM(thickness))
        if mirrored:
            t.SetMirrored(True)
        self.b.Add(t)
        t.thisown = False

    def outline_rounded(self, w, h, r, seg=10):
        pts = []
        for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                           (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
            for k in range(seg + 1):
                a = math.radians(a0 + 90 * k / seg)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.polyline("Edge.Cuts", pts, 0.1, closed=True)
        return pts

    @staticmethod
    def rounded_pts(w, h, r, inset=0.0, seg=6):
        w, h, r = w - 2 * inset, h - 2 * inset, max(r - inset, 0.1)
        pts = []
        for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                           (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
            for k in range(seg + 1):
                a = math.radians(a0 + 90 * k / seg)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    # ------------------------------------------------------------ copper
    def zone(self, layer, net, pts, holes=(), priority=0, clearance=0.2, name=""):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(self.L(layer))
        z.SetNet(self.net(net))
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(pcbnew.FromMM(clearance))
        z.SetMinThickness(pcbnew.FromMM(0.12))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        if name:
            z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(V(x, y))
        for hole in holes:
            hidx = ol.NewHole()
            for x, y in hole:
                ol.Append(V(x, y), 0, hidx)
        self.b.Add(z)
        z.thisown = False
        return z

    def track(self, layer, pts, width, net=None):
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V(x1, y1))
            t.SetEnd(V(x2, y2))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(self.L(layer))
            if net:
                t.SetNet(self.net(net))
            self.b.Add(t)
            t.thisown = False

    def via(self, x, y, net=None, drill=0.2, dia=0.45):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(x, y))
        v.SetDrill(pcbnew.FromMM(drill))
        v.SetWidth(pcbnew.FromMM(dia))
        if net:
            v.SetNet(self.net(net))
        self.b.Add(v)
        v.thisown = False
        return v

    def bvia(self, x, y, net, top, bottom, drill=0.15, dia=0.35):
        """Blind via between two named copper layers (laser-drilled, HDI)."""
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(x, y))
        v.SetViaType(pcbnew.VIATYPE_BLIND)
        v.SetLayerPair(self.L(top), self.L(bottom))
        v.SetDrill(pcbnew.FromMM(drill))
        v.SetWidth(pcbnew.FromMM(dia))
        v.SetNet(self.net(net))
        self.b.Add(v)
        v.thisown = False
        return v

    def fence(self, pts, net, top, bottom, drill=0.2, dia=0.4, margin=0.25):
        """Blind-via fence at explicit points (radar frame). A point is skipped when a via, a
        drilled pad, or copper on the layers the via spans (top..bottom) is within `margin` mm,
        so routing on layers below the fence does not punch gaps in it."""
        order = ["F.Cu"] + [f"In{k}.Cu" for k in range(1, 31)] + ["B.Cu"]
        span = {self.L(n) for n in order[order.index(top):order.index(bottom) + 1]}
        r = dia / 2 + margin
        obs, segs = [], []

        def box(bb):
            x0, y1 = pcbnew.ToMM(bb.GetLeft()) - OX, OY - pcbnew.ToMM(bb.GetTop())
            x1, y0 = pcbnew.ToMM(bb.GetRight()) - OX, OY - pcbnew.ToMM(bb.GetBottom())
            obs.append((x0 - r, y0 - r, x1 + r, y1 + r))

        for f in self.b.GetFootprints():
            for p in f.Pads():
                if p.HasHole() or any(p.IsOnLayer(lay) for lay in span):
                    box(p.GetBoundingBox())
        for d in self.b.GetDrawings():
            if d.GetLayer() in span:
                box(d.GetBoundingBox())
        for t_ in self.b.GetTracks():
            if isinstance(t_, pcbnew.PCB_VIA):
                box(t_.GetBoundingBox())
            elif t_.GetLayer() in span:
                a, b = t_.GetStart(), t_.GetEnd()
                segs.append(((pcbnew.ToMM(a.x) - OX, OY - pcbnew.ToMM(a.y)),
                             (pcbnew.ToMM(b.x) - OX, OY - pcbnew.ToMM(b.y)),
                             pcbnew.ToMM(t_.GetWidth()) / 2 + r))

        def seg_d(px, py, a, b):
            (ax, ay), (bx, by) = a, b
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            u = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
            return math.hypot(px - (ax + u * dx), py - (ay + u * dy))

        n, skipped = 0, 0
        for x, y in dict.fromkeys((round(px, 3), round(py, 3)) for px, py in pts):
            if any(a <= x <= c and b <= y <= d for a, b, c, d in obs) or \
                    any(seg_d(x, y, a, b) <= w for a, b, w in segs):
                skipped += 1
                continue
            self.bvia(x, y, net, top, bottom, drill, dia)
            obs.append((x - 2 * r + margin, y - 2 * r + margin, x + 2 * r - margin, y + 2 * r - margin))
            n += 1
        return n, skipped

    def stitch(self, net, pitch, keep, margin=0.6, dia=0.45, drill=0.2, region=None):
        """Drop through-vias on a grid wherever nothing else is within
        `margin` mm (pads, tracks, vias, copper graphics on any layer)."""
        obs = []   # (xmin, ymin, xmax, ymax) in radar frame, inflated
        r = dia / 2 + margin

        def add_box(bb, infl):
            x0, y1 = pcbnew.ToMM(bb.GetLeft()) - OX, OY - pcbnew.ToMM(bb.GetTop())
            x1, y0 = pcbnew.ToMM(bb.GetRight()) - OX, OY - pcbnew.ToMM(bb.GetBottom())
            obs.append((x0 - infl, y0 - infl, x1 + infl, y1 + infl))

        for f in self.b.GetFootprints():
            for p in f.Pads():
                add_box(p.GetBoundingBox(), r)
        for d in self.b.GetDrawings():
            if d.GetLayer() not in (pcbnew.Edge_Cuts,) and pcbnew.IsCopperLayer(d.GetLayer()):
                add_box(d.GetBoundingBox(), r)
        segs = []
        for t_ in self.b.GetTracks():
            if isinstance(t_, pcbnew.PCB_VIA):
                add_box(t_.GetBoundingBox(), r)
            else:
                a, b = t_.GetStart(), t_.GetEnd()
                segs.append(((pcbnew.ToMM(a.x) - OX, OY - pcbnew.ToMM(a.y)),
                             (pcbnew.ToMM(b.x) - OX, OY - pcbnew.ToMM(b.y)),
                             pcbnew.ToMM(t_.GetWidth()) / 2 + r))
        for hole in keep:          # extra keep-out polygons' bounding boxes
            xs, ys = [p[0] for p in hole], [p[1] for p in hole]
            obs.append((min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r))

        def seg_d(px, py, a, b):
            (ax, ay), (bx, by) = a, b
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            u = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
            return math.hypot(px - (ax + u * dx), py - (ay + u * dy))

        x0, y0, x1, y1 = region
        n = 0
        y = y0
        while y <= y1:
            x = x0
            while x <= x1:
                ok = not any(a <= x <= c and b <= y <= d for a, b, c, d in obs)
                if ok:
                    ok = all(seg_d(x, y, a, b) > w for a, b, w in segs)
                if ok:
                    self.via(x, y, net, drill, dia)
                    n += 1
                x += pitch
            y += pitch
        return n

    # -------------------------------------------------------- footprints
    def fp(self, lib, name, ref, value, x, y, rot=0.0, bottom=False, pad_net=None):
        f = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
        if f is None:
            raise RuntimeError(f"footprint not found: {lib}:{name}")
        f.SetReference(ref)
        f.SetValue(value)
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        f.SetPosition(V(x, y))
        f.SetOrientationDegrees(rot)
        self.b.Add(f)
        f.thisown = False
        if bottom:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if pad_net:
            for p in f.Pads():
                p.SetNet(self.net(pad_net))
        return f

    def custom_fp(self, ref, value, x, y, pads, courtyard=None, bottom=False, fab_text=True, fpid=None):
        """pads: list of dict(num, x, y, w, h, shape='rect'|'circle', drill=None, net=None)."""
        f = pcbnew.FOOTPRINT(self.b)
        f.SetReference(ref)
        f.SetValue(value)
        if fpid:
            f.SetFPID(pcbnew.LIB_ID("HG1", fpid))
        f.SetPosition(V(x, y))
        for pd in pads:
            p = pcbnew.PAD(f)
            shape = pd.get("shape", "rect")
            p.SetShape(pcbnew.PAD_SHAPE_CIRCLE if shape == "circle" else pcbnew.PAD_SHAPE_RECTANGLE)
            p.SetSize(pcbnew.VECTOR2I_MM(pd["w"], pd["h"]))
            if pd.get("drill"):
                p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                p.SetDrillSize(pcbnew.VECTOR2I_MM(pd["drill"], pd["drill"]))
                p.SetLayerSet(p.PTHMask())
            else:
                p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                p.SetLayerSet(p.SMDMask())
            p.SetNumber(str(pd["num"]))
            p.SetPosition(V(x + pd["x"], y + pd["y"]))
            if pd.get("net"):
                p.SetNet(self.net(pd["net"]))
            f.Add(p)
            p.thisown = False
        if courtyard:
            cw, ch = courtyard
            for lay in ("F.Fab", "F.CrtYd"):  # flipped to B.* with the footprint
                s = pcbnew.PCB_SHAPE(f)
                s.SetShape(pcbnew.SHAPE_T_RECTANGLE)
                s.SetStart(V(x - cw / 2, y + ch / 2))
                s.SetEnd(V(x + cw / 2, y - ch / 2))
                s.SetWidth(pcbnew.FromMM(0.1))
                s.SetLayer(self.L(lay))
                f.Add(s)
                s.thisown = False
        self.b.Add(f)
        f.thisown = False
        if bottom:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        return f

    @staticmethod
    def pad_xy(p):
        pos = p.GetPosition()
        return pcbnew.ToMM(pos.x) - OX, OY - pcbnew.ToMM(pos.y)

    def nearest_pad(self, f, x, y, used, side=None, numeric=True):
        best, bd = None, 1e9
        for p in f.Pads():
            num = p.GetNumber()
            if num in used or (numeric and not num.isdigit()):
                continue
            px, py = self.pad_xy(p)
            if side == "left" and px > self.pad_xy_center(f)[0] - 1:
                continue
            if side == "right" and px < self.pad_xy_center(f)[0] + 1:
                continue
            if side == "top" and py < self.pad_xy_center(f)[1] + 1:
                continue
            if side == "bottom" and py > self.pad_xy_center(f)[1] - 1:
                continue
            d = math.hypot(px - x, py - y)
            if d < bd:
                best, bd = p, d
        if best is not None:
            used.add(best.GetNumber())
        return best

    @staticmethod
    def pad_xy_center(f):
        pos = f.GetPosition()
        return pcbnew.ToMM(pos.x) - OX, OY - pcbnew.ToMM(pos.y)

    def connect(self, layer, f, pad, pts, width, net):
        pad.SetNet(self.net(net))
        px, py = self.pad_xy(pad)
        self.track(layer, list(pts) + [(px, py)], width, net)

    # ------------------------------------------------- schematic -> PCB sync
    def apply_netlist(self, xml_path, sheetfile, stage_x, stage_y):
        """Scripted 'Update PCB from Schematic': link footprints to symbols, copy
        values and pad nets from the KiCad XML netlist, and stage footprints of
        not-yet-placed symbols on a grid beside the board (as KiCad's update does)."""
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        pin_net = {}
        for n in root.find("nets"):
            # incl. KiCad's unconnected-(...) nets; KiCad stores '/' escaped in net names
            name = n.get("name").replace("/", "{slash}")
            for node in n.findall("node"):
                pin_net[(node.get("ref"), node.get("pin"))] = name
        stats = dict(linked=0, staged=0, pads=0)
        sx, sy, row_h = stage_x, stage_y, 0.0
        for c in root.find("components"):
            ref, fpname = c.get("ref"), (c.findtext("footprint") or "")
            if ref.startswith("#"):
                continue
            if not fpname and self.b.FindFootprintByReference(ref) is None:
                continue                       # not on the board (e.g. antenna element symbols)
            ts = c.find("tstamps")
            uid = (ts.text if ts is not None else c.findtext("tstamp") or "").split()[0]
            f = self.b.FindFootprintByReference(ref)
            if f is None:
                lib, name = fpname.split(":")
                f = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
                if f is None:
                    continue
                f.SetReference(ref)
                f.SetFPID(pcbnew.LIB_ID(lib, name))
                self.b.Add(f)
                f.thisown = False
                bb = f.GetBoundingBox(False)
                w, h = pcbnew.ToMM(bb.GetWidth()) + 4.0, pcbnew.ToMM(bb.GetHeight()) + 4.0
                if sx + w > stage_x + 120:
                    sx, sy, row_h = stage_x, sy - row_h, 0.0
                f.SetPosition(V(sx + w / 2, sy - h / 2))
                sx += w
                row_h = max(row_h, h)
                stats["staged"] += 1
            f.SetValue(c.findtext("value") or f.GetValue())
            props = {pp.get("name") for pp in c.findall("property")}
            attrs = f.GetAttributes()
            if "exclude_from_bom" in props:
                attrs |= pcbnew.FP_EXCLUDE_FROM_BOM
            else:
                attrs &= ~pcbnew.FP_EXCLUDE_FROM_BOM
            if "dnp" in props:
                attrs |= pcbnew.FP_DNP
            f.SetAttributes(attrs)
            try:
                f.SetPath(pcbnew.KIID_PATH("/" + uid))
                f.SetSheetname("/")
                f.SetSheetfile(sheetfile)
            except Exception:
                pass
            stats["linked"] += 1
            for p in f.Pads():
                net = pin_net.get((ref, p.GetNumber()))
                if net:
                    p.SetNet(self.net(net))
                    stats["pads"] += 1
        return stats

    # -------------------------------------------------------------- save
    def export_custom_footprints(self, libdir):
        """Write the generated (non-library) footprints to the project HG1.pretty."""
        os.makedirs(libdir, exist_ok=True)
        n = 0
        for f in self.b.GetFootprints():
            fid = f.GetFPID()
            if fid.GetLibNickname() == "HG1":
                try:
                    g = pcbnew.FOOTPRINT(f)
                    g.SetPosition(pcbnew.VECTOR2I(0, 0))
                    if g.IsFlipped():
                        g.Flip(g.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
                    g.SetOrientationDegrees(0)
                    pcbnew.FootprintSave(libdir, g)
                    n += 1
                except Exception as exc:
                    print("   footprint export skipped:", exc)
        return n

    def save(self, path):
        # NOTE: pcbnew.ZONE_FILLER segfaults in KiCad 10.0.3 when vias sit
        # inside zones; zones are refilled afterwards with
        # `kicad-cli pcb drc --refill-zones --save-board` (see generate_boards.py).
        self.b.Save(path)
