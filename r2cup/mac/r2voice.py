#!/usr/bin/env python3
"""R2カップ用ビープ音シンセサイザー（完全自作・サンプル音源不使用）

アストロメク・ドロイドっぽさの特徴を合成で再現する:
  - 口笛のような滑らかなピッチグライド（指数カーブ）
  - 音の頭の「しゃくり」（目標ピッチへ素早く滑り込む）
  - 2音を高速で行き来するトリル
  - FMによるワーブル（ふるえ）
  - 早口の電子チャター
  - 長い下降の悲鳴、低いブーイング（ラズベリー）

使い方:
  python r2voice.py happy --play          # 感情を鳴らす
  python r2voice.py talk "こんにちは！" --play   # テキストからおしゃべり
  python r2voice.py demo --out samples/   # 全種類をWAVに書き出す

依存: numpy のみ（再生は macOS の afplay）
"""
from __future__ import annotations

import argparse
import hashlib
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100


# ---------------------------------------------------------------- 基本部品

def _n(sec: float) -> int:
    return max(1, int(sec * SR))


def _env(n: int, attack: float = 0.006, release: float = 0.025) -> np.ndarray:
    a = min(_n(attack), n // 2)
    r = min(_n(release), n - a)
    e = np.ones(n)
    if a:
        e[:a] = np.linspace(0.0, 1.0, a) ** 1.5
    if r:
        e[-r:] = np.linspace(1.0, 0.0, r) ** 1.5
    return e


def _osc(freq: np.ndarray, bright: float = 0.18) -> np.ndarray:
    """周波数配列から音を作る。サイン主体＋少しの倍音で電子的な口笛っぽく。"""
    ph = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(ph) + bright * np.sin(2 * ph) + 0.4 * bright * np.sin(3 * ph)


def _curve(t: np.ndarray, shape: str) -> np.ndarray:
    if shape == "lin":
        return t
    if shape == "out":   # 最初に速く動いて落ち着く
        return 1 - (1 - t) ** 3
    if shape == "in":    # 最後に一気に動く
        return t ** 3
    if shape == "arc":   # 行って戻る
        return np.sin(np.pi * t)
    if shape == "s":
        return 0.5 - 0.5 * np.cos(np.pi * t)
    raise ValueError(shape)


def whistle(f0: float, f1: float, dur: float, shape: str = "s",
            vib_rate: float = 0.0, vib_depth: float = 0.0,
            scoop: float = 0.0, amp: float = 1.0, bright: float = 0.18) -> np.ndarray:
    """f0→f1 へ指数的にグライドする口笛音。

    scoop: 音頭のしゃくり量（0.15 なら目標の15%下から滑り込む。負で上から）
    """
    n = _n(dur)
    t = np.linspace(0.0, 1.0, n)
    c = _curve(t, shape)
    if shape == "arc":
        freq = f0 * (f1 / f0) ** c
    else:
        freq = f0 * (f1 / f0) ** c
    if scoop:
        k = np.exp(-np.arange(n) / (0.018 * SR))
        freq = freq * (1 - scoop * k)
    if vib_depth:
        freq = freq * (1 + vib_depth * np.sin(2 * np.pi * vib_rate * np.arange(n) / SR))
    return amp * _osc(freq, bright) * _env(n)


def blip(f: float, dur: float = 0.045, amp: float = 0.9, scoop: float = 0.12) -> np.ndarray:
    return whistle(f, f, dur, "lin", scoop=scoop, amp=amp)


def trill(fa: float, fb: float, dur: float, rate: float = 18.0,
          glide: float = 0.0, amp: float = 0.9) -> np.ndarray:
    """2音を高速で行き来する。glide>0 なら全体がその比率で上昇（負で下降）。"""
    n = _n(dur)
    tt = np.arange(n) / SR
    sq = np.tanh(6 * np.sin(2 * np.pi * rate * tt))        # 角を丸めた矩形
    base = np.sqrt(fa * fb) * (fb / fa) ** (0.5 * sq)
    if glide:
        base = base * (1 + glide) ** (tt / tt[-1])
    return amp * _osc(base) * _env(n)


def warble(fc: float, dur: float, rate: float = 28.0, depth: float = 0.25,
           drift: float = 1.0, amp: float = 0.85) -> np.ndarray:
    """FMでふるえる音。drift は終わりの周波数倍率。"""
    n = _n(dur)
    tt = np.arange(n) / SR
    base = fc * drift ** (tt / tt[-1])
    freq = base * (1 + depth * np.sin(2 * np.pi * rate * tt))
    return amp * _osc(freq, 0.12) * _env(n, 0.01, 0.04)


def raspberry(dur: float = 0.55, f: float = 110.0, amp: float = 0.75) -> np.ndarray:
    """低いブーイング。ノコギリ波っぽい倍音＋荒いAM。"""
    n = _n(dur)
    tt = np.arange(n) / SR
    freq = f * (1 + 0.06 * np.sin(2 * np.pi * 7 * tt)) * (0.85 ** (tt / tt[-1]))
    ph = 2 * np.pi * np.cumsum(freq) / SR
    saw = sum(np.sin(k * ph) / k for k in range(1, 14))
    am = 0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 31 * tt))
    sig = saw * am
    # 簡易ローパス（移動平均）でギラつきを抑える
    sig = np.convolve(sig, np.ones(6) / 6, mode="same")
    return amp * sig / np.max(np.abs(sig)) * _env(n, 0.02, 0.08)


def scream(dur: float = 1.5, amp: float = 1.0) -> np.ndarray:
    """高音からの長い下降。後半ほどビブラートが強くなる。"""
    n = _n(dur)
    t = np.linspace(0.0, 1.0, n)
    tt = np.arange(n) / SR
    freq = 3400 * (380 / 3400) ** (t ** 1.4)
    freq = freq * (1 + (0.01 + 0.07 * t) * np.sin(2 * np.pi * (9 + 5 * t) * tt))
    head = whistle(1800, 3600, 0.09, "out", amp=amp)
    return np.concatenate([head, amp * _osc(freq, 0.22) * _env(n, 0.005, 0.15)])


def chatter(rng: random.Random, count: int, lo: float = 1400, hi: float = 4200,
            speed: float = 1.0) -> list[np.ndarray]:
    """早口の電子音の連なり。"""
    out: list[np.ndarray] = []
    for _ in range(count):
        f = rng.uniform(lo, hi)
        d = rng.uniform(0.028, 0.065) / speed
        kind = rng.random()
        if kind < 0.55:
            out.append(blip(f, d, amp=rng.uniform(0.6, 0.95)))
        elif kind < 0.85:
            f2 = f * rng.choice([0.6, 0.75, 1.3, 1.6])
            out.append(whistle(f, f2, d * 1.6, rng.choice(["out", "in", "s"]),
                               amp=rng.uniform(0.6, 0.9)))
        else:
            out.append(trill(f, f * 1.25, d * 2.2, rate=rng.uniform(22, 34), amp=0.7))
        out.append(gap(rng.uniform(0.008, 0.035) / speed))
    return out


def gap(sec: float) -> np.ndarray:
    return np.zeros(_n(sec))


def seq(*parts) -> np.ndarray:
    flat: list[np.ndarray] = []
    for p in parts:
        if isinstance(p, list):
            flat.extend(p)
        else:
            flat.append(p)
    return np.concatenate(flat)


def finish(x: np.ndarray, peak: float = 0.85) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    x = x / m * peak
    pad = np.zeros(_n(0.04))
    return np.concatenate([pad, x, pad])


# ---------------------------------------------------------------- 感情パターン

def hello(rng):
    return seq(whistle(1500, 2600, 0.12, "out", scoop=0.1), gap(0.04),
               blip(2100, 0.05), gap(0.02), blip(2700, 0.05), gap(0.05),
               whistle(1700, 3300, 0.22, "in", vib_rate=11, vib_depth=0.02))


def happy(rng):
    return seq(blip(1800, 0.05), gap(0.02), blip(2300, 0.05), gap(0.02), blip(2900, 0.05),
               gap(0.04), trill(2400, 3100, 0.28, rate=20, glide=0.15), gap(0.05),
               chatter(rng, 4, 2000, 3800, 1.2), whistle(2200, 3600, 0.18, "in"))


def excited(rng):
    return seq(chatter(rng, 9, 1800, 4400, 1.5), trill(2600, 3500, 0.32, rate=26, glide=0.2),
               gap(0.03), whistle(1500, 3900, 0.25, "in", vib_rate=14, vib_depth=0.03),
               gap(0.03), blip(3600, 0.04), gap(0.02), blip(3900, 0.04))


def sad(rng):
    return seq(whistle(1500, 900, 0.45, "s", vib_rate=5, vib_depth=0.015), gap(0.12),
               whistle(1200, 620, 0.6, "s", vib_rate=4, vib_depth=0.02), gap(0.1),
               whistle(820, 480, 0.55, "in", vib_rate=3.5, vib_depth=0.03, amp=0.7))


def curious(rng):
    return seq(blip(1600, 0.06), gap(0.07), blip(1450, 0.06), gap(0.09),
               whistle(1300, 2900, 0.38, "in", scoop=0.05))


def surprised(rng):
    return seq(whistle(500, 3800, 0.22, "in", amp=1.0, bright=0.25), gap(0.01),
               whistle(3800, 3000, 0.12, "out"), gap(0.06),
               trill(2800, 3400, 0.2, rate=30))


def annoyed(rng):
    return seq(blip(2400, 0.05), gap(0.03), blip(1700, 0.05), gap(0.05),
               raspberry(0.5), gap(0.04), whistle(1300, 700, 0.18, "out"))


def thinking(rng):
    parts = []
    for i in range(6):
        f = 1100 + 250 * (i % 2) + rng.uniform(-60, 60)
        parts += [blip(f, 0.07, amp=0.55, scoop=0.05), gap(rng.uniform(0.12, 0.22))]
    parts.append(warble(1500, 0.35, rate=9, depth=0.06, drift=1.3, amp=0.6))
    return seq(parts)


def yes(rng):
    return seq(blip(1900, 0.06), gap(0.04), whistle(2000, 3000, 0.12, "in"))


def no(rng):
    return seq(whistle(2600, 1800, 0.12, "out"), gap(0.05), whistle(1900, 1100, 0.18, "s"))


def alarm(rng):
    return seq([trill(2200, 3200, 0.25, rate=12), gap(0.05)] * 3)


def scared(rng):
    return seq(scream(1.5))


EMOTIONS = {
    "hello": hello, "happy": happy, "excited": excited, "sad": sad,
    "curious": curious, "surprised": surprised, "annoyed": annoyed,
    "thinking": thinking, "yes": yes, "no": no, "alarm": alarm, "scared": scared,
}

# talk() でムードごとに変える音域・速さ
_MOOD = {
    "neutral": dict(lo=1300, hi=3200, speed=1.0, end=None),
    "happy":   dict(lo=1800, hi=3900, speed=1.25, end="up"),
    "excited": dict(lo=2000, hi=4400, speed=1.5, end="up"),
    "sad":     dict(lo=600,  hi=1500, speed=0.7, end="down"),
    "annoyed": dict(lo=1000, hi=2600, speed=1.1, end="buzz"),
    "curious": dict(lo=1300, hi=2900, speed=0.95, end="up"),
}


def talk(text: str, mood: str = "neutral") -> np.ndarray:
    """テキストに合わせた「おしゃべり」。同じ文は毎回同じ音になる。

    長さは文字数に比例（上限あり）、疑問文は語尾上がり、！で語尾に跳ね。
    """
    m = _MOOD.get(mood, _MOOD["neutral"])
    seed = int(hashlib.md5(f"{mood}:{text}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    stripped = text.strip()
    syllables = int(np.clip(len(stripped) * 0.45, 4, 26))
    parts: list[np.ndarray] = []
    # 文を2〜3フレーズに分け、間に短いポーズを入れて「文っぽさ」を出す
    phrases = 1 + min(2, syllables // 8)
    per = syllables // phrases
    for p in range(phrases):
        # フレーズごとに音域を少し下げる（自然な抑揚）
        drop = 1 - 0.08 * p
        parts += chatter(rng, per, m["lo"] * drop, m["hi"] * drop, m["speed"])
        if rng.random() < 0.5:
            f = rng.uniform(m["lo"], m["hi"]) * drop
            parts.append(whistle(f, f * rng.choice([0.7, 1.4]), 0.16 / m["speed"], "s",
                                 vib_rate=10, vib_depth=0.02))
        if p < phrases - 1:
            parts.append(gap(rng.uniform(0.09, 0.16)))
    end = m["end"]
    if stripped.endswith(("?", "？")):
        end = "up"
    if end == "up":
        f = m["lo"] * 1.1
        parts += [gap(0.03), whistle(f, f * 2.1, 0.26, "in")]
    elif end == "down":
        f = m["hi"]
        parts += [gap(0.05), whistle(f, f * 0.5, 0.4, "s", vib_rate=4, vib_depth=0.02)]
    elif end == "buzz":
        parts += [gap(0.04), raspberry(0.35)]
    if stripped.endswith(("!", "！")):
        parts += [gap(0.02), blip(m["hi"], 0.04), gap(0.015), blip(m["hi"] * 1.12, 0.04)]
    return seq(parts)


# ---------------------------------------------------------------- 出力・再生

def render(name: str, text: str | None = None, mood: str = "neutral",
           seed: int | None = None) -> np.ndarray:
    if name == "talk":
        return finish(talk(text or "", mood))
    rng = random.Random(seed)
    return finish(EMOTIONS[name](rng))


def save_wav(x: np.ndarray, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def play(x: np.ndarray) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        save_wav(x, f.name)
    player = ["afplay"] if sys.platform == "darwin" else ["aplay", "-q"]
    subprocess.run(player + [f.name], check=False)
    Path(f.name).unlink(missing_ok=True)


DEMO_TALK = [
    ("おはよう！今日もよろしくね！", "happy"),
    ("それ、本当にやるの？", "curious"),
    ("バッテリーが少なくなってきました。", "sad"),
    ("だから言ったじゃないか", "annoyed"),
    ("すごい！見て見て！", "excited"),
    ("了解しました。首を右に向けます。", "neutral"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="R2カップ ビープ音シンセ")
    ap.add_argument("name", choices=[*EMOTIONS, "talk", "demo"])
    ap.add_argument("text", nargs="?", default="", help="talk 用のテキスト")
    ap.add_argument("--mood", default="neutral", choices=list(_MOOD))
    ap.add_argument("--out", help="WAVの保存先（demo ではフォルダ）")
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--seed", type=int, default=None, help="感情パターンの乱数シード")
    a = ap.parse_args()

    if a.name == "demo":
        out = Path(a.out or "samples")
        for i, name in enumerate(EMOTIONS):
            p = save_wav(render(name, seed=i), out / f"{i + 1:02d}_{name}.wav")
            print(p)
        for i, (text, mood) in enumerate(DEMO_TALK):
            p = save_wav(render("talk", text, mood), out / f"talk_{i + 1:02d}_{mood}.wav")
            print(p, "←", text)
        return

    x = render(a.name, a.text, a.mood, a.seed)
    if a.out:
        print(save_wav(x, a.out))
    if a.play or not a.out:
        play(x)


if __name__ == "__main__":
    main()
