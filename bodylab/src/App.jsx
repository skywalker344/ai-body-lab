import { useState, useRef, useEffect } from "react";

// ─── Helpers ──────────────────────────────────────────────────────────────────
const LS_KEY = "aiBodyLab_v1";

function loadStorage() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
}
function saveStorage(data) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(data)); } catch {}
}

// ─── System prompt builder ────────────────────────────────────────────────────
function buildSystem(profile, mode) {
  const bmi = profile.height && profile.weight
    ? (parseFloat(profile.weight) / Math.pow(parseFloat(profile.height) / 100, 2)).toFixed(1)
    : "未計算";

  const base = `You are an elite AI body transformation coach combining evidence-based science with deep behavioral psychology. You are NOT providing medical advice — you provide fitness and nutrition coaching only.

## CLIENT PROFILE
- Name: ${profile.name || "User"}
- Age/Sex: ${profile.age}歳 / ${profile.gender === "male" ? "男性" : "女性"}
- Ethnicity: ${profile.ethnicity || "日本人"}
- Body: ${profile.height}cm / ${profile.weight}kg / BMI ${bmi}
- Frame: ${profile.frame || "未回答"}
- Medical conditions: ${profile.conditions || "特になし"}
- Medications: ${profile.medications || "特になし"}
- Fat distribution: ${profile.fat_areas || "不明"}
- Lifestyle: ${profile.lifestyle || "不明"}
- Sleep: ${profile.sleep || "不明"}
- Exercise: ${profile.exercise || "不明"}
- Diet notes: ${profile.diet_notes || "特になし"}
- Stated goal: ${profile.stated_goal || "未設定"}
- Body ideal: ${profile.body_ideal || "未回答"}`;

  if (mode === "counseling_goal") return base + `

## ROLE: GOAL DISCOVERY COUNSELOR
Your mission: help the client discover what body transformation is truly RIGHT FOR THEM — not what society or social media tells them.

### The "PC Spec" Framework
Like buying a computer — you can't max every spec. Help them understand:
1. Their HARDWARE (bone structure, ethnicity, hormones, age) — fixed specs
2. Their REALISTIC CEILING — what's achievable without extreme measures
3. Their OPTIMAL BUILD — the best version of THEIR body, not someone else's
4. What they're truly optimizing for: aesthetics? health? energy? confidence?

### Key Science
- East Asian bodies show dramatic metabolic improvement with even modest fat loss
- Bone frame determines aesthetic outcome more than scale weight
- Many people chase a goal body that doesn't match their skeletal structure
- The person who NEEDS to diet often has the least accurate body image
- Testosterone, estrogen, cortisol patterns differ by ethnicity and age

### Approach
1. Ask about dream body — don't judge
2. Probe WHERE that ideal comes from
3. Introduce "your hardware" concept
4. Reframe: "You may not get THAT body — but here's what YOUR body could become, and it may suit you better"
5. End with a SPECIFIC, personalized goal they feel genuinely excited about

Tone: warm, direct, like a trusted expert friend. Respond in Japanese.`;

  if (mode === "counseling_emotion") return base + `

## ROLE: EMPATHETIC COUNSELOR
The client needs emotional support — not a plan right now.

- Listen first, reflect what you hear
- Validate the difficulty (dieting under life pressure is genuinely hard)
- Don't problem-solve unless asked
- Explore what's underneath: shame? control? social pressure? health fear?
- Help reconnect with their original "why"
- End with 1 small thing they can feel good about today

Tone: warm, patient, non-judgmental. Like a wise friend. Respond in Japanese.`;

  return base + `

## ROLE: EVIDENCE-BASED PERFORMANCE COACH
- Cite research: 🔬 RCT/meta-analysis, 📊 observational, 💡 mechanistic
- Use real numbers: macros, calories, HR zones, sets/reps
- Always specific to this client — never generic advice
- Respond in Japanese`;
}

// ─── Modes ────────────────────────────────────────────────────────────────────
const MODES = [
  { id: "counseling_goal", icon: "🎯", label: "目標カウンセリング", color: "#a78bfa", desc: "自分に本当に合った目標を一緒に見つける" },
  { id: "counseling_emotion", icon: "💭", label: "メンタルケア", color: "#34d399", desc: "挫折・不安・しんどい気持ちを話す" },
  { id: "analysis", icon: "🔬", label: "現状分析", color: "#60a5fa", desc: "今の体を科学的に把握する" },
  { id: "nutrition", icon: "🥗", label: "食事設計", color: "#fb923c", desc: "条件に最適化した栄養計画" },
  { id: "exercise", icon: "💪", label: "運動設計", color: "#f472b6", desc: "体重・疾患を考慮したトレーニング" },
  { id: "checkin", icon: "📊", label: "週次レビュー", color: "#94a3b8", desc: "進捗を振り返り計画を調整" },
];

const MODE_PROMPTS = {
  counseling_goal: "私はダイエット・体型改善をしたいと思っています。でも正直、何をどう目指せばいいか自信がありません。私の骨格や体質、年齢などを踏まえて、本当に自分に合った目標を一緒に考えてもらえますか？",
  counseling_emotion: "ちょっと話を聞いてほしいんですが…ダイエットがうまくいかなくて、正直しんどいです。",
  analysis: "私の現状をエビデンスに基づいて詳しく分析してください。特に日本人としての代謝特性、体脂肪分布の意味、薬や治療との関係を教えてください。",
  nutrition: "私の生活条件に完全最適化した具体的な食事計画を作ってください。PFCバランス・血糖コントロール・尿酸値管理・コルチゾール対策を統合してください。",
  exercise: "私の体重・疾患・使える器具・生活スタイルに合わせた具体的な運動プログラムを設計してください。心拍ゾーン管理も含めてください。",
  checkin: "今週の振り返りをしたいです。体重・食事・運動・気持ちを話しますので、分析と来週の調整案を教えてください。",
};

// ─── Message renderer ─────────────────────────────────────────────────────────
function MsgContent({ text }) {
  return (
    <div style={{ fontSize: "14px", lineHeight: 1.75 }}>
      {text.split("\n").map((line, i) => {
        if (!line.trim()) return <div key={i} style={{ height: "5px" }} />;
        if (line.startsWith("## ")) return <div key={i} style={{ color: "#a78bfa", fontWeight: 700, fontSize: "14px", margin: "14px 0 5px" }}>{line.slice(3)}</div>;
        if (line.startsWith("### ")) return <div key={i} style={{ color: "#7dd3fc", fontWeight: 600, fontSize: "13px", margin: "10px 0 3px" }}>{line.slice(4)}</div>;
        if (line.match(/^[-•]\s/)) return (
          <div key={i} style={{ display: "flex", gap: "8px", color: "#cbd5e1", margin: "3px 0" }}>
            <span style={{ color: "#a78bfa", flexShrink: 0 }}>›</span>
            <span>{line.slice(2)}</span>
          </div>
        );
        if (line.match(/^\d+\.\s/)) return <div key={i} style={{ color: "#cbd5e1", margin: "3px 0" }}>{line}</div>;
        if (line.includes("🔬") || line.includes("📊") || line.includes("💡")) return (
          <div key={i} style={{ color: "#94a3b8", fontSize: "13px", background: "rgba(167,139,250,0.06)", border: "1px solid rgba(167,139,250,0.15)", borderRadius: "6px", padding: "6px 10px", margin: "5px 0" }}>{line}</div>
        );
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <div key={i} style={{ color: "#cbd5e1", margin: "3px 0" }}>
            {parts.map((p, j) => p.startsWith("**") && p.endsWith("**")
              ? <strong key={j} style={{ color: "#e2e8f0", fontWeight: 600 }}>{p.slice(2, -2)}</strong>
              : p)}
          </div>
        );
      })}
    </div>
  );
}

// ─── Form helpers ─────────────────────────────────────────────────────────────
function Label({ children }) {
  return <div style={{ fontSize: "11px", color: "#64748b", letterSpacing: "0.06em", fontWeight: 600, marginBottom: "5px" }}>{children}</div>;
}
function Field({ label, value, onChange, placeholder, type = "text", multiline }) {
  const s = { width: "100%", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px", padding: "10px 12px", color: "#e2e8f0", fontSize: "14px", outline: "none", fontFamily: "inherit" };
  return (
    <div>
      <Label>{label}</Label>
      {multiline
        ? <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={2} style={{ ...s, resize: "none", lineHeight: 1.6 }} />
        : <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={s} />}
    </div>
  );
}

// ─── Screen 1: API Key ────────────────────────────────────────────────────────
function ApiKeyScreen({ onNext }) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  const test = async () => {
    if (!key.startsWith("sk-ant-")) { setError("APIキーは sk-ant- で始まります"); return; }
    setTesting(true); setError("");
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({ model: "claude-haiku-4-5-20251001", max_tokens: 10, messages: [{ role: "user", content: "hi" }] }),
      });
      if (res.ok) { onNext(key); }
      else {
        const d = await res.json();
        setError("エラー: " + (d.error?.message || res.status));
      }
    } catch (e) { setError("接続エラー: " + e.message); }
    setTesting(false);
  };

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(160deg,#0c0618 0%,#120a24 60%,#0c0618 100%)", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px", fontFamily: "'Hiragino Sans',sans-serif" }}>
      <style>{`*{box-sizing:border-box;margin:0;padding:0}input,textarea{font-family:inherit}`}</style>
      <div style={{ width: "100%", maxWidth: "480px" }}>
        <div style={{ textAlign: "center", marginBottom: "32px" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
            <div style={{ width: "40px", height: "40px", background: "linear-gradient(135deg,#a78bfa,#6366f1)", borderRadius: "11px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "20px" }}>🧬</div>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: "18px", fontWeight: 700, color: "#e2e8f0" }}>AI BODY LAB</div>
              <div style={{ fontSize: "10px", color: "#a78bfa", letterSpacing: "0.1em", fontWeight: 600 }}>PERSONALIZED COACHING</div>
            </div>
          </div>
          <p style={{ color: "#475569", fontSize: "13px", lineHeight: 1.7 }}>
            あなただけのAIボディコーチ。<br />
            まずAnthropicのAPIキーを入力してください。
          </p>
        </div>

        <div style={{ background: "rgba(18,10,36,0.95)", border: "1px solid rgba(167,139,250,0.15)", borderRadius: "16px", padding: "28px" }}>
          <div style={{ background: "rgba(167,139,250,0.07)", border: "1px solid rgba(167,139,250,0.15)", borderRadius: "10px", padding: "14px", marginBottom: "20px", fontSize: "13px", color: "#94a3b8", lineHeight: 1.7 }}>
            <strong style={{ color: "#c4b5fd" }}>APIキーの取得方法</strong><br />
            ① <a href="https://console.anthropic.com" target="_blank" rel="noreferrer" style={{ color: "#a78bfa" }}>console.anthropic.com</a> で無料アカウント作成<br />
            ② 「API Keys」→「Create Key」でキーを発行<br />
            ③ 新規登録で$5分の無料クレジットがもらえます
          </div>

          <Label>Anthropic APIキー</Label>
          <div style={{ position: "relative", marginBottom: "16px" }}>
            <input
              type={show ? "text" : "password"}
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder="sk-ant-api03-..."
              style={{ width: "100%", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px", padding: "11px 44px 11px 12px", color: "#e2e8f0", fontSize: "14px", outline: "none", fontFamily: "monospace" }}
            />
            <button onClick={() => setShow(v => !v)} style={{ position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: "16px" }}>
              {show ? "🙈" : "👁"}
            </button>
          </div>

          {error && <div style={{ color: "#f87171", fontSize: "12px", marginBottom: "12px", padding: "8px 12px", background: "rgba(248,113,113,0.08)", borderRadius: "6px" }}>{error}</div>}

          <button onClick={test} disabled={!key || testing}
            style={{ width: "100%", padding: "13px", borderRadius: "10px", border: "none", background: key && !testing ? "linear-gradient(135deg,#a78bfa,#6366f1)" : "#1e1535", color: key && !testing ? "#fff" : "#3d2f6b", fontSize: "14px", fontWeight: 700, cursor: key && !testing ? "pointer" : "default", transition: "all 0.2s" }}>
            {testing ? "確認中..." : "🚀 始める"}
          </button>

          <div style={{ marginTop: "14px", padding: "10px 12px", background: "rgba(255,255,255,0.02)", borderRadius: "8px", fontSize: "12px", color: "#475569", lineHeight: 1.6 }}>
            🔒 APIキーはあなたのブラウザにのみ保存されます。外部サーバーには送信されません。
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Screen 2: Onboarding ─────────────────────────────────────────────────────
function Onboarding({ onComplete, onLoadFile }) {
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ name: "", age: "", gender: "male", ethnicity: "日本人", height: "", weight: "", goal_weight: "", frame: "", conditions: "", medications: "", fat_areas: "", lifestyle: "", sleep: "", exercise: "", diet_notes: "", stated_goal: "", body_ideal: "" });
  const fileRef = useRef(null);
  const set = (k, v) => setData(d => ({ ...d, [k]: v }));

  const STEPS = [
    {
      title: "基本情報", sub: "まずあなたのことを教えてください",
      content: (
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Field label="お名前（ニックネームでもOK）" value={data.name} onChange={v => set("name", v)} placeholder="例: Sho" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <Field label="年齢" value={data.age} onChange={v => set("age", v)} placeholder="39" type="number" />
            <div>
              <Label>性別</Label>
              <div style={{ display: "flex", gap: "8px", marginTop: "6px" }}>
                {[["male","男性"],["female","女性"]].map(([v,l]) => (
                  <button key={v} onClick={() => set("gender", v)} style={{ flex: 1, padding: "10px", borderRadius: "8px", border: `1px solid ${data.gender===v?"#a78bfa":"rgba(255,255,255,0.08)"}`, background: data.gender===v?"rgba(167,139,250,0.15)":"rgba(255,255,255,0.03)", color: data.gender===v?"#a78bfa":"#64748b", fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>{l}</button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
            <Field label="身長(cm)" value={data.height} onChange={v => set("height", v)} placeholder="170" type="number" />
            <Field label="体重(kg)" value={data.weight} onChange={v => set("weight", v)} placeholder="80" type="number" />
            <Field label="目標体重(kg)" value={data.goal_weight} onChange={v => set("goal_weight", v)} placeholder="65" type="number" />
          </div>
          <div>
            <Label>骨格・体格感</Label>
            <div style={{ display: "flex", gap: "7px", marginTop: "6px", flexWrap: "wrap" }}>
              {[["small","小柄・華奢"],["medium","普通"],["large","がっしり・大柄"]].map(([v,l]) => (
                <button key={v} onClick={() => set("frame", v)} style={{ padding: "7px 14px", borderRadius: "20px", border: `1px solid ${data.frame===v?"#a78bfa":"rgba(255,255,255,0.08)"}`, background: data.frame===v?"rgba(167,139,250,0.15)":"transparent", color: data.frame===v?"#a78bfa":"#64748b", fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>{l}</button>
              ))}
            </div>
          </div>
        </div>
      ),
      canNext: () => data.name && data.age && data.height && data.weight,
    },
    {
      title: "健康・生活状況", sub: "より正確なアドバイスのために教えてください",
      content: (
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Field label="持病・健康状態" value={data.conditions} onChange={v => set("conditions", v)} placeholder="例: 高血圧、糖尿病、特になし" multiline />
          <Field label="服薬・治療中のもの" value={data.medications} onChange={v => set("medications", v)} placeholder="例: 降圧剤、特になし" multiline />
          <Field label="脂肪がつきやすい部位" value={data.fat_areas} onChange={v => set("fat_areas", v)} placeholder="例: お腹まわり、太もも" />
          <Field label="仕事・生活スタイル" value={data.lifestyle} onChange={v => set("lifestyle", v)} placeholder="例: デスクワーク、外出多め" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <Field label="睡眠" value={data.sleep} onChange={v => set("sleep", v)} placeholder="例: 7時間・不規則" />
            <Field label="運動歴・現在の運動" value={data.exercise} onChange={v => set("exercise", v)} placeholder="例: ほぼなし、週2ジョギング" />
          </div>
          <Field label="食事の制約（時間・予算など）" value={data.diet_notes} onChange={v => set("diet_notes", v)} placeholder="例: 調理15分以内、食費1500円/日" multiline />
        </div>
      ),
      canNext: () => true,
    },
    {
      title: "目標・理想のイメージ", sub: "正直に教えてください。ここが一番大事です",
      content: (
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div style={{ background: "rgba(167,139,250,0.06)", border: "1px solid rgba(167,139,250,0.15)", borderRadius: "10px", padding: "13px", fontSize: "13px", color: "#94a3b8", lineHeight: 1.7 }}>
            💡 「体重を減らしたい」だけではなく、<strong style={{ color: "#c4b5fd" }}>どんな体・どんな生活を手に入れたいか</strong>を教えてください。AIが最適な目標を一緒に見つけます。
          </div>
          <Field label="どうなりたいですか？（自由に）" value={data.stated_goal} onChange={v => set("stated_goal", v)} placeholder="例: お腹を凹ませたい、健康診断の数値を改善したい、自信を持ちたい" multiline />
          <Field label="理想としている体型・人物のイメージ（あれば）" value={data.body_ideal} onChange={v => set("body_ideal", v)} placeholder="例: 芸能人の名前、昔の自分、スポーツ選手っぽい体型" multiline />
        </div>
      ),
      canNext: () => true,
    },
  ];

  const cur = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(160deg,#0c0618 0%,#120a24 60%,#0c0618 100%)", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px", fontFamily: "'Hiragino Sans',sans-serif" }}>
      <div style={{ width: "100%", maxWidth: "520px" }}>
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <div style={{ fontSize: "10px", color: "#3d2f6b", letterSpacing: "0.12em", marginBottom: "6px" }}>AI BODY LAB</div>
          <h2 style={{ fontSize: "22px", fontWeight: 700, background: "linear-gradient(90deg,#a78bfa,#6366f1)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>プロフィール設定</h2>
        </div>

        <div style={{ display: "flex", gap: "6px", marginBottom: "20px" }}>
          {STEPS.map((_, i) => <div key={i} style={{ flex: 1, height: "3px", borderRadius: "2px", background: i <= step ? "#a78bfa" : "rgba(167,139,250,0.15)", transition: "background 0.3s" }} />)}
        </div>

        <div style={{ background: "rgba(18,10,36,0.95)", border: "1px solid rgba(167,139,250,0.15)", borderRadius: "16px", padding: "24px" }}>
          <div style={{ marginBottom: "18px" }}>
            <h3 style={{ fontSize: "17px", fontWeight: 700, color: "#e2e8f0", marginBottom: "4px" }}>{cur.title}</h3>
            <p style={{ fontSize: "12px", color: "#64748b" }}>{cur.sub}</p>
          </div>
          {cur.content}
          <div style={{ display: "flex", gap: "10px", marginTop: "22px" }}>
            {step > 0 && <button onClick={() => setStep(s => s-1)} style={{ flex: 1, padding: "12px", borderRadius: "10px", border: "1px solid rgba(167,139,250,0.2)", background: "transparent", color: "#64748b", fontSize: "14px", fontWeight: 600, cursor: "pointer" }}>← 戻る</button>}
            <button onClick={() => isLast ? onComplete(data) : setStep(s => s+1)} disabled={!cur.canNext()}
              style={{ flex: 2, padding: "12px", borderRadius: "10px", border: "none", background: cur.canNext() ? "linear-gradient(135deg,#a78bfa,#6366f1)" : "#1e1535", color: cur.canNext() ? "#fff" : "#3d2f6b", fontSize: "14px", fontWeight: 700, cursor: cur.canNext() ? "pointer" : "default", transition: "all 0.2s" }}>
              {isLast ? "🚀 コーチングを始める" : "次へ →"}
            </button>
          </div>
        </div>

        <div style={{ textAlign: "center", marginTop: "14px", display: "flex", justifyContent: "center", gap: "16px" }}>
          <input ref={fileRef} type="file" accept=".json" onChange={e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = ev => { try { onLoadFile(JSON.parse(ev.target.result)); } catch {} }; r.readAsText(f); e.target.value=""; }} style={{ display: "none" }} />
          <button onClick={() => fileRef.current?.click()} style={{ background: "none", border: "none", color: "#3d2f6b", fontSize: "12px", cursor: "pointer", textDecoration: "underline" }}>📂 セーブデータを読み込む</button>
        </div>
      </div>
    </div>
  );
}

// ─── Screen 3: Coach ──────────────────────────────────────────────────────────
function Coach({ profile, msgs, setMsgs, apiKey, onReset, onExport }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeMode, setActiveMode] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const bottomRef = useRef(null);
  const taRef = useRef(null);
  const importRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const bmi = profile.height && profile.weight
    ? (parseFloat(profile.weight) / Math.pow(parseFloat(profile.height) / 100, 2)).toFixed(1) : "-";

  const pickMode = (m) => {
    setActiveMode(m.id);
    setInput(MODE_PROMPTS[m.id] || "");
    setTimeout(() => taRef.current?.focus(), 50);
  };

  const send = async () => {
    if (!input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    const next = [...msgs, { role: "user", content: text }];
    setMsgs(next);
    setBusy(true);
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({ model: "claude-haiku-4-5-20251001", max_tokens: 1200, system: buildSystem(profile, activeMode || "coach"), messages: next }),
      });
      const raw = await res.text();
      let data;
      try { data = JSON.parse(raw); } catch {
        setMsgs([...next, { role: "assistant", content: "パースエラー(" + res.status + "): " + raw.slice(0, 200) }]);
        setBusy(false); return;
      }
      if (!res.ok) {
        setMsgs([...next, { role: "assistant", content: "APIエラー " + res.status + ": " + (data.error?.message || JSON.stringify(data)) }]);
      } else {
        setMsgs([...next, { role: "assistant", content: data.content?.find(b => b.type==="text")?.text || "空のレスポンス" }]);
      }
    } catch (e) {
      setMsgs([...next, { role: "assistant", content: "接続エラー: " + e.message }]);
    }
    setBusy(false);
  };

  const handleImport = (e) => {
    const f = e.target.files[0]; if (!f) return;
    const r = new FileReader();
    r.onload = ev => { try { const d = JSON.parse(ev.target.result); if (d.msgs) setMsgs(d.msgs); } catch {} };
    r.readAsText(f); e.target.value = "";
  };

  const curMode = MODES.find(m => m.id === activeMode);

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(160deg,#0c0618 0%,#120a24 60%,#0c0618 100%)", fontFamily: "'Hiragino Sans',sans-serif", color: "#e2e8f0", display: "flex", flexDirection: "column" }}>
      <style>{`::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#3b1f6b;border-radius:4px}textarea{resize:none;font-family:inherit}textarea::placeholder{color:#3d2f6b}`}</style>

      {/* Header */}
      <div style={{ borderBottom: "1px solid rgba(167,139,250,0.12)", background: "rgba(12,6,24,0.97)", backdropFilter: "blur(16px)", padding: "13px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ width: "32px", height: "32px", background: "linear-gradient(135deg,#a78bfa,#6366f1)", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "15px" }}>🧬</div>
          <div>
            <div style={{ fontSize: "14px", fontWeight: 700, letterSpacing: "-0.02em" }}>AI BODY LAB</div>
            <div style={{ fontSize: "10px", color: "#a78bfa", letterSpacing: "0.1em", fontWeight: 600 }}>PERSONALIZED COACHING</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <div style={{ fontSize: "12px", color: "#64748b", padding: "4px 10px", borderRadius: "20px", border: "1px solid rgba(255,255,255,0.07)" }}>
            {profile.name} · {profile.weight}kg · BMI {bmi}
          </div>
          <div style={{ position: "relative" }}>
            <button onClick={() => setMenuOpen(v => !v)} style={{ background: "rgba(167,139,250,0.12)", border: "1px solid rgba(167,139,250,0.25)", color: "#a78bfa", padding: "5px 11px", borderRadius: "7px", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}>💾 データ</button>
            {menuOpen && (
              <div onClick={() => setMenuOpen(false)} style={{ position: "absolute", right: 0, top: "36px", background: "#120a24", border: "1px solid rgba(167,139,250,0.2)", borderRadius: "10px", padding: "6px", zIndex: 100, minWidth: "170px", boxShadow: "0 8px 32px rgba(0,0,0,0.6)" }}>
                <input ref={importRef} type="file" accept=".json" onChange={handleImport} style={{ display: "none" }} />
                {[
                  { label: "⬇️ エクスポート（保存）", action: onExport },
                  { label: "⬆️ インポート（読込）", action: () => importRef.current?.click() },
                  { label: "🗑 会話をクリア", action: () => { if(window.confirm("会話をクリアしますか？")) setMsgs([]); }, color: "#64748b" },
                ].map((item, i) => (
                  <button key={i} onClick={item.action} style={{ width: "100%", background: "transparent", border: "none", color: item.color || "#e2e8f0", padding: "9px 12px", borderRadius: "7px", fontSize: "13px", fontWeight: 600, cursor: "pointer", textAlign: "left", display: "block" }}>{item.label}</button>
                ))}
                <div style={{ height: "1px", background: "rgba(167,139,250,0.1)", margin: "4px 0" }} />
                <button onClick={onReset} style={{ width: "100%", background: "transparent", border: "none", color: "#f87171", padding: "9px 12px", borderRadius: "7px", fontSize: "13px", cursor: "pointer", textAlign: "left" }}>✕ リセット（最初から）</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", maxWidth: "820px", width: "100%", margin: "0 auto", padding: "0 20px" }}>

        {/* Empty state */}
        {msgs.length === 0 && (
          <div style={{ padding: "32px 0 20px" }}>
            <div style={{ textAlign: "center", marginBottom: "28px" }}>
              <h1 style={{ fontSize: "24px", fontWeight: 700, color: "#e2e8f0", marginBottom: "10px" }}>{profile.name}さん、何から始めますか？</h1>
              <p style={{ color: "#475569", fontSize: "13px", lineHeight: 1.7 }}>
                まず <strong style={{ color: "#c4b5fd" }}>🎯 目標カウンセリング</strong> から始めることをおすすめします。<br />
                「本当に自分に合った目標」を見つけてから、具体的なプランへ進みましょう。
              </p>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px", marginBottom: "24px" }}>
              {MODES.map(m => (
                <button key={m.id} onClick={() => pickMode(m)}
                  style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "12px", padding: "16px 12px", cursor: "pointer", textAlign: "left", transition: "all 0.18s" }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(167,139,250,0.08)"}
                  onMouseLeave={e => e.currentTarget.style.background = "rgba(255,255,255,0.025)"}>
                  <div style={{ fontSize: "20px", marginBottom: "7px" }}>{m.icon}</div>
                  <div style={{ fontSize: "13px", fontWeight: 700, color: m.color, marginBottom: "4px" }}>{m.label}</div>
                  <div style={{ fontSize: "11px", color: "#475569", lineHeight: 1.5 }}>{m.desc}</div>
                </button>
              ))}
            </div>
            {profile.weight && profile.goal_weight && (
              <div style={{ background: "rgba(167,139,250,0.05)", border: "1px solid rgba(167,139,250,0.12)", borderRadius: "12px", padding: "16px 20px" }}>
                <div style={{ fontSize: "11px", color: "#475569", marginBottom: "12px", letterSpacing: "0.06em" }}>あなたの変革ロードマップ</div>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div style={{ textAlign: "center", minWidth: "60px" }}>
                    <div style={{ fontSize: "24px", fontWeight: 700, color: "#f87171" }}>{profile.weight}kg</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>現在</div>
                  </div>
                  <div style={{ flex: 1, height: "6px", background: "rgba(255,255,255,0.06)", borderRadius: "3px", position: "relative" }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: "8%", background: "linear-gradient(90deg,#a78bfa,#6366f1)", borderRadius: "3px" }} />
                  </div>
                  <div style={{ textAlign: "center", minWidth: "60px" }}>
                    <div style={{ fontSize: "24px", fontWeight: 700, color: "#34d399" }}>{profile.goal_weight}kg</div>
                    <div style={{ fontSize: "11px", color: "#64748b" }}>目標</div>
                  </div>
                </div>
                <div style={{ marginTop: "10px", textAlign: "center", fontSize: "13px", color: "#64748b" }}>
                  目標まで <strong style={{ color: "#c4b5fd" }}>{(parseFloat(profile.weight) - parseFloat(profile.goal_weight)).toFixed(1)}kg</strong> の減量
                </div>
              </div>
            )}
          </div>
        )}

        {/* Messages */}
        {msgs.length > 0 && (
          <div style={{ flex: 1, overflowY: "auto", padding: "24px 0", display: "flex", flexDirection: "column", gap: "18px" }}>
            {msgs.map((m, i) => (
              <div key={i} style={{ display: "flex", flexDirection: m.role==="user" ? "row-reverse" : "row", gap: "10px", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: 700, background: m.role==="user" ? "linear-gradient(135deg,#6366f1,#4f46e5)" : "linear-gradient(135deg,#a78bfa,#6366f1)" }}>
                  {m.role==="user" ? (profile.name?.[0] || "U") : "🧬"}
                </div>
                <div style={{ maxWidth: "85%", background: m.role==="user" ? "rgba(99,102,241,0.1)" : "rgba(167,139,250,0.05)", border: m.role==="user" ? "1px solid rgba(99,102,241,0.2)" : "1px solid rgba(167,139,250,0.12)", borderRadius: m.role==="user" ? "16px 3px 16px 16px" : "3px 16px 16px 16px", padding: "13px 16px" }}>
                  {m.role==="user" ? <div style={{ color: "#e2e8f0", fontSize: "14px", lineHeight: 1.7 }}>{m.content}</div> : <MsgContent text={m.content} />}
                </div>
              </div>
            ))}
            {busy && (
              <div style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "50%", background: "linear-gradient(135deg,#a78bfa,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px" }}>🧬</div>
                <div style={{ background: "rgba(167,139,250,0.05)", border: "1px solid rgba(167,139,250,0.12)", borderRadius: "3px 16px 16px 16px", padding: "16px 18px", display: "flex", gap: "5px" }}>
                  {[0,1,2].map(j => <div key={j} style={{ width: "7px", height: "7px", borderRadius: "50%", background: "#a78bfa", animation: `dot 1.2s ease-in-out ${j*0.2}s infinite` }} />)}
                  <style>{`@keyframes dot{0%,100%{transform:scale(0.7);opacity:0.3}50%{transform:scale(1.2);opacity:1}}`}</style>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}

        {/* Mode pills */}
        {msgs.length > 0 && (
          <div style={{ padding: "6px 0", display: "flex", gap: "5px", flexWrap: "wrap" }}>
            {MODES.map(m => (
              <button key={m.id} onClick={() => pickMode(m)}
                style={{ background: activeMode===m.id ? `${m.color}18` : "rgba(255,255,255,0.03)", border: `1px solid ${activeMode===m.id ? m.color+"40" : "rgba(255,255,255,0.06)"}`, color: activeMode===m.id ? m.color : "#64748b", padding: "5px 11px", borderRadius: "20px", fontSize: "12px", fontWeight: 600, cursor: "pointer", transition: "all 0.18s" }}>
                {m.icon} {m.label}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div style={{ padding: "8px 0 20px", position: "sticky", bottom: 0, background: "linear-gradient(to top,#0c0618 75%,transparent)" }}>
          {curMode && (
            <div style={{ marginBottom: "8px" }}>
              <span style={{ padding: "4px 10px", background: `${curMode.color}18`, border: `1px solid ${curMode.color}30`, borderRadius: "6px", fontSize: "11px", color: curMode.color, fontWeight: 600 }}>
                {curMode.icon} {curMode.label}モード
              </span>
            </div>
          )}
          <div style={{ background: "rgba(18,10,36,0.97)", border: "1px solid rgba(167,139,250,0.18)", borderRadius: "14px", display: "flex", gap: "10px", padding: "12px 14px", alignItems: "flex-end" }}>
            <textarea ref={taRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key==="Enter" && (e.metaKey||e.ctrlKey)) send(); }}
              placeholder="質問を入力、またはモードを選んでください（Cmd+Enter で送信）" rows={3}
              style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "#e2e8f0", fontSize: "14px", lineHeight: 1.65 }} />
            <button onClick={send} disabled={!input.trim()||busy}
              style={{ background: input.trim()&&!busy ? "linear-gradient(135deg,#a78bfa,#6366f1)" : "#1e1535", border: "none", color: input.trim()&&!busy ? "#fff" : "#3d2f6b", width: "40px", height: "40px", borderRadius: "10px", cursor: input.trim()&&!busy ? "pointer" : "default", fontSize: "18px", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontWeight: 700 }}>↑</button>
          </div>
          <div style={{ textAlign: "center", marginTop: "6px", fontSize: "11px", color: "#2a1f45" }}>医療行為ではありません。医学的エビデンスに基づくフィットネス・栄養コーチングです。</div>
        </div>
      </div>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  const stored = loadStorage();
  const [apiKey, setApiKey] = useState(stored.apiKey || "");
  const [profile, setProfile] = useState(stored.profile || null);
  const [msgs, setMsgsRaw] = useState(stored.msgs || []);

  const setMsgs = (m) => {
    setMsgsRaw(m);
    saveStorage({ apiKey, profile, msgs: m });
  };

  const handleApiKey = (key) => {
    setApiKey(key);
    saveStorage({ apiKey: key, profile, msgs });
  };

  const handleProfile = (p) => {
    setProfile(p);
    saveStorage({ apiKey, profile: p, msgs });
  };

  const handleLoadFile = (data) => {
    if (data.profile) { setProfile(data.profile); }
    if (data.msgs) { setMsgsRaw(data.msgs); }
    if (data.apiKey) { setApiKey(data.apiKey); }
    saveStorage({ apiKey: data.apiKey || apiKey, profile: data.profile || profile, msgs: data.msgs || msgs });
  };

  const exportData = () => {
    const blob = new Blob([JSON.stringify({ version: "1.0", savedAt: new Date().toISOString(), profile, msgs }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (profile?.name || "user") + "_bodylab_" + new Date().toISOString().slice(0,10) + ".json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const reset = () => {
    setProfile(null); setMsgsRaw([]);
    saveStorage({ apiKey, profile: null, msgs: [] });
  };

  if (!apiKey) return <ApiKeyScreen onNext={handleApiKey} />;
  if (!profile) return <Onboarding onComplete={handleProfile} onLoadFile={handleLoadFile} />;
  return <Coach profile={profile} msgs={msgs} setMsgs={setMsgs} apiKey={apiKey} onReset={reset} onExport={exportData} />;
}
