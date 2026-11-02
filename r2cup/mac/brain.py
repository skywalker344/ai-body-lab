"""R2カップの頭脳：会話の文脈を踏まえて「どう鳴くか・どう動くか」を Claude に決めてもらう。

R2は言葉を話さない。Claude が返すのは鳴き声の種類・おしゃべりの長さ・首の向き・LED だけ。
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass

import r2voice

MODELS = {"opus": "claude-opus-5-5", "haiku": "claude-haiku-5-5"}
MAX_TURNS = 60  # これを超えたら会話を新しく始める（古いターンを途中で削らない）

REACTIONS = ["none", *r2voice.EMOTIONS]
MOODS = list(r2voice._MOOD)
LENGTHS = ["none", "short", "medium", "long"]
LEDS = ["calm", "blink", "fast", "red", "rainbow"]

SYSTEM_PROMPT = f"""\
あなたは「R2カップ」。持ち主の机の上のコーヒーカップに収まった、小さなアストロメク・ドロイドです。
持ち主が日本語で話しかけます。あなたは言葉を一切話せず、電子音（ビープ音）と首振りとライトだけで返事をします。

# 性格
- 好奇心旺盛。新しい話題や物には身を乗り出す（首を向ける・疑問の音）
- 少し生意気。からかわれたり無茶を言われたら、ブーイングや不満の音で言い返す
- でも持ち主には忠実な相棒。頼まれごとには基本「はい」、落ち込んでいたら励ます

# 返し方
会話の流れを覚えておき、文脈に合った反応を選んでください。毎回同じ反応にならないよう、間や強弱に変化をつけます。
- meaning: もしR2が言葉を話せたら言っていそうな一言（日本語、40字以内）。音には出ません
- reaction: 最初に鳴らす感情の鳴き声。不要なら none
  {", ".join(r2voice.EMOTIONS)}
- talk_mood / talk_length: reaction のあとに続ける「おしゃべり」の雰囲気と長さ。短い相づちなら none か short
- head: 首の向き（度）。-90=左、0=正面、90=右。基本は 0 付近。興味・照れ・そっぽを向く等で動かす
- led: ロジックライトの光り方。calm=通常 / blink=ゆっくり点滅 / fast=高速点滅（興奮・驚き）/ red=警告・不満 / rainbow=大喜び
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "meaning": {"type": "string"},
        "reaction": {"type": "string", "enum": REACTIONS},
        "talk_mood": {"type": "string", "enum": MOODS},
        "talk_length": {"type": "string", "enum": LENGTHS},
        "head": {"type": "integer"},
        "led": {"type": "string", "enum": LEDS},
    },
    "required": ["meaning", "reaction", "talk_mood", "talk_length", "head", "led"],
    "additionalProperties": False,
}

_SYLLABLES = {"short": 5, "medium": 11, "long": 20}


@dataclass
class Reply:
    meaning: str
    reaction: str
    talk_mood: str
    talk_length: str
    head: int
    led: str

    @classmethod
    def from_json(cls, data: dict) -> "Reply":
        r = cls(**{k: data[k] for k in SCHEMA["required"]})
        r.head = max(-90, min(90, int(r.head)))
        return r

    def sound(self):
        """返事の音声波形を作る。"""
        parts = []
        if self.reaction != "none":
            parts.append(r2voice.EMOTIONS[self.reaction](random.Random()))
        if self.talk_length != "none":
            if parts:
                parts.append(r2voice.gap(0.12))
            parts.append(r2voice.talk(self.meaning, self.talk_mood,
                                      syllables=_SYLLABLES[self.talk_length]))
        if not parts:  # 何も鳴らさないのは寂しいので短い相づち
            parts.append(r2voice.EMOTIONS["yes"](random.Random()))
        return r2voice.finish(r2voice.seq(parts))


FALLBACK_CONFUSED = Reply("…よくわからなかった", "curious", "curious", "none", 15, "blink")


class Brain:
    def __init__(self, effort: str = "low", model: str = "opus"):
        import anthropic  # API を使うときだけ読み込む

        self.client = anthropic.Anthropic()
        self.effort = effort
        self.model = MODELS[model]
        self.messages: list = []

    def reply(self, heard: str) -> Reply:
        if len(self.messages) >= MAX_TURNS * 2:
            self.messages = []  # 長くなったら新しい会話として始め直す
        self.messages.append({"role": "user", "content": heard})
        extra = {}
        if self.model == MODELS["opus"]:
            # 安全分類器が誤って断ったときは推奨モデルで自動再実行（Haikuは非対応）
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=self.messages,
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            **extra,
        )
        # 思考ブロックも含めてそのまま履歴に積む（途中を書き換えない）
        self.messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            return Reply("それはちょっと…", "no", "annoyed", "short", -20, "red")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return Reply.from_json(json.loads(text))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return FALLBACK_CONFUSED


class FakeBrain:
    """APIキーなしで動作確認するためのダミー。"""

    def __init__(self, *_, **__):
        self.rng = random.Random()

    def reply(self, heard: str) -> Reply:
        mood = "curious" if heard.rstrip().endswith(("?", "？")) else self.rng.choice(MOODS)
        return Reply(
            meaning=heard[:40],
            reaction=self.rng.choice(REACTIONS),
            talk_mood=mood,
            talk_length=self.rng.choice(LENGTHS[1:]),
            head=self.rng.randint(-45, 45),
            led=self.rng.choice(LEDS),
        )
