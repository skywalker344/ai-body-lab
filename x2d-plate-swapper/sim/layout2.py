"""X2D plate-swap arm: virtual layout & link-length study.
Coordinates (mm): x=0 at printer front face (door plane), +x into printer.
y=0 printer centre line, +y = right when facing printer. z=0 table.
Values marked ASSUME must be measured on the real machine.
"""
import math, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Wedge, FancyArrowPatch
plt.rcParams["font.family"] = "IPAGothic"

import os
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"

# --- known (web) ---
PW, PD, PH = 392, 406, 478          # printer outside W x D x H
PLATE = 257                          # plate approx square
TAB = 15                             # front tab depth (ASSUME, from photo)
# --- assumptions ---
TAB_TIP_X = 45                       # tab tip behind door plane (ASSUME)
SILL_Z = 90                          # door sill height above table (ASSUME)
ZB = SILL_Z + 3                      # bed surface parked just above sill
OPEN_Y = 170                         # half width of door opening (ASSUME)
HOOK_Y = 100                         # right-front clip-on hook (door hinge is LEFT)
HOOK_DX = 8                          # cutout centre behind tab tip
SEAT = 5                             # extra push to seat on rear pins
OUT_CLEAR = 10                       # plate rear edge this far outside door

plate_len = PLATE + TAB
hook_in = TAB_TIP_X + HOOK_DX + SEAT
hook_out = -OUT_CLEAR - plate_len + HOOK_DX
path_x = np.linspace(hook_out, hook_in, 200)

# z targets relative to bed
Z_PIN = ZB - 5      # peg tip into cutout
Z_PEEL = ZB + 35    # lift front edge to break magnet
Z_CARRY = ZB + 20   # carry front edge slightly lifted

def ranges(bx, by):
    r = np.hypot(path_x - bx, HOOK_Y - by)
    return r.min(), r.max()

# search base position: outside printer front (x<=-70), outside plate lane
best = None
for bx in range(-260, -69, 5):
    for by in range(190, 321, 5):        # right side (away from left hinge)
        rmin, rmax = ranges(bx, by)
        if rmin < 90:                    # too close: arm folds over itself
            continue
        # forearm must pass through door opening when at hook_in
        t = (0 - bx) / (hook_in - bx)
        ycross = by + t * (HOOK_Y - by)
        if ycross > OPEN_Y - 30:
            continue
        if best is None or rmax < best[0]:
            best = (rmax, rmin, bx, by)
rmax, rmin, BX, BY = best

TOOL = 40                 # palletiser-style horizontal tool offset
HS = ZB + 40              # shoulder height
dz = [Z_PIN - HS, Z_PEEL - HS, Z_CARRY - HS]
dmax = max(math.hypot(rmax - TOOL, d) for d in dz)
dmin = min(math.hypot(max(rmin - TOOL, 0), d) for d in dz)
L = math.ceil(dmax * 1.15 / 2 / 5) * 5      # equal links, 15 % margin
assert abs(L - L) <= dmin

def ik(r, z):
    """2-link planar IK (elbow up). returns shoulder & elbow points in (r,z)."""
    rr, zz = r - TOOL, z - HS
    d = math.hypot(rr, zz)
    a = math.atan2(zz, rr) + math.acos(d / (2 * L))
    e = (L * math.cos(a), HS + L * math.sin(a))
    return (0, HS), e, (rr, z), (r, z)

# stroke
stroke = hook_in - hook_out

report = f"""
=== 配置結果 ===
ベース位置 x={BX} mm (プリンタ前面から手前), y={BY} mm (中心から右)
フック経路 x: {hook_out:.0f} → {hook_in:.0f} mm (ストローク {stroke:.0f} mm), y={HOOK_Y}
必要水平リーチ r: {rmin:.0f} 〜 {rmax:.0f} mm
肩の高さ {HS} mm / ベッド面 {ZB} mm
上腕 = 前腕 = {L} mm, 先端オフセット {TOOL} mm  → 最大リーチ約 {2*L+TOOL} mm
"""
print(report)
open(OUT + "layout_v2.txt", "w").write(report)

# ---------------- figure ----------------
fig, (ax, bx_) = plt.subplots(1, 2, figsize=(15, 7.5), gridspec_kw={"width_ratios": [1.15, 1]})

# TOP VIEW
ax.set_title("上から見た図（仮想配置）", fontsize=14)
ax.add_patch(Rectangle((0, -PW/2), PD, PW, fill=False, lw=2, ec="#444"))
ax.text(PD/2, PW/2 + 12, "X2D 392×406", ha="center")
ax.add_patch(Rectangle((-2, -OPEN_Y), 4, 2*OPEN_Y, color="#f39c12"))
ax.text(8, OPEN_Y - 15, "ドア開口(仮定)", color="#d35400", fontsize=9)
# plate inside
ax.add_patch(Rectangle((TAB_TIP_X + TAB, -PLATE/2), PLATE, PLATE, fc="#2c3e50", alpha=.25, ec="#2c3e50"))
ax.add_patch(Rectangle((TAB_TIP_X, -PLATE/2), TAB, PLATE, fc="#2c3e50", alpha=.5))
ax.text(TAB_TIP_X + 140, 0, "プレート\n(印刷位置)", ha="center", va="center")
# rear pins
for py in (-60, 60):
    ax.add_patch(Circle((TAB_TIP_X + plate_len + 3, py), 4, color="k"))
ax.text(TAB_TIP_X + plate_len + 10, 75, "奥の位置決めピン", fontsize=8)
# shelf / staging
sx0 = -OUT_CLEAR - plate_len - 10
ax.add_patch(Rectangle((sx0, -PLATE/2 - 10), -sx0, PLATE + 20, fc="#27ae60", alpha=.15, ec="#27ae60", ls="--"))
ax.text(sx0 + 140, 0, "受け台（ベッドと同じ高さ）\n手前に傾けて→下の回収箱へ\n真上に新品マガジン", ha="center", fontsize=9, color="#1e8449")
ax.add_patch(Wedge((0, -PW/2), 2*OPEN_Y + 20, 90, 180, fc="#e67e22", alpha=.12, ec="#e67e22", ls=":"))
ax.plot([0, -(2*OPEN_Y + 20)], [-PW/2, -PW/2], color="#e67e22", lw=3)
ax.text(-190, -PW/2 + 25, "左蝶番ドアの通り道（受け台と重なる！）\nPLA：開けっ放し固定／ABS等：上下スライド扉に交換", color="#d35400", fontsize=9, ha="center")
# hook path
ax.annotate("", xy=(hook_out, HOOK_Y), xytext=(hook_in, HOOK_Y),
            arrowprops=dict(arrowstyle="<->", color="#8e44ad", lw=2))
ax.text((hook_in + hook_out)/2, HOOK_Y - 22, f"フック移動 {stroke:.0f}mm（右手前・クリップ式フック）", ha="center", color="#8e44ad", fontsize=9)
# reach annulus
ax.add_patch(Wedge((BX, BY), 2*L + TOOL, 0, 360, width=2*L + TOOL - rmin + 20, fc="#3498db", alpha=.07))
ax.add_patch(Circle((BX, BY), 45, fc="#3498db", ec="k"))
ax.text(BX, BY - 65, f"アーム根元\n({BX},{BY})", ha="center", fontsize=9)
for px in (hook_in, hook_out):
    ax.plot([BX, px], [BY, HOOK_Y], color="#2980b9", lw=4, alpha=.7, solid_capstyle="round")
ax.set_xlim(-420, 450); ax.set_ylim(-260, 400); ax.set_aspect("equal")
ax.set_xlabel("x mm（＋がプリンタ奥）"); ax.set_ylabel("y mm"); ax.grid(alpha=.2)

# SIDE VIEW (section through hook line, r measured from base)
b = bx_
b.set_title("横から見た図（腕の長さ確認）", fontsize=14)
b.axhline(0, color="k")
b.add_patch(Rectangle((-20, ZB - 15), 400, 15, fc="#95a5a6", alpha=.4))
b.text(150, ZB - 30, "ベッド/受け台の高さ（任意位置で停止）", fontsize=9)
b.add_patch(Rectangle((-20, 0), 40, HS - 20, fc="#7f8c8d", alpha=.4))
b.text(0, 20, "台座", ha="center", fontsize=8)
colors = {"刺す": "#8e44ad", "剥がす(+35)": "#c0392b", "引く/押す(+20)": "#16a085"}
for (name, z), r in zip([("刺す", Z_PIN), ("剥がす(+35)", Z_PEEL), ("引く/押す(+20)", Z_CARRY)], (rmax, rmax, rmin)):
    s, e, w, t = ik(r, z)
    c = colors[name]
    b.plot([s[0], e[0], w[0]], [s[1], e[1], w[1]], "-o", color=c, lw=3, label=f"{name}  r={r:.0f}")
    b.plot([w[0], t[0], t[0]], [w[1], w[1], t[1]], color=c, lw=2)
b.add_patch(Rectangle((-30, ZB + 130), 300, 12, fc="#f1c40f", alpha=.5))
b.text(120, ZB + 150, "新品マガジン（受け台の上 +130mm・ひじより上）", fontsize=9, ha="center")
b.legend(loc="upper right", fontsize=9)
b.set_xlim(-60, 2*L + TOOL + 40); b.set_ylim(0, ZB + 2*L); b.set_aspect("equal"); b.grid(alpha=.2)
b.set_xlabel("根元からの水平距離 r (mm)"); b.set_ylabel("高さ z (mm)")
b.text(-50, ZB + 2*L - 25, f"上腕 {L}mm ＋ 前腕 {L}mm ＋ 先端 {TOOL}mm", fontsize=11)

fig.text(0.01, 0.01, "※ 外形・造形サイズはWeb公開値。ドア開口・敷居高さ・ツメ位置・切り欠き位置は仮定（要実測）。", fontsize=9, color="#555")
plt.tight_layout(rect=(0, 0.03, 1, 1))
plt.savefig(OUT + "x2d_arm_layout_v2.png", dpi=110)
print("saved")
