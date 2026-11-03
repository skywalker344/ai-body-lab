#!/usr/bin/env python3
"""R2カップ用ドームを元モデル（MakerWorld / The Elemental Brick）から作る。

  1. ドーム本体（グレー）とブルートリム（青）を中心合わせ
  2. 中身の詰まったドームを、外側から一定の肉厚だけ残してくり抜く（底は開ける）
  3. フロントロジック（2窓）・PSI・リアロジックに光の窓を開ける
  4. 底の内側に取り付け用の棚（リング）を足す
  5. 直径100mmに縮小して書き出す（色ごとに別STL＝はめ込み多色印刷用）

使い方:
  python make_dome.py <元STLのフォルダ> <出力フォルダ>

依存: trimesh numpy scipy scikit-image manifold3d matplotlib
元モデルのSTLはライセンスの都合でリポジトリに含めない。
"""
import os
import sys

import numpy as np
import trimesh
from manifold3d import Manifold, Mesh
from matplotlib.path import Path
from scipy import ndimage
from skimage import measure

# ------------------------------------------------------------------ 設定
TARGET_DIAMETER = 100.0   # 仕上がり直径 mm
WALL = 2.4                # 仕上がり肉厚 mm
LEDGE_WIDTH = 6.0         # 底の取り付け棚の幅 mm（仕上がり）
LEDGE_HEIGHT = 2.4        # 底の取り付け棚の高さ mm（仕上がり）
PITCH = 0.45              # くり抜き計算の解像度（元寸法 mm）
CLOSE_RADIUS_VOX = 3      # すき間埋めの半径（ボクセル数。0.45mm×3 ≒ 1.4mm）

GREY = "obj_42_dome.stl_3.stl"
BLUE = "obj_57_blue trim (1).stl"
SMALL_PARTS = {  # 一緒に縮小しておく小物（元ファイル名 → 出力名）
    "obj_44_dome.stl_13.stl": "radar_eye_housing.stl",
    "obj_45_dome.stl_14.stl": "part_45.stl",
    "obj_46_dome.stl_16.stl": "part_46_disc.stl",
    "obj_47_dome.stl_17.stl": "holo_a.stl",
    "obj_48_dome.stl_18.stl": "holo_b.stl",
    "obj_49_dome.stl_19.stl": "holo_c.stl",
    "obj_50_dome.stl_20.stl": "part_50.stl",
}

# 窓（元寸法 mm、ドーム中心・底面基準。正面は -Y）
# box: (xmin, xmax, zmin, zmax, ymin, ymax)
WINDOWS_BOX = [
    (-29.5, -22.5, 3.0, 10.5, -80, -35),    # フロントロジック 下
    (-29.5, -22.5, 14.5, 21.5, -80, -35),   # フロントロジック 上
    (-50.0, -25.5, 12.5, 18.5, 35, 80),     # リアロジック（背面）
]
# cyl: (x, z, r, ymin, ymax)  Y方向の円柱
WINDOWS_CYL = [
    (7.0, 10.0, 3.6, -80, -35),             # PSI
]


# ------------------------------------------------------------------ 共通
def load_centered(path, center=None):
    m = trimesh.load(path, force="mesh")
    return m


def to_manifold(m: trimesh.Trimesh) -> Manifold:
    mesh = Mesh(vert_properties=np.asarray(m.vertices, dtype=np.float32),
                tri_verts=np.asarray(m.faces, dtype=np.uint32))
    out = Manifold(mesh)
    if out.status().name != "NoError":
        raise RuntimeError(f"manifold error: {out.status()}")
    return out


def to_trimesh(man: Manifold) -> trimesh.Trimesh:
    mm = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mm.vert_properties)[:, :3],
                           faces=np.asarray(mm.tri_verts), process=True)


def occupancy(mesh: trimesh.Trimesh, xs, ys, zs) -> np.ndarray:
    """z方向にスライスして断面をラスタライズし、中身の詰まり具合を3D配列にする。"""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    pts = np.column_stack([X.ravel(), Y.ravel()])
    vol = np.zeros((len(xs), len(ys), len(zs)), dtype=bool)
    for k, z in enumerate(zs):
        sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        inside = np.zeros(len(pts), dtype=bool)
        for loop in sec.discrete:
            inside ^= Path(loop[:, :2]).contains_points(pts)  # 偶奇規則で穴も扱う
        vol[:, :, k] = inside.reshape(X.shape)
    return vol


# ------------------------------------------------------------------ 本体
def main(src, out):
    os.makedirs(out, exist_ok=True)
    grey = trimesh.load(os.path.join(src, GREY), force="mesh")
    blue = trimesh.load(os.path.join(src, BLUE), force="mesh")
    # 2パーツは同じ位置関係のまま、合体した外形の中心・底を原点にそろえる
    gb, bb = grey.bounds, blue.bounds
    for m in (grey, blue):
        b = m.bounds
        c = b.mean(0)
        m.apply_translation([-c[0], -c[1], -b[0][2]])
    union = to_trimesh(to_manifold(grey) + to_manifold(blue))
    radius = max(union.extents[:2]) / 2
    s = TARGET_DIAMETER / (2 * radius)
    wall = WALL / s
    print(f"元の直径 {2 * radius:.1f}mm → 縮尺 {s:.3f}、元寸法での肉厚 {wall:.2f}mm")

    # --- くり抜き用の空洞を作る（外面からの距離が肉厚以上の部分）
    pad = 12
    xs = np.arange(-radius - 2, radius + 2, PITCH)
    ys = xs.copy()
    zs = np.arange(PITCH / 2, union.bounds[1][2] + 2, PITCH)
    vol = occupancy(union, xs, ys, zs)
    below = np.repeat(vol[:, :, :1], pad, axis=2)          # 底の下にも中身があるとみなす＝底を開ける
    full = np.concatenate([below, vol], axis=2)
    # 色パーツ同士のはめ込みのすき間（約0.2mm）を埋める。埋めないと内側に壁が残る
    r = CLOSE_RADIUS_VOX
    g = np.mgrid[-r:r + 1, -r:r + 1, -r:r + 1]
    ball = (g ** 2).sum(0) <= r * r
    full = np.pad(full, r + 1)
    full = ndimage.binary_closing(full, structure=ball)[r + 1:-r - 1, r + 1:-r - 1, r + 1:-r - 1]
    dist = ndimage.distance_transform_edt(full, sampling=PITCH)
    cavity = dist > wall
    lab, n = ndimage.label(cavity)
    if n > 1:  # 一番大きい空洞だけ残す
        sizes = ndimage.sum(cavity, lab, range(1, n + 1))
        cavity = lab == (1 + int(np.argmax(sizes)))
    cavity = np.pad(cavity, 1)
    verts, faces, _, _ = measure.marching_cubes(cavity.astype(np.float32), 0.5)
    verts = verts - 1
    verts = np.column_stack([
        xs[0] + verts[:, 0] * PITCH,
        ys[0] + verts[:, 1] * PITCH,
        zs[0] - pad * PITCH + verts[:, 2] * PITCH,
    ])
    cav = trimesh.Trimesh(verts, faces[:, ::-1], process=True)
    if cav.volume < 0:
        cav.invert()
    cav_m = to_manifold(cav)

    # --- 窓
    cut = Manifold()
    for x0, x1, z0, z1, y0, y1 in WINDOWS_BOX:
        cut += Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])
    for x, z, r, y0, y1 in WINDOWS_CYL:
        c = Manifold.cylinder(y1 - y0, r, r, 48).rotate([-90, 0, 0]).translate([x, y0, z])
        cut += c

    # --- 底の取り付け棚（外周の内側にリング）
    inner_r = radius - wall - LEDGE_WIDTH / s
    ring = (Manifold.cylinder(LEDGE_HEIGHT / s, radius + 1, radius + 1, 128)
            - Manifold.cylinder(LEDGE_HEIGHT / s, inner_r, inner_r, 128))
    shell_outer = to_manifold(union)
    ledge = ring ^ shell_outer      # 外形からはみ出さない分だけ

    g = to_manifold(grey) - cav_m - cut
    b = to_manifold(blue) - cav_m - cut
    g = g + (ledge - b)             # 棚はグレー側に足す（青と重ならないように）

    for name, man in (("dome_grey.stl", g), ("dome_blue.stl", b)):
        tm = to_trimesh(man)
        tm.apply_scale(s)
        tm.export(os.path.join(out, name))
        print(f"{name}: {np.round(tm.extents, 1)} mm  体積 {tm.volume / 1000:.1f} cm3  閉じた形状={tm.is_watertight}")

    for src_name, dst in SMALL_PARTS.items():
        tm = trimesh.load(os.path.join(src, src_name), force="mesh")
        tm.apply_translation(-tm.bounds[0])
        tm.apply_scale(s)
        tm.export(os.path.join(out, dst))
    print("小物も縮小:", ", ".join(SMALL_PARTS.values()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
