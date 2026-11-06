# R2カップ 体ファームウェア（XIAO ESP32-C6）

Hamee の冷蔵庫R2-D2 の中身を入れ替えるための、体側のプログラム。
Mac の `mac/r2cup.py` から USB で命令と音を受け取り、首振り・LED・スピーカーを動かす。

## 1. Arduino IDE の準備（初回だけ）
1. Arduino IDE 2 をインストール（https://www.arduino.cc/en/software）
2. 「Arduino IDE → 設定（Settings）」の「追加のボードマネージャのURL」に次を入れる
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. 左の「ボードマネージャ」で `esp32`（by Espressif Systems）を検索し、**3.x** をインストール
4. XIAO ESP32-C6 を USB-C で Mac につなぐ
5. 「ツール → ボード → esp32 → XIAO_ESP32C6」を選ぶ
6. 「ツール → USB CDC On Boot」を **Enabled** にする（Serial が USB で使えるように）
7. 「ツール → ポート」で `/dev/cu.usbmodem…` を選ぶ

## 2. 書き込みと動作確認（部品なしでOK）
1. `firmware/r2cup_body/r2cup_body.ino` を開いて「書き込み（→）」
2. 「シリアルモニタ」を 115200 bps・改行 LF で開く
3. 次を打って確かめる
   - `PING` → `PONG`
   - `LED BLINK` → XIAO の小さなLED（黄色）が1秒ごとに点滅
   - `LED CALM` → ゆっくり明るさが変わる
   - `INFO` → 状態が表示される
4. シリアルモニタを閉じてから、Mac で会話ループとつなぐ
   ```
   ls /dev/cu.usbmodem*          # ポート名を調べる
   python r2cup.py --text --debug --port /dev/cu.usbmodemXXXX --speaker mac
   ```
   返事のたびに XIAO のLEDの光り方が変わればOK（アンプが無いうちは `--speaker mac`）

## 3. ピン割り当て（v1）
| XIAO | 用途 | つなぐ先 |
|---|---|---|
| D0 | I2S BCLK | MAX98357A BCLK |
| D1 | I2S LRC | MAX98357A LRC |
| D2 | I2S DIN | MAX98357A DIN |
| D3 | モーター IN1 | DRV8833 AIN1 |
| D4 | モーター IN2 | DRV8833 AIN2 |
| D5 | ホールセンサー（磁石でLOW） | センサーの OUT |
| D6 | 頭のボタン（押すとLOW）※仮 | ドームの線（テスターで特定） |
| D7 | ドームLED 1 ※仮 | 抵抗（100〜220Ω）経由でドームの線 |
| D8 | ドームLED 2 ※仮 | 同上 |
| D9 | 前面LED | 抵抗（100〜220Ω）経由 |
| D10 | 予備 | |
| 5V | 電源 | MAX98357A VIN・DRV8833 VM・ホールセンサー VCC |
| GND | 共通 | 全部の GND |

- DRV8833 の AOUT1/AOUT2 → モーター（元の M+ / M-）
- MAX98357A の +/- → スピーカー（元の SPR の2本）
- モーターは元が単4×2本（3V）なので、5V から PWM で約60%に絞っている（`DUTY` で調整）

## 4. 命令一覧
| 命令 | 内容 |
|---|---|
| `PING` | `PONG` を返す |
| `INFO` | 角度・速度・音量などを表示 |
| `HEAD <度>` | 首を向ける（右が＋、±170°まで） |
| `HOME` | ホールセンサーで正面を探す |
| `CAL` | 1周の時間を測って回転速度を保存（ホールセンサーが必要。1周回るので注意） |
| `SPEED <度/秒>` | 回転速度を手で設定 |
| `DUTY <60〜255>` | モーターの強さ |
| `MOTOR <-255〜255>` | モーターを直接回す（テスト用。`MOTOR 0` で止める） |
| `STOP` | 止める |
| `LED CALM/BLINK/FAST/RED/RAINBOW/OFF` | 光り方 |
| `VOL <0〜100>` | 音量 |
| `AUDIO <バイト数>` | 続けて 16bit・22050Hz・モノラルの音を送る。終わると `DONE AUDIO` |

頭のボタンが押されると `EVENT BUTTON` を返す。

## 注意
- ドームの線は回転軸の中を通っているので、回しすぎるとねじれて切れる。`HEAD` は ±170° に制限している
- `MOTOR` 命令は制限なしで回るので、テストは短く
