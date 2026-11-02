"""Rotary cell: arm in front of X2D, stations at 0 (printer) / 90 (fresh) / 180 (used)."""
import math, os, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Wedge
from matplotlib.transforms import Affine2D
plt.rcParams["font.family"] = "IPAGothic"
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"
PW, PD = 392, 406; PL, PWD = 272, 257          # printer, plate (len incl. tab, width)
TAB_X, HOOK_DX = 45, 8
R_MIN = 80                                       # closest hook radius (gripper/base clearance)
D = R_MIN + PL + 20                              # base distance in front of door so plate clears
R_IN = D + TAB_X + HOOK_DX                       # hook radius when plate seated
R_SWEEP = math.hypot(R_MIN + PL, PWD / 2)        # swept radius of carried plate
print(f"base {D} mm in front of door, hook r {R_MIN}-{R_IN} mm, sweep radius {R_SWEEP:.0f} mm")
m = 0.30 * 9.81
print(f"worst carry moment (plate in air at full reach) {m*(R_IN+136)/1000:.2f} N·m, folded {m*(R_MIN+136)/1000:.2f} N·m")
fig, ax = plt.subplots(figsize=(9, 9))
B = np.array([-D, 0.0])
ax.add_patch(Rectangle((0, -PW/2), PD, PW, fill=False, lw=2, ec="#444")); ax.text(PD/2, 0, "X2D\n(0°)", ha="center", va="center", fontsize=13)
ax.add_patch(Circle(B, R_SWEEP, fill=False, ls="--", ec="#3498db")); ax.text(B[0], B[1] - R_SWEEP - 25, f"プレートの旋回範囲 半径{R_SWEEP:.0f}mm（この円内は空ける）", ha="center", color="#2471a3")
def plate(theta, r_hook, color, label):
    t = math.radians(theta)
    tr = Affine2D().rotate(t).translate(*B) + ax.transData
    ax.add_patch(Rectangle((r_hook, -PWD/2), PL, PWD, fc=color, alpha=.35, ec=color, transform=tr))
    c = B + (r_hook + PL/2 + 0) * np.array([math.cos(t), math.sin(t)])
    ax.text(*c, label, ha="center", va="center", fontsize=11)
plate(0, R_MIN, "#7f8c8d", "引き出し後\n（ここで旋回）")
plate(90, R_MIN, "#2e86c1", "新品ストック\n(90°)\n段積みラック")
plate(180, R_MIN, "#c0392b", "使用済み\n(180°)\n回収箱に落とす")
ax.add_patch(Circle(B, 55, fc="#f39c12", ec="k")); ax.text(*B, "アーム\n根元", ha="center", va="center", fontsize=9)
ax.annotate("", xy=(0, -PW/2 - 40), xytext=(-D, -PW/2 - 40), arrowprops=dict(arrowstyle="<->"))
ax.text(-D/2, -PW/2 - 60, f"{D} mm", ha="center")
ax.annotate("", xy=(B[0] + R_IN, 40), xytext=(B[0] + R_MIN, 40), arrowprops=dict(arrowstyle="<->", color="#8e44ad", lw=2))
ax.text(B[0] + (R_IN + R_MIN)/2, 55, f"出し入れ {R_IN - R_MIN} mm（半径方向だけ）", ha="center", color="#8e44ad")
ax.set_xlim(-D - R_SWEEP - 60, PD + 40); ax.set_ylim(-R_SWEEP - 80, R_SWEEP + 60); ax.set_aspect("equal"); ax.grid(alpha=.2)
ax.set_title("旋回レイアウト（上から見た図）：0°プリンタ / 90°新品 / 180°使用済み", fontsize=13)
fig.text(.01, .01, "動き＝半径方向の出し入れ＋上下＋根元の回転だけ → 円筒座標ロボット（R-θ-Z）向き。寸法は仮。", fontsize=9, color="#555")
plt.tight_layout(rect=(0, .03, 1, 1)); plt.savefig(OUT + "rotary_layout.png", dpi=100)
