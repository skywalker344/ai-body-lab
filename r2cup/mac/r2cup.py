#!/usr/bin/env python3
"""R2カップ 会話ループ

  聞く（マイク → Whisper） → 考える（Claude） → 返す（ビープ音＋首振り＋LED）

使い方:
  python r2cup.py                 # マイクで常時待ち受け（話し終わりを自動検出）
  python r2cup.py --ptt           # Enter を押してから話す
  python r2cup.py --text          # キーボード入力で会話（マイク・Whisper不要）
  python r2cup.py --text --fake   # APIも使わずに動作確認
  python r2cup.py --port /dev/cu.usbmodem1101   # マイコンにも命令を送る
  python r2cup.py --debug         # R2が心の中で言っていること等を表示
  python r2cup.py --model opus    # 文脈の読みが深いモデル（標準は速い haiku）

必要: export ANTHROPIC_API_KEY=...
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import numpy as np

import r2voice
from brain import Brain, FakeBrain, Reply

MIC_SR = 16000
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

# Whisper が無音や雑音から作りがちな幻聴フレーズ
_HALLUCINATIONS = ("ご視聴ありがとうございました", "チャンネル登録", "おやすみなさい。", "字幕")


# ---------------------------------------------------------------- 体（マイコン）

class Body:
    """マイコンへ1行1命令のテキストを送る。ポート未指定なら表示だけ。"""

    def __init__(self, port: str | None, debug: bool):
        self.ser = None
        self.debug = debug
        if port:
            import serial  # pyserial

            self.ser = serial.Serial(port, 115200, timeout=0.1)
            time.sleep(1.5)  # 接続直後のリセット待ち

    def send(self, line: str) -> None:
        if self.debug or not self.ser:
            print(f"  [体] {line}")
        if self.ser:
            self.ser.write((line + "\n").encode())

    def act(self, r: Reply) -> None:
        self.send(f"HEAD {r.head}")
        self.send(f"LED {r.led.upper()}")


# ---------------------------------------------------------------- 耳

class Ears:
    def __init__(self, ptt: bool):
        import sounddevice  # noqa: F401  インストール確認を先にする
        import mlx_whisper  # noqa: F401

        self.ptt = ptt
        self.noise = self._measure_noise()

    def _record(self, sec: float) -> np.ndarray:
        import sounddevice as sd

        x = sd.rec(int(sec * MIC_SR), samplerate=MIC_SR, channels=1, dtype="float32")
        sd.wait()
        return x[:, 0]

    def _measure_noise(self) -> float:
        print("周囲の音を測っています…（1秒静かに）")
        x = self._record(1.0)
        return float(np.sqrt(np.mean(x ** 2)))

    def listen(self) -> np.ndarray | None:
        """話し始めを待ち、0.9秒黙ったら終了。最長15秒。"""
        import sounddevice as sd

        if self.ptt:
            input("\n[Enter] を押して話す > ")
        else:
            print("\n…聞いています")
        block = int(0.05 * MIC_SR)
        thresh = max(self.noise * 3.0, 0.008)
        chunks: list[np.ndarray] = []
        speaking = False
        silent = 0.0
        started = time.time()
        with sd.InputStream(samplerate=MIC_SR, channels=1, dtype="float32",
                            blocksize=block) as stream:
            while True:
                data, _ = stream.read(block)
                x = data[:, 0].copy()
                loud = float(np.sqrt(np.mean(x ** 2))) > thresh
                if not speaking:
                    chunks = (chunks + [x])[-6:]  # 話し始めの直前0.3秒を残す
                    if loud:
                        speaking, started = True, time.time()
                    elif self.ptt and time.time() - started > 8:
                        return None
                    continue
                chunks.append(x)
                silent = 0.0 if loud else silent + 0.05
                if silent > 0.9 or time.time() - started > 15:
                    break
        audio = np.concatenate(chunks)
        return audio if len(audio) > MIC_SR * 0.4 else None

    def transcribe(self, audio: np.ndarray) -> str:
        import mlx_whisper

        out = mlx_whisper.transcribe(audio, path_or_hf_repo=WHISPER_MODEL, language="ja")
        text = out.get("text", "").strip()
        if not text or any(h in text for h in _HALLUCINATIONS):
            return ""
        return text


# ---------------------------------------------------------------- 考える

# 考えている間の首の動き（左右にゆっくりきょろきょろ）。音は鳴らさない
THINKING_LOOK = [20, -15, 10, -20]
THINKING_STEP = 0.7  # 秒


def think(brain, body, heard: str) -> Reply:
    """Claude に問い合わせる。待っている間はLEDを点滅させ、首をきょろきょろ動かす。"""
    result: dict = {}

    def ask():
        try:
            result["reply"] = brain.reply(heard)
        except Exception as e:  # ネット切断など。止まらずに悲しい音で知らせる
            print(f"  [エラー] {type(e).__name__}: {e}", file=sys.stderr)
            if type(e).__name__ == "AuthenticationError":
                print("  → APIキーが正しくありません。export ANTHROPIC_API_KEY=... を確認し、"
                      "ANTHROPIC_AUTH_TOKEN が残っていれば unset してください", file=sys.stderr)
            result["reply"] = Reply("通信がうまくいかない…", "sad", "sad", "short", 0, "red")

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    body.send("LED BLINK")
    i = 0
    while worker.is_alive():
        body.send(f"HEAD {THINKING_LOOK[i % len(THINKING_LOOK)]}")
        i += 1
        worker.join(THINKING_STEP)
    return result["reply"]


# ---------------------------------------------------------------- メイン

def main() -> None:
    ap = argparse.ArgumentParser(description="R2カップ 会話ループ")
    ap.add_argument("--text", action="store_true", help="キーボード入力で会話する")
    ap.add_argument("--ptt", action="store_true", help="Enter を押してから話す")
    ap.add_argument("--fake", action="store_true", help="Claude API を使わずダミー応答")
    ap.add_argument("--port", help="マイコンのシリアルポート")
    ap.add_argument("--model", default="haiku", choices=["opus", "haiku"],
                    help="opus=文脈の読みが深い / haiku=返事が速い")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    brain = FakeBrain() if a.fake else Brain(effort=a.effort, model=a.model)
    body = Body(a.port, a.debug)
    ears = None if a.text else Ears(a.ptt)

    r2voice.play(r2voice.render("hello"))
    body.send("LED CALM")
    print("R2カップ起動。終了は Ctrl+C")

    try:
        while True:
            if ears:
                audio = ears.listen()
                if audio is None:
                    continue
                heard = ears.transcribe(audio)
                if not heard:
                    continue
                print(f"あなた: {heard}")
            else:
                heard = input("\nあなた > ").strip()
                if not heard:
                    continue

            t0 = time.time()
            reply = think(brain, body, heard)

            if a.debug:
                print(f"  [R2の心の声] {reply.meaning}  ({time.time() - t0:.1f}秒)")
                print(f"  [音] {reply.reaction} → {reply.talk_mood}/{reply.talk_length}")
            body.act(reply)
            r2voice.play(reply.sound())
    except (KeyboardInterrupt, EOFError):
        body.send("HEAD 0")
        body.send("LED OFF")
        r2voice.play(r2voice.render("sad"))
        print("\nまたね")


if __name__ == "__main__":
    main()
