"""X2D plate-swap robot arm - Blender animation (concept check).

Usage
  * Blender GUI : Scripting tab -> open this file -> Run Script, then press Space.
  * Headless    : blender -b -P x2d_swap_anim.py -- --render OUT_DIR [--step 2]
                  (or `python x2d_swap_anim.py -- ...` with the bpy module)

All dimensions are in metres. Values tagged ASSUME are placeholders until the
real X2D is measured (door sill, tab position, pin position ...).
Coordinates: +X into the printer (door plane at X=0), +Y to the right when
facing the printer, +Z up.  Door hinge is on the LEFT (-Y).
"""
import math, os, sys
import bpy
from mathutils import Vector, Quaternion, Euler

# ------------------------------------------------------------------ params
RISER = 0.20                 # printer/arm/shelf stand on a 20 cm riser (bin sits below)
PW, PD, PH = 0.392, 0.406, 0.478   # X2D outside (web specs)
ZB = 0.093                   # bed surface parked level with door sill (ASSUME)
PLATE = 0.257                # plate square
TAB = 0.015                  # front tab depth (ASSUME, from photo)
TAB_X = 0.045                # tab tip behind door plane (ASSUME)
HOOK_DX = 0.008              # clip hole centre behind tab tip
HOOK_Y = 0.100               # clip on right side of tab (marker stays visible)
TO_REAR = PLATE + TAB - HOOK_DX   # hook -> rear edge = 0.264
PIN_X = TAB_X + PLATE + TAB  # rear locating pins (plate rear edge when seated)
SEATED_HOOK_X = PIN_X - TO_REAR   # = TAB_X + HOOK_DX
OUT_HOOK_X = -0.010 - TO_REAR + 0.0  # plate fully outside on shelf
SHELF_LEN = 0.300
MAG_Z = ZB + 0.130           # fresh plate magazine height above shelf
INSERT_TILT = math.radians(12)

BASE = Vector((-0.110, 0.190, 0.0))   # arm base (from layout study)
L1 = L2 = 0.095              # upper arm / forearm
TOOL = 0.040                 # horizontal tool offset (palletiser style)
PIN = 0.025                  # T-pin length below tool
HS = ZB + 0.040              # shoulder height
FPS = 24

def Z(z):  # local height -> world
    return z + RISER

# ------------------------------------------------------------------ helpers
def clear_scene():
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return
    # GUI: keep the open script, wipe everything else
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                 bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)

MATS = {}
def mat(name, rgba, metal=0.0, rough=0.5, alpha=1.0, emit=0.0):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    if emit:
        b.inputs["Emission Color"].default_value = rgba
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    m.diffuse_color = rgba
    MATS[name] = m
    return m

def box(name, x0, x1, y0, y1, z0, z1, material, parent=None):
    """Axis-aligned box. If parent given, coords are in parent-local space."""
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    if parent:
        o.parent = parent
    return o

def cyl(name, r, h, loc, material, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(material)
    return o

def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_mode = "XYZ"
    return o

def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

class Track:
    """Piece-wise smooth channel: list of (frame, value)."""
    def __init__(self, *keys):
        self.k = list(keys)
    def __call__(self, f):
        k = self.k
        if f <= k[0][0]:
            return k[0][1]
        for (f0, v0), (f1, v1) in zip(k, k[1:]):
            if f0 <= f <= f1:
                t = smooth((f - f0) / (f1 - f0)) if f1 > f0 else 1
                if isinstance(v0, tuple):
                    return tuple(a + (b - a) * t for a, b in zip(v0, v1))
                return v0 + (v1 - v0) * t
        return k[-1][1]

# ------------------------------------------------------------------ scene
def build():
    clear_scene()
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.unit_settings.system = "METRIC"

    M = dict(
        frame=mat("frame", (0.12, 0.12, 0.13, 1), 0.3, 0.4),
        panel=mat("panel", (0.6, 0.65, 0.7, 1), 0, 0.1, alpha=0.12),
        glass=mat("glass", (0.55, 0.75, 0.9, 1), 0, 0.05, alpha=0.18),
        bed=mat("bed", (0.35, 0.36, 0.38, 1), 0.6, 0.35),
        plate=mat("plate", (0.05, 0.05, 0.08, 1), 0.2, 0.35),
        plate2=mat("plate_new", (0.1, 0.12, 0.25, 1), 0.2, 0.35),
        tab=mat("tab", (0.02, 0.02, 0.02, 1), 0.2, 0.5),
        marker=mat("marker", (0.95, 0.95, 0.95, 1)),
        clip=mat("clip", (0.95, 0.35, 0.1, 1), 0, 0.4),
        part=mat("part", (0.95, 0.95, 0.92, 1), 0, 0.5),
        shelf=mat("shelf", (0.2, 0.65, 0.35, 1), 0, 0.5),
        mag=mat("mag", (0.95, 0.75, 0.15, 1), 0, 0.5),
        arm=mat("arm", (0.75, 0.77, 0.8, 1), 0.8, 0.3),
        joint=mat("joint", (0.15, 0.4, 0.85, 1), 0.2, 0.4),
        pin=mat("pin", (0.85, 0.1, 0.4, 1), 0.5, 0.3),
        riser=mat("riser", (0.55, 0.45, 0.35, 1), 0, 0.7),
        bin=mat("bin", (0.7, 0.85, 0.95, 1), 0, 0.1, alpha=0.35),
        table=mat("table", (0.85, 0.85, 0.83, 1), 0, 0.8),
        text=mat("text", (0.02, 0.15, 0.55, 1), emit=3.0),
    )

    # table + riser
    box("Table", -0.75, 0.6, -0.55, 0.55, -0.02, 0.0, M["table"])
    box("Riser", -0.33, PD + 0.02, -PW / 2 - 0.01, 0.30, 0, RISER, M["riser"])

    # printer: base, posts, top, translucent walls
    box("X2D_base", 0, PD, -PW / 2, PW / 2, Z(0), Z(ZB - 0.045), M["frame"])
    for (x, y) in [(0, -PW / 2), (0, PW / 2 - 0.02), (PD - 0.02, -PW / 2), (PD - 0.02, PW / 2 - 0.02)]:
        box("X2D_post", x, x + 0.02, y, y + 0.02, Z(0), Z(PH), M["frame"])
    box("X2D_top", 0, PD, -PW / 2, PW / 2, Z(PH - 0.03), Z(PH), M["frame"])
    box("X2D_wall_L", 0.02, PD - 0.02, -PW / 2, -PW / 2 + 0.004, Z(0), Z(PH), M["panel"])
    box("X2D_wall_R", 0.02, PD - 0.02, PW / 2 - 0.004, PW / 2, Z(0), Z(PH), M["panel"])
    box("X2D_wall_B", PD - 0.004, PD, -PW / 2, PW / 2, Z(0), Z(PH), M["panel"])
    # toolhead parked at back-left
    box("Toolhead", PD - 0.12, PD - 0.04, -PW / 2 + 0.03, -PW / 2 + 0.11, Z(PH - 0.13), Z(PH - 0.04), M["frame"])
    # bed (heater) below plate
    box("Bed", TAB_X, PIN_X + 0.01, -0.135, 0.135, Z(ZB - 0.012), Z(ZB - 0.002), M["bed"])
    for y in (-0.06, 0.06):
        cyl("RearPin", 0.003, 0.008, (PIN_X + 0.003, y, Z(ZB + 0.002)), M["frame"], 16)
    # door: hinged on LEFT, held open ~100 deg (PLA mode)
    hinge = empty("DoorHinge", (0, -PW / 2, Z(0.06)))
    door = box("Door", 0, 0.004, 0, PW - 0.01, 0, PH - 0.10, M["glass"], hinge)
    hinge.rotation_euler.z = math.radians(-100)

    # shelf (tilting), hinge at door plane
    sh = empty("ShelfHinge", (0, 0, Z(ZB)))
    box("Shelf", -SHELF_LEN, 0, -0.140, 0.140, -0.008, 0, M["shelf"], sh)
    box("ShelfGuideL", -SHELF_LEN, 0, -0.142, -0.134, 0, 0.006, M["shelf"], sh)
    box("ShelfGuideR", -SHELF_LEN, 0, 0.134, 0.142, 0, 0.006, M["shelf"], sh)
    box("ShelfServo", -0.02, 0.0, -0.19, -0.15, Z(ZB - 0.05) - Z(ZB), -0.01, M["joint"], sh)

    # bin on table in front
    bx0, bx1 = -0.72, -0.36
    box("Bin_floor", bx0, bx1, -0.18, 0.18, 0, 0.004, M["bin"])
    box("Bin_wF", bx0, bx0 + 0.004, -0.18, 0.18, 0, 0.13, M["bin"])
    box("Bin_wB", bx1 - 0.004, bx1, -0.18, 0.18, 0, 0.13, M["bin"])
    box("Bin_wL", bx0, bx1, -0.18, -0.176, 0, 0.13, M["bin"])
    box("Bin_wR", bx0, bx1, 0.176, 0.18, 0, 0.13, M["bin"])

    # magazine frame (posts on left/back so the arm can come from the right)
    for (x, y) in [(-SHELF_LEN, -0.15), (-0.012, -0.15), (-0.012, 0.13)]:
        box("MagPost", x, x + 0.012, y, y + 0.02, Z(ZB + 0.06), Z(MAG_Z + 0.05), M["mag"])
    box("MagRail", -SHELF_LEN, 0, -0.15, -0.13, Z(MAG_Z - 0.004), Z(MAG_Z), M["mag"])
    box("MagRail2", -0.02, 0, -0.15, 0.15, Z(MAG_Z - 0.004), Z(MAG_Z), M["mag"])

    # plates
    def make_plate(name, material):
        root = empty(name)
        root.rotation_mode = "XYZ"
        yc = -HOOK_Y  # plate centre relative to hook (local y)
        box(name + "_body", -HOOK_DX + TAB, TO_REAR, yc - PLATE / 2, yc + PLATE / 2, -0.002, 0, material, root)
        box(name + "_tab", -HOOK_DX, -HOOK_DX + TAB, yc - PLATE / 2 + 0.01, yc + PLATE / 2 - 0.01, -0.002, 0, M["tab"], root)
        box(name + "_marker", -HOOK_DX + 0.003, -HOOK_DX + 0.012, yc - 0.0045, yc + 0.0045, 0, 0.0004, M["marker"], root)
        box(name + "_clip", -0.012, 0.010, -0.016, 0.016, 0, 0.008, M["clip"], root)
        return root
    A = make_plate("PlateUsed", M["plate"])
    B = make_plate("PlateNew", M["plate2"])
    spares = []
    for i in range(2):
        s = make_plate(f"PlateSpare{i}", M["plate2"])
        s.location = (OUT_HOOK_X, HOOK_Y, Z(MAG_Z + 0.008 * (i + 1)))
        spares.append(s)

    # small printed parts on the used plate
    parts = []
    k = 0
    for i in range(3):
        for j in range(4):
            lx = 0.07 + i * 0.06
            ly = -HOOK_Y - 0.08 + j * 0.05
            p = box(f"Part{k}", -0.007, 0.007, -0.007, 0.007, 0, 0.012 + 0.006 * ((i + j) % 3), M["part"])
            p.rotation_mode = "XYZ"
            parts.append((p, Vector((lx, ly, 0))))
            k += 1

    # arm
    cyl("ArmPedestal", 0.045, Z(HS) - RISER - 0.02, (BASE.x, BASE.y, RISER + (Z(HS) - RISER - 0.02) / 2), M["joint"])
    arm = {}
    for nm, ln, r in [("Upper", L1, 0.014), ("Fore", L2, 0.012), ("Tool", TOOL, 0.009)]:
        bpy.ops.mesh.primitive_cube_add(size=1)
        o = bpy.context.active_object
        o.name = "Arm" + nm
        o.scale = (ln, r * 2, r * 2)
        bpy.ops.object.transform_apply(scale=True)
        o.data.materials.append(M["arm"])
        o.rotation_mode = "QUATERNION"
        arm[nm] = o
    for nm in ("Shoulder", "Elbow", "Wrist"):
        o = cyl("Joint" + nm, 0.018, 0.04, (0, 0, 0), M["joint"])
        o.rotation_mode = "QUATERNION"
        arm[nm] = o
    pin = cyl("TPin", 0.003, PIN, (0, 0, 0), M["pin"], 12)
    pin.rotation_mode = "XYZ"
    tbar = box("TBar", -0.008, 0.008, -0.0025, 0.0025, -0.0025, 0.0025, M["pin"])
    tbar.rotation_mode = "XYZ"
    arm["Pin"], arm["TBar"] = pin, tbar

    # labels (Japanese font if found)
    font = None
    for fp in ["/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
               "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothB.ttc",
               "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"]:
        if os.path.exists(fp):
            try:
                font = bpy.data.fonts.load(fp)
                break
            except Exception:
                pass

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    cam.location = (-0.95, 0.85, Z(0.40))
    tgt = empty("CamTarget", (-0.08, 0.0, Z(0.02)))
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    cam.data.lens = 30
    sc.camera = cam

    labels = {}
    def label(key, txt):
        cu = bpy.data.curves.new(key, "FONT")
        cu.body = txt
        cu.size = 0.042
        cu.align_x = "CENTER"
        if font:
            cu.font = font
        o = bpy.data.objects.new("Label_" + key, cu)
        sc.collection.objects.link(o)
        o.data.materials.append(M["text"])
        o.parent = cam              # HUD caption fixed to the camera
        o.location = (0.0, 0.27, -1.0)
        labels[key] = o
    for key, txt in STEPS_TXT:
        label(key, txt)

    # lights / world
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-40))
    sc.collection.objects.link(sun)
    area = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "AREA"))
    area.data.energy = 120
    area.data.size = 1.0
    area.location = (-0.8, -0.6, 1.2)
    area.rotation_euler = (math.radians(40), 0, math.radians(-120))
    sc.collection.objects.link(area)
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    sc.world = world

    return dict(A=A, B=B, spares=spares, parts=parts, arm=arm, shelf=sh, labels=labels)

# ------------------------------------------------------------------ timeline
STEPS_TXT = [
    ("s0", "① 印刷完了 → GO（人がカメラで確認）"),
    ("s1", "② T字ピンを刺して90°回してロック"),
    ("s2", "③ 手前を持ち上げて磁石から剥がす"),
    ("s3", "④ 受け台まで引き出す"),
    ("s4", "⑤ 受け台を傾けて回収箱へ落とす"),
    ("s5", "⑥ マガジンから新品を1枚下ろす"),
    ("s6", "⑦ 斜め12°で奥のピンまで押し込む"),
    ("s7", "⑧ 奥ピンを支点に手前を下ろす → 磁石で吸着"),
    ("s8", "⑨ プレート自動認識OK → 次の印刷へ"),
]
STEP_FRAMES = [0, 24, 64, 88, 196, 280, 356, 448, 520, 600]
END = 600

HOME = (-0.06, 0.12, ZB + 0.075)
ABOVE_A = (SEATED_HOOK_X, HOOK_Y, ZB + 0.030)
IN_A = (SEATED_HOOK_X, HOOK_Y, ZB + 0.002)
PEEL = (SEATED_HOOK_X - 0.003, HOOK_Y, ZB + 0.035)
DRAG0 = (SEATED_HOOK_X - 0.01, HOOK_Y, ZB + 0.020)
DRAG1 = (OUT_HOOK_X, HOOK_Y, ZB + 0.020)
DOWN_OUT = (OUT_HOOK_X, HOOK_Y, ZB + 0.002)
UP_OUT = (OUT_HOOK_X, HOOK_Y, ZB + 0.040)
PARK = (-0.04, 0.215, ZB + 0.060)
ABOVE_B = (OUT_HOOK_X, HOOK_Y, ZB + 0.030)
LIFT_B = (OUT_HOOK_X + 0.006, HOOK_Y, ZB + TO_REAR * math.sin(INSERT_TILT))
PUSH_B = (PIN_X - TO_REAR * math.cos(INSERT_TILT), HOOK_Y, ZB + TO_REAR * math.sin(INSERT_TILT))
SEAT_B = (SEATED_HOOK_X, HOOK_Y, ZB + 0.002)
UP_B = (SEATED_HOOK_X, HOOK_Y, ZB + 0.040)

HOOK = Track((0, HOME), (24, HOME), (44, ABOVE_A), (56, IN_A), (70, IN_A), (88, PEEL), (98, DRAG0),
             (170, DRAG1), (180, DOWN_OUT), (190, DOWN_OUT), (200, UP_OUT), (218, PARK),
             (300, PARK), (318, ABOVE_B), (328, DOWN_OUT), (342, DOWN_OUT), (362, LIFT_B),
             (440, PUSH_B), (476, SEAT_B), (490, SEAT_B), (502, UP_B), (530, HOME), (END, HOME))
PINROT = Track((0, 0.0), (58, 0.0), (68, 90.0), (182, 90.0), (190, 0.0), (330, 0.0), (340, 90.0),
               (478, 90.0), (488, 0.0), (END, 0.0))
A_GRAB, A_RELEASE = 68, 182
SHELF = Track((0, 0.0), (220, 0.0), (240, 35.0), (272, 35.0), (290, 0.0), (END, 0.0))
A_SLIDE = Track((0, 0.0), (232, 0.0), (244, 0.03), (262, 0.40), (END, 0.40))
B_DROP = Track((0, MAG_Z), (292, MAG_Z), (318, ZB), (END, ZB))
B_GRAB, B_RELEASE = 340, 478
PARTS_FLY = (240, 270)

def plate_on_hook(o, hook):
    hx, hy, hz = hook
    th = math.asin(max(0.0, min(1.0, (hz - ZB) / TO_REAR)))
    o.location = (hx, hy, Z(hz))
    o.rotation_euler = (0, th, 0)

def plate_flat(o, x, y=HOOK_Y, z=ZB):
    o.location = (x, y, Z(z))
    o.rotation_euler = (0, 0, 0)

def plate_on_shelf(o, phi, slide):
    """Plate lying on tilted shelf, hook distance from hinge = -OUT_HOOK_X + slide."""
    d = -OUT_HOOK_X + slide
    o.location = (-d * math.cos(phi), HOOK_Y, Z(ZB) - d * math.sin(phi))
    o.rotation_euler = (0, -phi, 0)

def ik(tip):
    tip = Vector(tip)
    S = Vector((BASE.x, BASE.y, HS))
    u = Vector((tip.x - BASE.x, tip.y - BASE.y, 0)).normalized()
    r = (Vector((tip.x, tip.y, 0)) - Vector((BASE.x, BASE.y, 0))).length - TOOL
    zz = tip.z + PIN - HS
    d = math.hypot(r, zz)
    d = min(d, L1 + L2 - 1e-4)
    a = math.atan2(zz, r) + math.acos(d / (2 * L1))
    E = S + u * (L1 * math.cos(a)) + Vector((0, 0, L1 * math.sin(a)))
    W = S + u * r + Vector((0, 0, zz))
    T = W + u * TOOL
    return S, E, W, T, u

def place_link(o, p, q):
    p, q = Vector((p.x, p.y, Z(p.z))), Vector((q.x, q.y, Z(q.z)))
    o.location = (p + q) / 2
    o.rotation_quaternion = (q - p).to_track_quat("X", "Z")
    o.keyframe_insert("location")
    o.keyframe_insert("rotation_quaternion")

def key(o):
    o.keyframe_insert("location")
    o.keyframe_insert("rotation_euler")

def animate(obj):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 0, END
    A, B, arm = obj["A"], obj["B"], obj["arm"]
    for f in range(0, END + 1):
        sc.frame_set(f)
        hook = HOOK(f)
        # arm
        S, E, W, T, u = ik(hook)
        place_link(arm["Upper"], S, E)
        place_link(arm["Fore"], E, W)
        place_link(arm["Tool"], W, T)
        for nm, p in (("Shoulder", S), ("Elbow", E), ("Wrist", W)):
            o = arm[nm]
            o.location = (p.x, p.y, Z(p.z))
            o.rotation_quaternion = Vector((u.y, -u.x, 0)).to_track_quat("Z", "X")
            o.keyframe_insert("location"); o.keyframe_insert("rotation_quaternion")
        yaw = math.atan2(u.y, u.x)
        arm["Pin"].location = (T.x, T.y, Z(T.z - PIN / 2))
        key(arm["Pin"])
        arm["TBar"].location = (T.x, T.y, Z(T.z - PIN + 0.002))
        arm["TBar"].rotation_euler = (0, 0, yaw + math.radians(PINROT(f)))
        key(arm["TBar"])
        # used plate
        phi = math.radians(SHELF(f))
        if f < A_GRAB:
            plate_flat(A, SEATED_HOOK_X)
        elif f <= A_RELEASE:
            plate_on_hook(A, hook)
        elif phi == 0 and A_SLIDE(f) == 0:
            plate_flat(A, OUT_HOOK_X)
        else:
            s = A_SLIDE(f)
            if s <= 0.20:
                plate_on_shelf(A, phi if f < 262 else math.radians(35), s)
            else:  # falling into bin
                t = smooth((f - 254) / 18)
                plate_on_shelf(A, math.radians(35), 0.20)
                p0 = Vector(A.location)
                p1 = Vector((-0.40, HOOK_Y - 0.02, 0.03))
                A.location = p0.lerp(p1, t)
                A.rotation_euler = (math.radians(4) * t, -math.radians(35) * (1 - t) - math.radians(8) * t, 0)
        key(A)
        # parts follow plate A until they fly into bin
        for i, (p, lp) in enumerate(obj["parts"]):
            rot = Euler(A.rotation_euler)
            wp = Vector(A.location) + rot.to_matrix() @ lp
            if f < PARTS_FLY[0]:
                p.location = wp
                p.rotation_euler = rot
            else:
                t = smooth((f - PARTS_FLY[0]) / (PARTS_FLY[1] - PARTS_FLY[0]))
                tgt = Vector((-0.62 + 0.03 * (i % 4), -0.12 + 0.05 * (i // 4) + 0.01 * (i % 3), 0.01))
                if f == PARTS_FLY[0]:
                    obj.setdefault("p0", {})[i] = wp.copy()
                p0 = obj["p0"][i]
                mid = p0.lerp(tgt, t)
                mid.z += 0.06 * math.sin(math.pi * t)
                p.location = mid
                p.rotation_euler = (rot.x + 2.5 * t * (1 + i % 3), rot.y + 1.7 * t, 0.8 * t * i)
            key(p)
        # new plate
        if f < B_GRAB:
            plate_flat(B, OUT_HOOK_X, z=B_DROP(f))
        elif f <= B_RELEASE:
            plate_on_hook(B, hook)
        else:
            plate_flat(B, SEATED_HOOK_X)
        key(B)
        # shelf
        obj["shelf"].rotation_euler = (0, -phi, 0)
        obj["shelf"].keyframe_insert("rotation_euler")
        # labels
        for i, (k, _) in enumerate(STEPS_TXT):
            vis = STEP_FRAMES[i] <= f < STEP_FRAMES[i + 1] or (i == len(STEPS_TXT) - 1 and f >= STEP_FRAMES[i])
            o = obj["labels"][k]
            o.hide_render = not vis
            o.hide_viewport = not vis
            o.keyframe_insert("hide_render")
            o.keyframe_insert("hide_viewport")
    # constant interpolation for visibility, linear elsewhere (dense keys)
    for o in bpy.data.objects:
        ad = o.animation_data
        if ad and ad.action:
            fcs = getattr(ad.action, "fcurves", None)
            if fcs is None:
                try:
                    fcs = [fc for layer in ad.action.layers for strip in layer.strips
                           for bag in strip.channelbags for fc in bag.fcurves]
                except Exception:
                    fcs = []
            for fc in fcs:
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT" if "hide" in fc.data_path else "LINEAR"
    sc.frame_set(0)

# ------------------------------------------------------------------ main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    obj = build()
    animate(obj)
    out = None
    step = 2
    if "--render" in argv:
        out = argv[argv.index("--render") + 1]
    if "--step" in argv:
        step = int(argv[argv.index("--step") + 1])
    if "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[argv.index("--save") + 1]))
    if out:
        sc = bpy.context.scene
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = int(os.environ.get("SAMPLES", 12))
        try:
            sc.cycles.use_denoising = True
        except Exception:
            pass
        sc.render.resolution_x, sc.render.resolution_y = 960, 540
        sc.render.image_settings.file_format = "PNG"
        frames = range(int(os.environ.get("F0", 0)), int(os.environ.get("F1", END)) + 1, step)
        for f in frames:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(out, f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)

if __name__ == "__main__":
    main()
