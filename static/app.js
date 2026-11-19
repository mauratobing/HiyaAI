/* Care front end: plain JS, no framework, no build step. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const state = {
    turns: [],          // {speaker, text, duration_ms}
    analysis: null,
    role: "agent",
    whisper: false,
    listening: false,
    playing: false,
    cancelDemo: false,
    scenarios: [],
    coachedTurns: new Set(),
    seq: 0,
    startedAt: null,
    openMoments: new Set(),
    practice: null,      // {id, name, ended} while a simulated customer is on the line
    personas: [],
    autoListen: false,
    muted: false,        // ignore the mic while the customer's voice is playing
    replying: false,
    voiceCustomer: true,
    prevDone: new Set(),
  };

  /* ------------------------------------------------------------------ mascot */
  let mid = 0;
  function mascot(mood = "good") {
    const id = "mg" + ++mid;
    const mouths = {
      idle: '<path d="M42 66q8 7 16 0" stroke="#1d3b3d" stroke-width="3" fill="none" stroke-linecap="round"/>',
      good: '<path d="M40 64q10 11 20 0" stroke="#1d3b3d" stroke-width="3.2" fill="none" stroke-linecap="round"/>',
      ok: '<path d="M42 66q8 7 16 0" stroke="#1d3b3d" stroke-width="3" fill="none" stroke-linecap="round"/>',
      warn: '<path d="M43 68h14" stroke="#1d3b3d" stroke-width="3" stroke-linecap="round"/>',
      bad: '<ellipse cx="50" cy="68" rx="5" ry="6" fill="#1d3b3d"/>',
    };
    const brows = mood === "warn" || mood === "bad"
      ? '<path d="M32 42l11 4M68 42l-11 4" stroke="#1d3b3d" stroke-width="3" stroke-linecap="round"/>' : "";
    return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b6f0e2"/><stop offset="1" stop-color="#6ccab8"/></linearGradient></defs>
      <ellipse cx="50" cy="94" rx="24" ry="4" fill="#2f8f8d" opacity=".15"/>
      <path d="M44 14q6-9 12 0M38 8q12-12 24 0" stroke="#2f8f8d" stroke-width="3" fill="none" stroke-linecap="round" opacity=".55"/>
      <ellipse cx="50" cy="57" rx="35" ry="33" fill="url(#${id})"/>
      <path d="M17 54a33 33 0 0 1 66 0" stroke="#2f8f8d" stroke-width="5" fill="none" stroke-linecap="round"/>
      <rect x="10" y="48" width="10" height="18" rx="5" fill="#2f8f8d"/><rect x="80" y="48" width="10" height="18" rx="5" fill="#2f8f8d"/>
      <path d="M85 62q2 16-18 20" stroke="#2f8f8d" stroke-width="3.4" fill="none" stroke-linecap="round"/><circle cx="65" cy="82.5" r="3.6" fill="#2f8f8d"/>
      <circle cx="38" cy="54" r="4.6" fill="#1d3b3d"/><circle cx="62" cy="54" r="4.6" fill="#1d3b3d"/>
      <circle cx="39.6" cy="52.4" r="1.5" fill="#fff"/><circle cx="63.6" cy="52.4" r="1.5" fill="#fff"/>
      <circle cx="29" cy="66" r="5" fill="#ff9aa2" opacity=".45"/><circle cx="71" cy="66" r="5" fill="#ff9aa2" opacity=".45"/>
      ${brows}${mouths[mood] || mouths.ok}
    </svg>`;
  }
  const setHTML = (el, html) => { el.innerHTML = html; };

  /* ------------------------------------------------------------------- gauge */
  const CX = 110, CY = 112, R = 88;
  const pt = (score) => {
    const a = (180 + score * 1.8) * Math.PI / 180;
    return [CX + R * Math.cos(a), CY + R * Math.sin(a)];
  };
  const arc = (from, to) => {
    const [x1, y1] = pt(from), [x2, y2] = pt(to);
    return `M${x1.toFixed(1)} ${y1.toFixed(1)} A${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
  };
  function drawGauge() {
    setHTML($("#gauge"), `
      <path d="${arc(0, 100)}" stroke="#eef4f4" stroke-width="22" fill="none" stroke-linecap="round"/>
      <path d="${arc(1.5, 33)}" stroke="#f3a9a3" stroke-width="16" fill="none" stroke-linecap="round"/>
      <path d="${arc(37, 58)}" stroke="#f6cd8d" stroke-width="16" fill="none" stroke-linecap="round"/>
      <path d="${arc(62, 98.5)}" stroke="#8fd8c3" stroke-width="16" fill="none" stroke-linecap="round"/>
      <g class="needle" id="needle" style="transform:rotate(-90deg)">
        <path d="M110 112 L110 38" stroke="#1d3b3d" stroke-width="4" stroke-linecap="round"/>
        <circle cx="110" cy="112" r="9" fill="#1d3b3d"/><circle cx="110" cy="112" r="3.5" fill="#fff"/>
      </g>`);
  }

  /* ------------------------------------------------------------------- icons */
  const tick = '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7.5" fill="currentColor" opacity=".18"/><path d="M4.6 8.3l2.2 2.2 4.6-4.8" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const ring = '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.6" stroke="currentColor" stroke-width="1.5" fill="none" opacity=".5"/></svg>';
  const ICONS = {
    pressure: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 3h6"/></svg>',
    asks: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 11h18M7 15h3"/></svg>',
    intro: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0 1 16 0"/></svg>',
    pace: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h3l2-6 4 12 3-9 2 3h4"/></svg>',
    customer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.600-7 10-7 10z"/></svg>',
  };

  /* ------------------------------------------------------------------ render */
  const SIGNALS = [
    { id: "pressure", label: "Pressure", match: (f) => ["urgency", "threat", "commanding", "secrecy", "pressure_after_care"].includes(f.id) },
    { id: "asks", label: "Asks", match: (f) => ["pay_before_id", "credentials", "odd_payment", "remote_access", "no_callback"].includes(f.id) },
    { id: "intro", label: "Intro" },
    { id: "clarity", label: "Clarity", match: (f) => ["pace", "jargon"].includes(f.id) },
    { id: "customer", label: "Care cues", care: true, match: (f) => f.id.startsWith("care_") || f.id === "doubt" || f.id === "no_ack" },
  ];

  function renderSignals(a) {
    const root = $("#signals");
    root.replaceChildren();
    for (const s of SIGNALS) {
      let n = 0, fine = false;
      if (s.id === "intro") {
        const intro = a ? a.checklist.filter((c) => ["name", "company"].includes(c.id) && c.done).length : 0;
        fine = intro === 2;
        n = a && a.flags.some((f) => f.id === "no_intro") ? 1 : 0;
      } else if (a) {
        n = a.flags.filter(s.match).length;
        fine = s.id === "clarity" && a.avg_wpm && n === 0;
      }
      const el = h("div", { class: `sig ${s.care ? "care" : ""} ${n ? "hot" : fine ? "fine" : ""}`, title: s.label });
      el.innerHTML = ICONS[s.id === "clarity" ? "pace" : s.id] + s.label;
      el.append(h("span", { class: "n" }, String(n)));
      root.append(el);
    }
  }

  function renderCare(a) {
    const care = a ? a.care : { active: false, cues: [], actions: [] };
    const row = $("#cueRow");
    row.replaceChildren();
    if (!care.cues.length) {
      row.append(h("span", { class: "cue none" }, a && a.started ? "None heard yet. Care keeps listening." : "None heard yet"));
    } else {
      care.cues.forEach((c) => row.append(h("span", { class: "cue", title: `Turn ${c.turn_index + 1}` }, c.label)));
    }
    const ul = $("#actions");
    ul.replaceChildren();
    const actions = care.actions.length ? care.actions : [
      "Acknowledged what they said", "Slowed down or offered to repeat", "Offered a pause, call-back or letter",
      "Offered a trusted person to join", "Pointed to specialist support"].map((label) => ({ label, done: false }));
    actions.forEach((c) => {
      const li = h("li", { class: `${c.done ? "done" : ""} ${care.active ? "" : "idle"}` });
      li.innerHTML = (c.done ? tick : ring) + c.label;
      ul.append(li);
    });
    $("#careHint").textContent = care.active ? "They may need more time or support. This is not a diagnosis."
      : "Signs they may need more time or support. Not a diagnosis.";
  }

  function renderChecks(a) {
    const ul = $("#checks");
    ul.replaceChildren();
    const list = a ? a.checklist : [];
    for (const c of list) {
      const li = h("li", { class: c.done ? "done" : "" });
      li.innerHTML = (c.done ? tick : ring) + c.label;
      ul.append(li);
    }
    const total = a ? a.checks_total : 6, done = a ? a.checks_done : 0;
    $("#fcDone").textContent = done;
    $("#fcTotal").textContent = total;
    const dashes = $("#fcDashes");
    dashes.replaceChildren(...Array.from({ length: total }, (_, i) => h("i", { class: i < done ? "on" : "" })));
    const pct = Math.round((done / total) * 100);
    $("#progPct").textContent = pct + "%";
    $("#progBar").style.width = pct + "%";
  }

  function renderHeadline(a) {
    $("#gaugeCard").dataset.level = a.level;
    $("#levelPill span").textContent = a.pill;
    $("#headline").textContent = a.headline;
    $("#sub").textContent = a.sub;
    $("#scoreNum").textContent = a.started ? a.score : "–";
    $("#needle").style.transform = `rotate(${(a.started ? a.score : 50) * 1.8 - 90}deg)`;
    const mood = a.level === "idle" ? "idle" : a.level;
    setHTML($("#brandMark"), mascot(mood === "bad" ? "warn" : mood));
    setHTML($("#panelMascot"), mascot(mood));
    const peek = $("#peek");
    setHTML(peek, mascot(mood) + '<span class="bang">!</span>');
    peek.classList.toggle("alert", a.level === "bad" || a.level === "warn");
    $("#panelTitle").textContent = {
      idle: "Listening for what they need", good: "Handled with care", ok: "Mostly there",
      warn: "Let's slow down", bad: "Let's pause and reset",
    }[a.level];
  }

  function renderNext(a) {
    const s = a.suggestion;
    const card = $("#nextCard");
    if (!a.started) {
      $("#nextTitle").textContent = "Your next step";
      $("#nextSay").textContent = "Say hello and tell them who you are. I'll listen for anything they need from you.";
      $("#nextWhy").textContent = "";
      card.dataset.tone = "info";
      card.dataset.say = "Hello, my name is [name] and I'm calling from [company].";
      card.classList.remove("no-say");
      return;
    }
    if (!s) { card.dataset.say = ""; card.classList.add("no-say"); return; }
    $("#nextTitle").textContent = s.title;
    $("#nextSay").textContent = s.say ? `“${s.say}”` : "";
    $("#nextWhy").textContent = s.why;
    card.dataset.tone = s.tone;
    card.dataset.say = s.say;
    card.classList.toggle("no-say", !s.say);
  }

  const KIND_ICON = { risk: "!", pace: "≈", doubt: "?", care: "♥", missing: "…" };
  const SEV_LABEL = { high: "High", medium: "Medium", low: "Low" };
  function momentRow(f, key) {
    const kindTag = f.kind === "care" ? "Care" : f.kind === "doubt" ? "Doubt" : SEV_LABEL[f.severity];
    const open = state.openMoments.has(key);
    const row = h("div", { class: `moment sev-${f.severity} kind-${f.kind} ${open ? "open" : ""}` },
      h("button", {
        class: "moment-top", "aria-expanded": String(open),
        onclick: () => {
          state.openMoments.has(key) ? state.openMoments.delete(key) : state.openMoments.add(key);
          row.classList.toggle("open");
        },
      },
        h("div", { class: "m-ico" }, KIND_ICON[f.kind] || "!"),
        h("div", { class: "m-main" },
          h("div", { class: "m-label" }, f.label),
          h("div", { class: "m-sub" },
            f.turn_index != null ? `Turn ${f.turn_index + 1} · ` : "", f.evidence ? `“${f.evidence}”` : "")),
        h("span", { class: "tag" }, kindTag)),
      h("div", { class: "moment-detail" },
        f.why || "",
        f.say ? h("div", { class: "try" }, h("b", {}, "Try saying"), f.say) : null));
    return row;
  }

  function renderMoments(a) {
    const list = $("#momentList");
    list.replaceChildren();
    const real = a.flags.filter((f) => f.kind !== "care").reverse();
    real.forEach((f) => list.append(momentRow(f, `${f.id}-${f.turn_index}`)));
    const n = real.length;
    $("#momentsTitle").textContent = !a.started ? "Nothing flagged yet"
      : n === 0 ? "No flags so far. Nicely done." : `Care flagged ${n} moment${n > 1 ? "s" : ""} to review`;
  }

  function renderThread(a, gained = []) {
    // attach tags to bubbles, and add one coach whisper per flagged turn
    document.querySelectorAll(".msg[data-i]").forEach((msg) => {
      const i = Number(msg.dataset.i);
      const tags = $(".tags", msg);
      const have = new Set([...tags.children].map((t) => t.dataset.k));
      a.flags.filter((f) => f.turn_index === i).forEach((f) => {
        const k = f.id;
        if (!have.has(k)) tags.append(h("span", { class: `t ${f.kind === "care" || f.kind === "doubt" ? f.kind : f.severity}`, "data-k": k }, f.label));
      });
    });
    const latest = state.turns.length - 1;
    const fresh = a.flags.filter((f) => f.turn_index === latest && f.say && f.kind !== "missing");
    if (fresh.length && !state.coachedTurns.has(latest)) {
      state.coachedTurns.add(latest);
      const s = a.suggestion;
      const say = s && s.say ? s.say : fresh[0].say;
      const thread = $("#thread");
      thread.append(h("div", { class: "coach" },
        h("div", { class: "av", html: "" }, ""),
        h("div", { class: "cb" }, h("small", {}, "Try saying this instead"), `“${say}”`,
          h("div", {}, h("button", { class: "copy", onclick: () => copy(say) }, "Copy")))));
      setHTML($(".coach:last-child .av"), mascot(a.level === "bad" ? "warn" : "ok"));
      thread.scrollTop = thread.scrollHeight;
      if (state.whisper && !state.playing) speak(say, { rate: 0.95, pitch: 1.1, quiet: true });
    } else if (gained.length && state.turns.length && state.turns[latest].speaker === "agent" && !state.coachedTurns.has("g" + latest)) {
      state.coachedTurns.add("g" + latest);
      const thread = $("#thread");
      const phrase = gained.map((g) => g.charAt(0).toLowerCase() + g.slice(1)).join(", ");
      const node = h("div", { class: "coach good" },
        h("div", { class: "av" }),
        h("div", { class: "cb" }, h("small", {}, "Nice"), `You ${phrase}.`));
      thread.append(node);
      setHTML($(".av", node), mascot("good"));
      thread.scrollTop = thread.scrollHeight;
    }
  }

  function render(a) {
    const now = new Set([
      ...a.checklist.filter((c) => c.done).map((c) => "c_" + c.id),
      ...a.care.actions.filter((c) => c.done).map((c) => "a_" + c.id),
    ]);
    const labels = Object.fromEntries([
      ...a.checklist.map((c) => ["c_" + c.id, c.label]), ...a.care.actions.map((c) => ["a_" + c.id, c.label])]);
    const gained = [...now].filter((k) => !state.prevDone.has(k)).map((k) => labels[k]);
    state.prevDone = now;
    state.analysis = a;
    renderHeadline(a);
    renderChecks(a);
    renderCare(a);
    renderSignals(a);
    renderNext(a);
    renderMoments(a);
    renderThread(a, gained);
  }

  /* --------------------------------------------------------------- transcript */
  function addBubble(turn, index) {
    $("#empty")?.remove();
    $("#introCard")?.remove();
    const thread = $("#thread");
    const msg = h("div", { class: `msg ${turn.speaker}`, "data-i": index },
      h("div", { class: "who" }, turn.speaker === "agent" ? "You (agent)" : "Customer"),
      h("div", { class: "bubble" }, turn.text),
      h("div", { class: "tags" }));
    thread.append(msg);
    thread.scrollTop = thread.scrollHeight;
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(path + " " + res.status);
    return res.json();
  }

  async function addTurn(speaker, text, duration_ms = null, opts = {}) {
    text = text.trim();
    if (!text) return;
    if (!state.startedAt) state.startedAt = Date.now();
    const turn = { speaker, text, duration_ms: duration_ms ? Math.round(duration_ms) : null };
    state.turns.push(turn);
    addBubble(turn, state.turns.length - 1);
    const mySeq = ++state.seq;
    try {
      const a = await api("/api/analyze", { turns: state.turns });
      if (mySeq === state.seq) render(a); // ignore stale replies
    } catch (e) {
      $("#micNote").textContent = "Couldn't reach the server. Is it running?";
    }
    if (speaker === "agent" && state.practice && opts.reply !== false) customerReply();
  }

  /* ----------------------------------------------------------------- speech */
  const synth = window.speechSynthesis;
  function pickVoice(role) {
    const voices = synth ? synth.getVoices() : [];
    const en = voices.filter((v) => /^en[-_]GB/i.test(v.lang)).concat(voices.filter((v) => /^en/i.test(v.lang)));
    if (!en.length) return null;
    return role === "customer" ? en[Math.min(1, en.length - 1)] : en[0];
  }
  function speak(text, { role = "agent", rate = 1, pitch = 1, quiet = false } = {}) {
    return new Promise((resolve) => {
      if (!synth) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      const v = pickVoice(role);
      if (v) u.voice = v;
      u.lang = v ? v.lang : "en-GB";
      u.rate = rate; u.pitch = role === "customer" ? 1.18 : pitch; u.volume = quiet ? 0.8 : 1;
      const est = 1200 + text.split(/\s+/).length * 420;
      const t = setTimeout(resolve, est + 1500);       // never hang if the browser has no voices
      u.onend = u.onerror = () => { clearTimeout(t); resolve(); };
      synth.cancel();
      synth.speak(u);
    });
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); $("#micNote").textContent = "Copied."; }
    catch { $("#micNote").textContent = "Copy isn't available in this browser."; }
    setTimeout(() => ($("#micNote").textContent = ""), 1800);
  }

  /* -------------------------------------------------------------- microphone */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, utterStart = 0, micGen = 0;
  // One utterance at a time: the mic switches itself off when you stop talking, and stays off
  // while the customer is speaking, so it can never transcribe the customer's voice as yours.
  function startMic() {
    if (!SR) { $("#micNote").textContent = "The mic needs Chrome or Edge. You can still type below."; return; }
    if (state.playing) stopDemo();
    if (state.listening || state.muted || state.replying) return;
    const gen = ++micGen;
    let heard = false;
    rec = new SR();
    rec.lang = "en-GB"; rec.continuous = false; rec.interimResults = true;
    rec.onresult = (e) => {
      if (gen !== micGen || state.muted || state.replying) return;
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (!utterStart) utterStart = performance.now();
        if (r.isFinal) {
          const dur = performance.now() - utterStart; utterStart = 0;
          heard = true;
          $("#textIn").value = "";
          state.autoListen = !!state.practice;          // keep the conversation hands-free in practice calls
          addTurn(state.role, r[0].transcript, dur);
          stopMic(true);                                // you've finished: mic off
          return;
        } else interim += r[0].transcript;
      }
      if (interim) $("#textIn").value = interim;
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        $("#micNote").textContent = "Mic permission was blocked. Allow it in the address bar, or type instead.";
        state.listening = false; state.autoListen = false; syncMic();
      }
    };
    rec.onend = () => {
      if (gen !== micGen) return;
      state.listening = false; syncMic();
      if (!heard) { state.autoListen = false; $("#micNote").textContent = "Mic off. Press the mic to speak."; }
    };
    state.listening = true; syncMic();
    try { rec.start(); $("#micNote").textContent = "Listening. Say your piece, then pause."; } catch (_) { state.listening = false; syncMic(); }
  }
  function stopMic(keepNote = false) {
    micGen++;                                           // anything the old recognizer still says is ignored
    state.listening = false;
    try { rec && rec.abort(); } catch (_) {}
    utterStart = 0;
    syncMic();
    if (!keepNote) $("#micNote").textContent = "";
  }
  function syncMic() {
    $("#micBtn").classList.toggle("on", state.listening);
    $("#liveDot").classList.toggle("on", state.listening);
    $("#micBtn").setAttribute("aria-label", state.listening ? "Stop microphone" : "Start microphone");
  }

  /* -------------------------------------------------------- practice customer */
  function lockRole(on) {
    $(".role").classList.toggle("locked", on);
    if (on) {
      state.role = "agent";
      document.querySelectorAll(".role-btn").forEach((x) => x.classList.toggle("active", x.dataset.role === "agent"));
    }
  }
  function notice(text) {
    const thread = $("#thread");
    thread.append(h("div", { class: "sys" }, text));
    thread.scrollTop = thread.scrollHeight;
  }
  function showTyping(name) {
    hideTyping();
    const thread = $("#thread");
    thread.append(h("div", { class: "msg customer typing", id: "typing" },
      h("div", { class: "who" }, name),
      h("div", { class: "bubble" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")))));
    thread.scrollTop = thread.scrollHeight;
  }
  const hideTyping = () => $("#typing")?.remove();

  async function customerSays(text) {
    stopMic(true);                                      // never listen while the customer is talking
    let speaking = Promise.resolve();
    if (state.voiceCustomer && synth) {
      state.muted = true;
      speaking = speak(text, { role: "customer" }).then(() => new Promise((r) => setTimeout(() => { state.muted = false; r(); }, 700)));
    }
    await addTurn("customer", text);
    await speaking;
    state.muted = false;
  }
  async function customerReply() {
    const pr = state.practice;
    if (!pr || pr.ended || state.replying) return;
    state.replying = true;
    showTyping(pr.name);
    await sleep(900 + Math.random() * 500);
    try {
      if (state.practice !== pr) return;                     // a new call was started meanwhile
      const r = await api("/api/customer_reply", { persona: pr.id, turns: state.turns });
      hideTyping();
      if (state.practice !== pr) return;
      if (r.ended) pr.ended = true;
      if (r.text) await customerSays(r.text);
      if (r.ended) endCall();
    } catch (_) {
      hideTyping();
      $("#micNote").textContent = "Couldn't get a reply from the customer.";
    } finally {
      if (state.practice === pr) state.replying = false;
      // hands-free: if you were speaking, hand the floor back by turning the mic on again
      if (state.practice === pr && state.autoListen && !pr.ended && !state.listening) startMic();
    }
  }
  function endCall() {
    state.practice.ended = true;
    stopMic();
    notice("The call has ended");
    $("#micNote").textContent = "Tap Share recap to review it, or New call to try another customer.";
  }
  const cleanWord = (v, fallback) => (v || "").replace(/[^A-Za-z'\-]/g, "") || fallback;
  async function startCall({ mode, persona, name, agentName, company }) {
    closeModalSilently();
    stopMic();
    const P = state.personas.find((x) => x.id === persona);
    newCall(name || P.name, P.context);
    if (mode !== "practice") { $("#micNote").textContent = "Free mode: you speak for both sides using the switch below."; return; }
    const pr = { id: persona, name: name || P.name, ended: false };
    state.practice = pr;
    lockRole(true);
    $("#empty")?.remove();
    // the agent must open the call themselves: typed (a ready-made line) or spoken
    const opening = `Hi, it's ${cleanWord((agentName || "").split(/\s+/)[0], "Sam")} from ${(company || "").trim() || "Northbridge Finance"}.`;
    showIntroCard(opening);
    $("#micNote").textContent = "The call is connected. Introduce yourself: send the line above, or press the mic and say it.";
  }
  function showIntroCard(line) {
    const input = h("input", { type: "text", class: "field", id: "introIn", value: line, maxlength: "200", "aria-label": "Your introduction" });
    const send = () => {
      const v = input.value.trim();
      if (!v || !state.practice || state.turns.length) return;
      addTurn("agent", v);
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); send(); } });
    const card = h("div", { class: "intro-card", id: "introCard" },
      h("b", {}, "Start the call"),
      h("p", {}, "Say who you are and where you're calling from. Edit the line, then send it, or say it out loud."),
      input,
      h("div", { class: "row" },
        h("button", { class: "btn primary", type: "button", onclick: send }, "Send intro"),
        h("button", { class: "btn", type: "button", onclick: () => { if (!state.listening) startMic(); } }, "🎤 Say it instead")));
    $("#thread").append(card);
  }
  function openSetup() {
    if (!state.personas.length) return;
    const sel = { persona: state.personas[0].id, mode: "practice" };
    const nameIn = h("input", { type: "text", class: "field", maxlength: "30", placeholder: state.personas[0].name, "aria-label": "Customer name" });
    const agentIn = h("input", { type: "text", class: "field", maxlength: "20", value: "Sam", "aria-label": "Your name" });
    const companyIn = h("input", { type: "text", class: "field", maxlength: "40", value: "Northbridge Finance", "aria-label": "Your company" });
    const grid = h("div", { class: "persona-grid" });
    state.personas.forEach((p) => {
      const b = h("button", {
        type: "button", class: "persona" + (p.id === sel.persona ? " sel" : ""),
        onclick: () => {
          sel.persona = p.id; nameIn.placeholder = p.name;
          grid.querySelectorAll(".persona").forEach((x) => x.classList.toggle("sel", x === b));
        },
      }, h("b", {}, p.label), h("span", {}, p.blurb));
      grid.append(b);
    });
    const modes = h("div", { class: "mode" });
    [["practice", "Practice call", "You open the call; the customer answers."],
     ["free", "Free mode", "You speak for both sides."]].forEach(([id, t, d]) => {
      const b = h("button", {
        type: "button", class: id === sel.mode ? "sel" : "",
        onclick: () => { sel.mode = id; modes.querySelectorAll("button").forEach((x) => x.classList.toggle("sel", x === b)); },
      }, t, h("small", {}, d));
      modes.append(b);
    });
    const demos = h("div", { class: "demo-row" });
    state.scenarios.forEach((sc) => demos.append(h("button", {
      type: "button", class: "chip", title: sc.blurb,
      onclick: () => { closeModalSilently(); playDemo(sc); },
    }, sc.title)));
    openModal(h("div", {},
      h("h2", {}, "New call"),
      h("p", {}, "Who are you calling? Pick a customer. You introduce yourself, typed or spoken, and the customer answers back. Care coaches you as you go."),
      h("h4", {}, "Customer"), grid,
      h("h4", {}, "Customer's name (optional)"), nameIn,
      h("h4", {}, "You are"),
      h("div", { class: "two" }, agentIn, companyIn),
      h("p", { class: "fine" }, "You open the call yourself. You'll get a ready-made intro to send (“Hi, it's Sam from Northbridge Finance.”), or you can say it out loud."),
      h("h4", {}, "Mode"), modes,
      h("div", { class: "row" },
        h("button", { class: "btn primary", type: "button", onclick: () => startCall({ mode: sel.mode, persona: sel.persona, name: nameIn.value.trim(), agentName: agentIn.value, company: companyIn.value }) }, "Start call")),
      h("h4", {}, "Or watch a scripted demo"), demos));
  }

  /* -------------------------------------------------------------------- demo */
  async function playDemo(sc) {
    stopMic();
    newCall(sc.customer, sc.context);
    state.playing = true; state.cancelDemo = false;
    $("#stopBtn").hidden = false;
    for (const t of sc.turns) {
      if (state.cancelDemo) break;
      await sleep(550);
      if (state.cancelDemo) break;
      const speaking = speak(t.text, { role: t.speaker });
      await addTurn(t.speaker, t.text, t.duration_ms || null);
      await speaking;
    }
    state.playing = false;
    $("#stopBtn").hidden = true;
  }
  function stopDemo() {
    state.cancelDemo = true; state.playing = false;
    synth && synth.cancel();
    $("#stopBtn").hidden = true;
  }

  /* --------------------------------------------------------------- call state */
  function newCall(customer = "New customer", context = "Collections") {
    stopDemo(); state.cancelDemo = false;
    state.turns = []; state.coachedTurns = new Set(); state.startedAt = null;
    state.openMoments = new Set(); state.seq++;
    state.practice = null; state.replying = false; state.muted = false; state.prevDone = new Set();
    lockRole(false);
    $("#thread").replaceChildren(h("div", { class: "empty", id: "empty" },
      h("p", {}, "Choose who you're calling. You open the call as the agent, then speak or type, and the customer answers back."),
      h("button", { class: "btn primary", type: "button", onclick: openSetup }, "Choose a customer")));
    $("#callTitle").textContent = `Outbound call · ${customer}`;
    $("#callSub").firstChild.textContent = `${context} · `;
    $("#timer").textContent = "00:00";
    api("/api/analyze", { turns: [] }).then(render);
  }
  setInterval(() => {
    if (!state.startedAt) return;
    const s = Math.floor((Date.now() - state.startedAt) / 1000);
    $("#timer").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  }, 1000);

  /* -------------------------------------------------------------------- modal */
  function openModal(node) {
    const body = $("#modalBody");
    body.replaceChildren(node);
    $("#modal").hidden = false;
  }
  const closeModalSilently = () => { $("#modal").hidden = true; };
  const closeModal = () => { $("#modal").hidden = true; setTab("live"); };

  async function showRecap() {
    if (!state.turns.length) {
      return openModal(h("div", {}, h("h2", {}, "Recap"), h("p", {}, "There's nothing to recap yet. Start a call or play a demo, then come back.")));
    }
    const r = await api("/api/recap", { turns: state.turns });
    const md = r.markdown;
    openModal(h("div", {},
      h("h2", {}, "Call recap"),
      h("p", {}, `Care score ${r.state.score}/100 · ${r.state.care.cues.length} care cue${r.state.care.cues.length === 1 ? "" : "s"} heard · ${r.state.checks_done} of ${r.state.checks_total} trust checks. Text only; no audio is stored.`),
      h("pre", {}, md),
      h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: () => download("care-recap.md", md) }, "Download .md"),
        h("button", { class: "btn ghost", onclick: () => copy(md) }, "Copy"))));
  }
  function download(name, text) {
    const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "text/markdown" })), download: name });
    document.body.append(a); a.click(); a.remove();
  }
  function showHow() {
    openModal(h("div", {},
      h("h2", {}, "How Care works"),
      h("p", {}, "Caller ID tells a customer who is calling before they pick up. Care helps the person on the call notice when that customer needs more time or support, and respond well."),
      h("h4", {}, "What it listens for"),
      h("ul", {},
        h("li", {}, "Care cues from the customer: a bereavement or other life event, a health issue, money worries, finding it hard to follow, asking you to slow down or repeat, feeling stressed. These are signals that someone may need extra support, never a diagnosis."),
        h("li", {}, "How you adapt: acknowledging what they said, slowing down, offering a pause or call-back, offering a trusted person, pointing to specialist support."),
        h("li", {}, "Pushing on regardless: asking for payment, using jargon, rushing or adding pressure after a cue was heard."),
        h("li", {}, "Trust basics and scam-like patterns, because vulnerable customers are also the ones scammers target.")),
      h("h4", {}, "Why voice"),
      h("p", {}, "The call is already audio. The agent's eyes and hands are busy, and the signs that matter (hesitation, asking you to repeat, pace) live in how things are said. A form or a report after the call arrives too late. The nudges are short enough to read at a glance or, with headphones on, hear as a whisper."),
      h("h4", {}, "Under the hood"),
      h("p", {}, "Browser speech-to-text feeds a local rule engine that responds instantly. Only text is analysed, and nothing is stored.")));
  }
  function setTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  }

  /* -------------------------------------------------------------------- init */
  async function init() {
    drawGauge();
    renderSignals(null);
    renderChecks(null);
    renderCare(null);
    setHTML($("#brandMark"), mascot("good"));
    setHTML($("#panelMascot"), mascot("idle"));
    setHTML($("#peek"), mascot("idle") + '<span class="bang">!</span>');

    document.querySelectorAll(".tab").forEach((t) =>
      t.addEventListener("click", () => {
        setTab(t.dataset.tab);
        if (t.dataset.tab === "recap") showRecap();
        else if (t.dataset.tab === "how") showHow();
        else closeModalSilently();
      }));
    $("#modalClose").addEventListener("click", closeModal);
    $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });

    $("#recapBtn").addEventListener("click", () => { setTab("recap"); showRecap(); });
    $("#newBtn").addEventListener("click", () => { setTab("live"); openSetup(); });
    $("#voiceToggle").addEventListener("change", (e) => (state.voiceCustomer = e.target.checked));
    $("#whisperToggle").addEventListener("change", (e) => (state.whisper = e.target.checked));
    $("#micBtn").addEventListener("click", () => { if (state.listening) { state.autoListen = false; stopMic(); } else startMic(); });
    $("#stopBtn").addEventListener("click", stopDemo);
    $("#copyBtn").addEventListener("click", () => copy($("#nextCard").dataset.say || ""));
    $("#speakBtn").addEventListener("click", () => { const s = $("#nextCard").dataset.say; if (s) speak(s, { quiet: true }); });
    document.querySelectorAll(".role-btn").forEach((b) =>
      b.addEventListener("click", () => {
        if ($(".role").classList.contains("locked")) return;
        state.role = b.dataset.role;
        document.querySelectorAll(".role-btn").forEach((x) => x.classList.toggle("active", x === b));
      }));
    $("#composer").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("#textIn").value;
      $("#textIn").value = "";
      if (state.playing) stopDemo();
      state.autoListen = false; stopMic();
      addTurn(state.role, v);
    });

    try {
      const [scs, pers] = await Promise.all([api("/api/scenarios"), api("/api/personas")]);
      state.scenarios = scs;
      state.personas = pers;
      const chips = $("#demoChips");
      scs.forEach((s) => chips.append(h("button", { class: "chip", title: s.blurb, onclick: () => playDemo(s) }, s.title)));
    } catch (_) { $("#micNote").textContent = "Couldn't reach the server."; }
    if (synth) synth.getVoices();
    newCall();
  }
  init();
})();
