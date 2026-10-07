"""HoloGuard HG-1 product renders (Blender 5.x, Cycles).

Imports the FreeCAD part meshes (mech/out/*.stl) and the KiCad board models
(board/glb/*.glb), assembles them in the design frame and renders:
  render/HG1_hero.png      3/4 front on pole mount
  render/HG1_rear.png      rear 3/4: convection fins, tilt bracket, M12 I/O
  render/HG1_exploded.png  exploded assembly
  render/HG1_xray.png      transparent radome, 120x80 deg staring volume, track

Run:
  blender -b --factory-startup -P mech/render_blender.py -- [--quick] [--only NAME]
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MO = os.path.join(ROOT, "mech", "out")
GLB = os.path.join(ROOT, "board", "glb")
OUT = os.path.join(ROOT, "render")
os.makedirs(OUT, exist_ok=True)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
QUICK = "--quick" in argv
ONLY = argv[argv.index("--only") + 1] if "--only" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
MM = 0.001


# ------------------------------------------------------------------ materials
def principled(name, base, metal=0.0, rough=0.5, coat=0.0, trans=0.0, ior=1.45,
               emis=None, emis_str=0.0, alpha=1.0, aniso=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if trans:
        b.inputs["Transmission Weight"].default_value = trans
        b.inputs["IOR"].default_value = ior
    if emis:
        b.inputs["Emission Color"].default_value = (*emis, 1.0)
        b.inputs["Emission Strength"].default_value = emis_str
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
    if aniso:
        b.inputs["Anisotropic"].default_value = aniso
    return m


def anodized(name, base, rough):
    """Anodised cast aluminium with a fine bead-blast micro-texture."""
    m = principled(name, base, metal=1.0, rough=rough, coat=0.15)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2200.0
    noise.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


M = {
    "housing": anodized("Housing anodised graphite", (0.040, 0.043, 0.047), 0.42),
    "radome": principled("Radome PC/ABS RAL7035", (0.42, 0.43, 0.42), rough=0.6),
    "logo": principled("Logo", (0.012, 0.11, 0.16), rough=0.35, coat=0.3),
    "screws": principled("Stainless", (0.78, 0.78, 0.80), metal=1.0, rough=0.22),
    "connectors": principled("Nickel", (0.72, 0.72, 0.74), metal=1.0, rough=0.28),
    "plugs": principled("Black overmould", (0.018, 0.018, 0.02), rough=0.62),
    "bracket": anodized("Bracket anodised", (0.055, 0.058, 0.062), 0.48),
    "bracket_hw": principled("Black knobs", (0.012, 0.012, 0.013), rough=0.5),
    "pole": principled("Galvanised", (0.42, 0.43, 0.44), metal=1.0, rough=0.42),
    "ant_pcb": principled("RO4003C + mask", (0.018, 0.10, 0.045), rough=0.32, coat=0.35),
    "ant_copper": principled("ENEPIG gold", (1.0, 0.72, 0.32), metal=1.0, rough=0.22),
    "gnss": principled("Ceramic", (0.66, 0.62, 0.53), rough=0.4),
    "alu": principled("Bare aluminium", (0.86, 0.86, 0.88), metal=1.0, rough=0.33),
    "absorber": principled("Absorber foam", (0.02, 0.02, 0.022), rough=0.95),
    "frame": principled("Shield frame", (0.80, 0.80, 0.82), metal=1.0, rough=0.42),
    "backdrop": principled("Backdrop", (0.16, 0.17, 0.185), rough=0.8),
    "glow": principled("Hologram", (0.0, 0.0, 0.0), rough=1.0, emis=(0.05, 0.75, 1.0), emis_str=3.0),
    "glow_soft": principled("Hologram soft", (0.0, 0.0, 0.0), rough=1.0, emis=(0.05, 0.55, 1.0),
                            emis_str=0.9),
    "track": principled("Track", (0.0, 0.0, 0.0), rough=1.0, emis=(1.0, 0.35, 0.05), emis_str=12.0),
    "drone": principled("Drone body", (0.75, 0.76, 0.78), rough=0.35),
    "rotor": principled("Rotor", (0.02, 0.02, 0.02), rough=0.5),
}
GLASS = principled("Radome x-ray", (0.75, 0.88, 0.95), rough=0.08, trans=1.0, ior=1.35)

# ------------------------------------------------------------------ assembly
root = bpy.data.objects.new("HG1", None)
sc.collection.objects.link(root)
root.rotation_euler = (math.pi / 2, 0.0, 0.0)     # model +Y -> world up, boresight -> world -Y


def activate(o):
    for s in bpy.context.selected_objects:
        s.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def stl(name, mat, smooth=35):
    path = os.path.join(MO, name + ".stl")
    if not os.path.exists(path):
        return None
    bpy.ops.wm.stl_import(filepath=path, global_scale=MM)
    o = bpy.context.selected_objects[0]
    o.name = name
    o.data.materials.append(mat)
    activate(o)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
    except Exception:
        pass
    o.parent = root
    return o


def glb(fname, name, loc, rot):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(GLB, fname))
    new = [o for o in bpy.data.objects if o not in before]
    e = bpy.data.objects.new(name, None)
    sc.collection.objects.link(e)
    for o in new:
        if o.parent is None:
            o.parent = e
    e.parent = root
    e.location = loc
    e.rotation_euler = rot
    return e, new


P = {}
for n, m in (("housing", "housing"), ("radome", "radome"), ("radome_screws", "screws"), ("logo", "logo"),
             ("connectors", "connectors"), ("m12_plugs", "plugs"), ("bracket", "bracket"),
             ("bracket_hw", "bracket_hw"), ("pole", "pole"), ("ant_pcb", "ant_pcb"),
             ("ant_copper", "ant_copper"), ("gnss_patch", "gnss"), ("iso_fence", "alu"),
             ("absorber", "absorber"), ("shield_frame", "frame")):
    P[n] = stl(n, M[m])

# DSP faces the rear wall: rotate 180 deg about Y, F side at Z = 33.5 mm
P["dsp"], _ = glb("HG1-DSP.glb", "dsp_board", (0.0, 0.020, 0.0351), (0.0, math.pi, 0.0))
# PWR lies on the floor, component side up (+Y), M12 axis at Z = 29 mm
P["pwr"], _ = glb("HG1-PWR.glb", "pwr_board", (0.0, -0.0976, 0.029), (-math.pi / 2, 0.0, 0.0))

# ------------------------------------------------------------------ studio
world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.20, 0.22, 0.25, 1.0)
bg.inputs["Strength"].default_value = 0.12

FLOOR_Z = -0.33
bm = bmesh.new()
prof = [(-3.0, FLOOR_Z)]
for k in range(13):
    a = math.radians(90.0 * k / 12.0)
    prof.append((1.0 + 0.8 * math.sin(a), FLOOR_Z + 0.8 * (1 - math.cos(a))))
prof.append((1.8, 3.0))
rows = []
for x in (-4.0, 4.0):
    rows.append([bm.verts.new((x, y, z)) for (y, z) in prof])
for i in range(len(prof) - 1):
    bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
me = bpy.data.meshes.new("cyclorama")
bm.to_mesh(me)
cyc = bpy.data.objects.new("cyclorama", me)
sc.collection.objects.link(cyc)
cyc.data.materials.append(M["backdrop"])
for f in cyc.data.polygons:
    f.use_smooth = True


def area(name, loc, size, energy, color=(1, 1, 1), target=(0, 0, 0)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.size = size
    ld.energy = energy
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    d = Vector(target) - Vector(loc)
    lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return lo


LIGHTS = [area("key", (-1.1, -1.3, 1.1), 1.4, 95.0, (1.0, 0.97, 0.93)),
          area("fill", (1.4, -0.9, 0.3), 1.8, 26.0, (0.85, 0.92, 1.0)),
          area("rim", (0.6, 1.0, 1.0), 0.9, 80.0, (0.9, 0.95, 1.0)),
          area("top", (0.0, -0.2, 1.6), 1.2, 22.0)]

cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def aim(loc, target, lens=55.0, fstop=None, focus=None):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = lens
    cam_data.dof.use_dof = fstop is not None
    if fstop:
        cam_data.dof.aperture_fstop = fstop
        cam_data.dof.focus_distance = focus or d.length


# ------------------------------------------------------------------ render setup
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 24 if QUICK else 160
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 8
sc.render.resolution_x = 960 if QUICK else 2000
sc.render.resolution_y = 600 if QUICK else 1250
sc.render.image_settings.file_format = "PNG"
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass


def shoot(name):
    if ONLY and ONLY != name:
        return
    sc.render.filepath = os.path.join(OUT, f"HG1_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath, flush=True)


def show(names, state):
    for n in names:
        o = P.get(n)
        if o is None:
            continue
        o.hide_render = not state
        for c in o.children_recursive:
            c.hide_render = not state


# 1. hero ---------------------------------------------------------------
aim((-0.50, -0.80, 0.16), (0.0, -0.01, -0.035), lens=58, fstop=4.0)
shoot("hero")

# 2. rear ---------------------------------------------------------------
aim((0.62, 0.66, 0.24), (0.0, 0.03, -0.04), lens=55, fstop=4.0)
shoot("rear")

# 3. exploded -----------------------------------------------------------
show(["pole", "bracket", "bracket_hw", "m12_plugs"], False)
EXPLODE = {"radome": 205, "radome_screws": 205, "logo": 205, "iso_fence": 150, "absorber": 150,
           "ant_pcb": 120, "ant_copper": 120, "gnss_patch": 120, "shield_frame": 70, "dsp": 30}
for n in ("radome", "radome_screws", "logo"):      # radome slid sideways so the array shows
    P[n].location.x += 0.175
for n, dz in EXPLODE.items():
    if P.get(n) is not None:
        P[n].location.z += dz * MM
P["pwr"].location.y -= 0.050
aim((-0.62, -0.78, 0.30), (0.07, -0.12, -0.02), lens=42, fstop=8.0)
shoot("exploded")
for n in ("radome", "radome_screws", "logo"):
    P[n].location.x -= 0.175
for n, dz in EXPLODE.items():
    if P.get(n) is not None:
        P[n].location.z -= dz * MM
P["pwr"].location.y += 0.050
show(["pole", "bracket", "bracket_hw", "m12_plugs"], True)

# 4. x-ray / holographic staring volume ----------------------------------
P["radome"].data.materials[0] = GLASS
P["logo"].hide_render = True
cyc.hide_render = True
bg.inputs["Color"].default_value = (0.004, 0.008, 0.016, 1.0)
bg.inputs["Strength"].default_value = 1.0
for lo in LIGHTS:
    lo.data.energy *= 0.45

apex = Vector((0.0, -0.058, 0.0))


def tube(points, mat, r):
    cu = bpy.data.curves.new("c", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, q in zip(sp.points, points):
        p.co = (*q, 1.0)
    ob = bpy.data.objects.new("holo", cu)
    sc.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def dirv(az, el):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


RANGE = 0.42
for az in range(-60, 61, 15):                         # meridians of the staring volume
    pts = [apex + dirv(az, el) * RANGE for el in range(-40, 41, 4)]
    tube(pts, M["glow_soft"] if abs(az) != 60 else M["glow"], 0.00035 if abs(az) != 60 else 0.0007)
for el in range(-40, 41, 10):                         # parallels
    pts = [apex + dirv(az, el) * RANGE for az in range(-60, 61, 3)]
    tube(pts, M["glow_soft"] if abs(el) != 40 else M["glow"], 0.00035 if abs(el) != 40 else 0.0007)
for az, el in ((-60, -40), (-60, 40), (60, -40), (60, 40)):   # frustum edges
    tube([apex, apex + dirv(az, el) * RANGE], M["glow"], 0.0007)
for rr in (0.14, 0.28):                                 # range rings on the horizon
    tube([apex + dirv(az, 0) * rr for az in range(-60, 61, 3)], M["glow_soft"], 0.00035)

# tracked drone inside the volume + its digital beam
d_az, d_el, d_r = 24.0, 14.0, 0.34
dp = apex + dirv(d_az, d_el) * d_r
body = bpy.data.objects.new("drone", bpy.data.meshes.new("drone"))
sc.collection.objects.link(body)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.scale(bm, vec=(0.022, 0.022, 0.008), verts=bm.verts)
for sx in (-1, 1):
    for sy in (-1, 1):
        g = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=(0.03, 0.003, 0.003), verts=g)
        bmesh.ops.rotate(bm, verts=g, cent=(0, 0, 0),
                         matrix=__import__("mathutils").Matrix.Rotation(math.radians(45 if sx == sy else -45), 3, "Z"))
        bmesh.ops.translate(bm, vec=(sx * 0.0105, sy * 0.0105, 0), verts=g)
bm.to_mesh(body.data)
body.location = dp
body.data.materials.append(M["drone"])
for sx in (-1, 1):
    for sy in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.011, depth=0.0008, location=dp + Vector((sx * 0.021, sy * 0.021, 0.006)))
        bpy.context.active_object.data.materials.append(M["rotor"])
# track box
s = 0.034
c = [dp + Vector((x, y, z)) for x in (-s, s) for y in (-s, s) for z in (-s * 0.6, s * 0.6)]
for i, j in ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)):
    tube([c[i], c[j]], M["track"], 0.0004)
tube([apex, dp], M["track"], 0.0005)
aim((-0.62, -1.05, 0.42), (0.06, -0.22, -0.01), lens=34, fstop=None)
shoot("xray")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "HG1_scene.blend"))
print("DONE", flush=True)
