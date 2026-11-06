// R2カップ 体ファームウェア v1  (Seeed XIAO ESP32-C6 / Arduino-ESP32 3.x)
//
// Mac から USB シリアルで1行1命令を受け取り、ドームの首振り（DCモーター＋ホールセンサー）、
// LED、スピーカー（MAX98357A, I2S）を動かす。部品が未接続でも起動し、
// 基板上のLEDで命令が届いたことを確認できる。
//
// 命令（改行区切り。返事は OK / ERR / EVENT で始まる1行）
//   PING                  → PONG
//   INFO                  → 状態を表示
//   HEAD <度>             → 首を向ける（右が＋。±LIMIT_DEG まで）
//   HOME                  → ホールセンサーで正面を探す
//   CAL                   → 1周の時間を測って回転速度を記録（ホールセンサー必須）
//   SPEED <度/秒>         → 回転速度を手で設定（CAL できないとき）
//   MOTOR <-255..255>     → モーターを直接回す（テスト用。0 で停止）
//   STOP                  → 首を止める
//   LED CALM|BLINK|FAST|RED|RAINBOW|OFF
//   VOL <0..100>          → 音量
//   AUDIO <バイト数>      → 続けて 16bit/22050Hz/モノラルの PCM を送る。再生後に DONE AUDIO
//
// ボタン（頭）が押されると EVENT BUTTON を送る。

#include <Arduino.h>
#include <ESP_I2S.h>
#include <Preferences.h>

// ------------------------------------------------------------ ピン割り当て
// ドームの5本の線はテスターで調べてから確定する（D6〜D8 は仮）
const int PIN_I2S_BCLK  = D0;   // MAX98357A BCLK
const int PIN_I2S_LRC   = D1;   // MAX98357A LRC
const int PIN_I2S_DIN   = D2;   // MAX98357A DIN
const int PIN_MOT_A     = D3;   // DRV8833 AIN1
const int PIN_MOT_B     = D4;   // DRV8833 AIN2
const int PIN_HALL      = D5;   // ホールセンサー（磁石が来ると LOW）
const int PIN_BUTTON    = D6;   // 頭のボタン（押すと LOW）  ※仮
const int PIN_DOME_LED1 = D7;   // ドームのLED 1（抵抗経由） ※仮
const int PIN_DOME_LED2 = D8;   // ドームのLED 2（抵抗経由） ※仮
const int PIN_FRONT_LED = D9;   // 前面のLED（抵抗経由）
#ifdef LED_BUILTIN
const int PIN_STATUS_LED = LED_BUILTIN;
#else
const int PIN_STATUS_LED = 15;  // XIAO ESP32-C6 の基板上LED（LOW で点灯）
#endif

// ------------------------------------------------------------ 設定
const int   SAMPLE_RATE    = 22050;
const float LIMIT_DEG      = 170;    // ドームの線がねじれ切れないための上限
const float DEADBAND_DEG   = 3;      // 目標との差がこれ以下なら止める
const float SEARCH_DEG     = 200;    // HOME で左右に探す範囲
const uint32_t MOVE_TIMEOUT_MS = 6000;  // 動きっぱなし防止
const int   PWM_FREQ       = 20000;
const int   PWM_BITS       = 8;

Preferences prefs;
I2SClass i2s;
bool i2sReady = false;

float degPerSec = 120;   // CAL / SPEED で上書き
int   headDuty  = 150;   // 0-255。VM=5V なので約3V相当に抑える（元は単4×2本）
int   volume    = 60;

// ------------------------------------------------------------ 首振り
enum HeadMode { HEAD_IDLE, HEAD_TRACK, HEAD_HOMING, HEAD_CAL, HEAD_RAW };
HeadMode headMode = HEAD_IDLE;
float headDeg = 0;       // 推定角度（正面=0、右が＋）
float targetDeg = 0;
bool  homed = false;
int   motorDir = 0;      // +1 右, -1 左, 0 停止
int   homingPhase = 0;
uint32_t lastUpdateUs = 0, moveStartMs = 0, calStartMs = 0;
int   lastHall = HIGH;

void motorWrite(int dir, int duty) {
  motorDir = dir;
  if (dir > 0)      { ledcWrite(PIN_MOT_A, duty); ledcWrite(PIN_MOT_B, 0); }
  else if (dir < 0) { ledcWrite(PIN_MOT_A, 0);    ledcWrite(PIN_MOT_B, duty); }
  else              { ledcWrite(PIN_MOT_A, 255);  ledcWrite(PIN_MOT_B, 255); }  // ブレーキ
}

void motorStop() { motorWrite(0, 0); }

void startMove(HeadMode mode) {
  headMode = mode;
  moveStartMs = millis();
}

void updateHead() {
  uint32_t now = micros();
  float dt = (now - lastUpdateUs) / 1e6f;
  lastUpdateUs = now;
  if (motorDir != 0 && headMode != HEAD_RAW) headDeg += motorDir * degPerSec * dt;

  // ホールセンサーの立ち下がり（磁石が正面に来た瞬間）
  int hall = digitalRead(PIN_HALL);
  bool hallEdge = (lastHall == HIGH && hall == LOW);
  lastHall = hall;

  if (hallEdge && motorDir != 0) {
    if (headMode == HEAD_CAL) {
      if (calStartMs == 0) {
        calStartMs = millis();                 // 1回目に正面を通った：測り始め
        headDeg = 0;
        moveStartMs = millis();
      } else {
        float sec = (millis() - calStartMs) / 1000.0f;   // 2回目：ちょうど1周
        degPerSec = 360.0f / sec;
        prefs.putFloat("dps", degPerSec);
        Serial.printf("OK CAL %.1f deg/s\n", degPerSec);
        homed = true;
        headDeg = 360;                         // 右に1周した位置にいる
        targetDeg = 0;                         // 逆向きに1周して線のねじれを戻す
        startMove(HEAD_TRACK);
      }
      return;
    }
    headDeg = 0;
    if (!homed) Serial.println("EVENT HOMED");
    homed = true;
    if (headMode == HEAD_HOMING) {
      motorStop();
      headMode = HEAD_IDLE;
      targetDeg = 0;
      Serial.println("OK HOME");
      return;
    }
  }

  if (headMode == HEAD_IDLE || headMode == HEAD_RAW) return;

  if (millis() - moveStartMs > MOVE_TIMEOUT_MS) {
    motorStop();
    Serial.println(headMode == HEAD_HOMING ? "ERR HOME no hall sensor found" : "ERR HEAD timeout");
    headMode = HEAD_IDLE;
    return;
  }

  if (headMode == HEAD_HOMING) {
    // 右へ SEARCH_DEG、だめなら左へ SEARCH_DEG 探す（時間ベースの推定で）
    float goal = (homingPhase == 0) ? SEARCH_DEG : -SEARCH_DEG;
    if ((homingPhase == 0 && headDeg >= goal) || (homingPhase == 1 && headDeg <= goal)) {
      if (homingPhase == 0) { homingPhase = 1; moveStartMs = millis(); }
      else { motorStop(); headMode = HEAD_IDLE; headDeg = 0; Serial.println("ERR HOME no hall sensor found"); return; }
    }
    motorWrite(homingPhase == 0 ? +1 : -1, headDuty);
    return;
  }

  if (headMode == HEAD_CAL) { motorWrite(+1, headDuty); return; }

  float err = targetDeg - headDeg;
  if (fabsf(err) <= DEADBAND_DEG) {
    motorStop();
    headMode = HEAD_IDLE;
    return;
  }
  // 近づいたら減速して行き過ぎを減らす
  int duty = fabsf(err) < 20 ? max(90, headDuty * 2 / 3) : headDuty;
  motorWrite(err > 0 ? +1 : -1, duty);
}

// ------------------------------------------------------------ LED
enum LedMode { LED_OFF, LED_CALM, LED_BLINK, LED_FAST, LED_RED, LED_RAINBOW };
LedMode ledMode = LED_CALM;

void ledOut(int pin, int v) { ledcWrite(pin, constrain(v, 0, 255)); }

void updateLeds() {
  uint32_t t = millis();
  int a = 0, b = 0, f = 0;
  switch (ledMode) {
    case LED_OFF: break;
    case LED_CALM: {
      float s = 0.5f + 0.5f * sinf(t / 700.0f);
      a = 40 + 160 * s; b = 40 + 160 * (1 - s); f = 60;
      break;
    }
    case LED_BLINK: a = b = ((t / 500) % 2) ? 255 : 0; f = a; break;
    case LED_FAST:  a = ((t / 70) % 3) ? 255 : 0; b = ((t / 90) % 2) ? 255 : 0; f = 255; break;
    case LED_RED:   a = b = 0; f = ((t / 150) % 2) ? 255 : 0; break;
    case LED_RAINBOW: {
      int phase = (t / 120) % 3;
      a = phase == 0 ? 255 : 30; b = phase == 1 ? 255 : 30; f = phase == 2 ? 255 : 30;
      break;
    }
  }
  ledOut(PIN_DOME_LED1, a);
  ledOut(PIN_DOME_LED2, b);
  ledOut(PIN_FRONT_LED, f);
  // 基板上のLEDは LOW で点灯。ドームLED1と同じ明るさにする
  ledOut(PIN_STATUS_LED, 255 - a);
}

// ------------------------------------------------------------ ボタン
int lastButton = HIGH;
uint32_t buttonChangedMs = 0;

void updateButton() {
  int v = digitalRead(PIN_BUTTON);
  if (v != lastButton && millis() - buttonChangedMs > 30) {
    buttonChangedMs = millis();
    lastButton = v;
    if (v == LOW) Serial.println("EVENT BUTTON");
  }
}

void tick() { updateHead(); updateLeds(); updateButton(); }

// ------------------------------------------------------------ 音
void playAudio(long nbytes) {
  if (!i2sReady) {
    // アンプが無くてもデータは読み捨てて、通信を崩さない
  }
  static uint8_t buf[1024];
  long left = nbytes;
  uint32_t lastData = millis();
  while (left > 0) {
    int want = min((long)sizeof(buf), left);
    want &= ~1;  // 16bit 単位
    if (want == 0) want = 1;
    int got = Serial.readBytes(buf, want);
    if (got <= 0) {
      if (millis() - lastData > 2000) { Serial.println("ERR AUDIO timeout"); return; }
      tick();
      continue;
    }
    lastData = millis();
    left -= got;
    int16_t *s = (int16_t *)buf;
    for (int i = 0; i < got / 2; i++) s[i] = (int16_t)((int32_t)s[i] * volume / 100);
    if (i2sReady) i2s.write(buf, got);
    tick();  // 鳴らしながら首とLEDも動かす
  }
  Serial.println("DONE AUDIO");
}

// ------------------------------------------------------------ 命令
LedMode parseLed(const String &s) {
  if (s == "CALM") return LED_CALM;
  if (s == "BLINK") return LED_BLINK;
  if (s == "FAST") return LED_FAST;
  if (s == "RED") return LED_RED;
  if (s == "RAINBOW") return LED_RAINBOW;
  return LED_OFF;
}

void handle(String line) {
  line.trim();
  if (line.length() == 0) return;
  int sp = line.indexOf(' ');
  String cmd = sp < 0 ? line : line.substring(0, sp);
  String arg = sp < 0 ? "" : line.substring(sp + 1);
  cmd.toUpperCase();
  arg.trim();

  if (cmd == "PING") { Serial.println("PONG"); }
  else if (cmd == "INFO") {
    Serial.printf("OK INFO fw=1 head=%.0f target=%.0f homed=%d dps=%.1f duty=%d vol=%d hall=%d amp=%d\n",
                  headDeg, targetDeg, homed, degPerSec, headDuty, volume, digitalRead(PIN_HALL), i2sReady);
  }
  else if (cmd == "HEAD") {
    targetDeg = constrain(arg.toFloat(), -LIMIT_DEG, LIMIT_DEG);
    startMove(HEAD_TRACK);
    Serial.printf("OK HEAD %.0f\n", targetDeg);
  }
  else if (cmd == "HOME") { homingPhase = 0; startMove(HEAD_HOMING); Serial.println("OK HOMING"); }
  else if (cmd == "CAL")  { calStartMs = 0; startMove(HEAD_CAL); moveStartMs = millis(); Serial.println("OK CAL start"); }
  else if (cmd == "SPEED") {
    float v = arg.toFloat();
    if (v > 5 && v < 2000) { degPerSec = v; prefs.putFloat("dps", v); Serial.printf("OK SPEED %.1f\n", v); }
    else Serial.println("ERR SPEED");
  }
  else if (cmd == "DUTY") {
    int v = arg.toInt();
    if (v >= 60 && v <= 255) { headDuty = v; prefs.putInt("duty", v); Serial.printf("OK DUTY %d\n", v); }
    else Serial.println("ERR DUTY 60-255");
  }
  else if (cmd == "MOTOR") {
    int v = constrain(arg.toInt(), -255, 255);
    headMode = v == 0 ? HEAD_IDLE : HEAD_RAW;
    if (v == 0) motorStop(); else motorWrite(v > 0 ? 1 : -1, abs(v));
    Serial.printf("OK MOTOR %d\n", v);
  }
  else if (cmd == "STOP") { motorStop(); headMode = HEAD_IDLE; Serial.println("OK STOP"); }
  else if (cmd == "LED")  { arg.toUpperCase(); ledMode = parseLed(arg); Serial.println("OK LED " + arg); }
  else if (cmd == "VOL")  { volume = constrain(arg.toInt(), 0, 100); prefs.putInt("vol", volume); Serial.printf("OK VOL %d\n", volume); }
  else if (cmd == "AUDIO") { playAudio(arg.toInt()); }
  else { Serial.println("ERR unknown " + cmd); }
}

// ------------------------------------------------------------ 起動
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);

  pinMode(PIN_HALL, INPUT_PULLUP);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  for (int pin : {PIN_MOT_A, PIN_MOT_B, PIN_DOME_LED1, PIN_DOME_LED2, PIN_FRONT_LED, PIN_STATUS_LED}) {
    ledcAttach(pin, PWM_FREQ, PWM_BITS);
  }
  motorWrite(0, 0);
  ledcWrite(PIN_MOT_A, 0); ledcWrite(PIN_MOT_B, 0);  // 起動時は空転（ブレーキ無し）

  prefs.begin("r2cup", false);
  degPerSec = prefs.getFloat("dps", degPerSec);
  headDuty  = prefs.getInt("duty", headDuty);
  volume    = prefs.getInt("vol", volume);

  i2s.setPins(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DIN);
  i2sReady = i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);

  lastHall = digitalRead(PIN_HALL);
  lastUpdateUs = micros();
  Serial.println("EVENT READY r2cup-body fw=1");
}

String lineBuf;

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handle(lineBuf); lineBuf = ""; }
    else if (c != '\r' && lineBuf.length() < 120) lineBuf += c;
  }
  tick();
  delay(2);
}
