# HiyaCare

**A live coach for business calls with customers who may need more support.**

[![Care demo: a practice call where the agent rushes a bereaved customer](https://github.com/user-attachments/assets/2c9485cb-b030-4e5b-b48b-bde4679bedb3)](https://github.com/mauratobing/HiyaAI/releases/tag/v1.0.0)

▶ [Watch the demo video](https://github.com/mauratobing/HiyaAI/releases/tag/v1.0.0)

Branded caller ID tells a customer *who* is calling before they pick up. Care helps the person on the call *notice when that customer needs more time or support, and respond well*, so a legitimate call doesn't end up harming (or frightening) someone who is bereaved, unwell, worried about money, or struggling to follow.

It listens to the conversation and does three things in real time:

1. **Hears care cues** in what the customer says: a bereavement or other life event, a health issue, money worries, finding it hard to follow, asking you to slow down or repeat, feeling stressed.
2. **Tracks how the agent adapts**: acknowledging, slowing down, offering a pause or call-back, offering a trusted person, pointing to specialist support.
3. **Flags pushing on regardless**: asking for payment, using jargon, rushing or adding pressure *after* a cue was heard, and suggests a better thing to say.

Cues are signals that someone *may* need extra support. They are never a diagnosis, and nothing is stored.

Track: **Real-Time Assistance** (coaching).

## Run it (about 1 minute)

Needs Python 3.10+. Use **Chrome or Edge** for the microphone (the browser's built-in speech recognition).

```bash
# from inside this folder (the one containing README.md)
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>.

### Try it

1. **Start a practice call:** click **New call**, choose a customer (recently bereaved, hard of hearing, money worries, anxious and overwhelmed, or wary after a scam warning), optionally rename them, set your own name and company, and press **Start call**. **The call opens with you**: "Hi, it's Sam from Northbridge Finance." (spoken aloud, and counted as saying your name and company). Then speak (mic) or type as the agent. A **simulated customer answers back**, reacting to what you actually say:
   - you haven't said who you are → "Sorry, who is this?" (and they hang up if it continues)
   - you've introduced yourself → "What's it about?", and once you say why you're calling they tell you what's going on
   - you acknowledge, slow down, or offer a pause, a trusted person or support → they soften, and eventually accept
   - you push for payment or add pressure → they pull back, then end the call
   - you use jargon → they say they don't follow
   - you ask for a PIN or similar → they hang up

   Care coaches you on the left and in the chat as you go, and tells you when you did something right. Use **Free mode** instead if you want to speak for both sides.
2. **Play the demos** (bottom right, or inside **New call**). Three realistic scripted calls, spoken aloud by the browser's text-to-speech:
   - *Bereavement, handled with care*: the agent notices, slows down and offers support.
   - *The same call, rushed*: a polite agent who keeps going after the customer opens up.
   - *Hard to hear, hard to follow*: a rough start, then the agent changes course.
   Watching the first two back to back is the clearest way to see what Care does.
3. **Free mode:** press the mic and speak as the agent. Flip to *I'm the customer* to play the other side (try "My husband passed away last month and I'm a bit confused"), or just type.
4. Tap **Share recap** for an audit-style summary you can download as Markdown.

The demos and practice calls need no mic and no internet beyond localhost. With **Voice the customer** on, the customer's replies are spoken aloud by the browser (the mic is paused while they talk, so it doesn't hear itself).

The simulated customer is **rule-based, not an AI model**: it uses the same detectors as the coach, picks from written lines per persona, and will repeat itself in long calls. An LLM-driven customer is the obvious next step.

## How it works

```
mic ─► browser speech-to-text ─► POST /api/analyze ─► rule engine (app/analyzer.py)
                                                          │
   gauge · care cues · adaptations · flags · next step ◄──┘

```

- **Care cues (customer):** life event, health, money worries, finding it hard to follow, asked you to slow down or repeat, stressed or upset.
- **Adaptations (agent):** acknowledged what they said, slowed down or offered to repeat, offered a pause / call-back / letter, offered a trusted person to join, pointed to specialist support.
- **Pushing on after a cue:** payment ask, urgency, threat or command *without* a real adaptation; jargon; "didn't acknowledge what they told you"; speaking above 150 words a minute (185 on a normal call).
- **Trust basics (6 checks):** said your name, named your company, gave the reason, asked if it's a good time, mentioned recording, offered a way to verify you.
- **Scam-like patterns,** because vulnerable customers are also the ones scammers target: PIN or security-code requests, remote access, unusual payment methods, secrecy, discouraging a call-back, payment before identity.
- The engine is **stateless**: the browser sends the transcript so far and gets the whole call state back. No server-side storage, and no audio leaves the browser except via the browser's own speech recognition.

### How the score works

The care score (0 to 100) is calculated in `analyze_call` in `app/analyzer.py`, recomputed from the whole transcript after every turn.

1. **Start at 50.**
2. **+6 for each trust check completed** (up to +36).
3. **+5 for each adaptation shown** (up to +25), but only once a care cue has been heard, and only for things the agent says *after* the cue.
4. **Minus points for each risk the agent says:**

   | Severity | Penalty | Examples |
   |---|---|---|
   | High | −18 | **kept pushing after a cue** (a payment ask, urgency or threat with no real adaptation), PIN or security-code request, remote access, gift cards/crypto, asking for secrecy, discouraging a call-back, payment before identifying yourself |
   | Medium | −10 | **didn't acknowledge** what they told you, **jargon** after a cue, speaking too fast, urgency, threats |
   | Low | −5 | commanding tone |

   - A repeat of the same risk later in the call costs **half**.
   - Customer doubt ("is this a scam?") costs −5. Still not having said who you are after two agent turns costs −3.
   - An acknowledgement ("I'm sorry to hear that") alone does **not** excuse a payment ask in the same breath. It takes a pause, slower pace, trusted person or support offer.
5. **+2 for each reassuring customer reply** ("thank you", "that makes sense"), up to 3 times.
6. **Clamp to 0 to 100.**

Care cues themselves **never** reduce the score: the agent isn't at fault for the customer's situation.

| Score | Headline | Pill |
|---|---|---|
| 80 to 100 | Handling this with care (or "Clear, calm and trustworthy" if no cue was heard) | On track |
| 60 to 79 | Mostly there | On track |
| 35 to 59 | Slow down | Needs attention |
| 0 to 34 | Pause and reset | At risk |

**Worked examples (the demos):** *handled with care* = 50 + 36 (6 trust checks) + 25 (all 5 adaptations) + 2 = 113, clamped to **100**. *Rushed* = 50 + 18 (3 checks) + 5 (1 adaptation) − 71 (pressure after a cue three times, jargon, speed, no acknowledgement, customer doubt) = **2**. *Hard to hear* starts badly (a rushed, jargon-heavy turn) then recovers: 50 + 30 + 20 − 38 + 2 = **64**.

**Caveat:** the weights and thresholds are hand-picked judgements, not learned from real call data. Replacing them with a trained classifier, validated on real calls, is the first item under "what I'd do next" in the write-up.

### Why voice?
The call is already audio. The agent's eyes and hands are busy, and the signs that matter (hesitation, "sorry, could you say that again?", pace) live in *how* things are said. A form or a report after the call arrives too late. Nudges are short enough to glance at, or, with **Whisper nudges** on and headphones in, to hear.

## Tests

```bash
python3 -m pytest -q                   # scoring engine, simulated customer, AI-response parser
python3 tests/shoot.py /tmp/shots      # headless Chrome walkthrough + screenshots (server on :8765)
```

One test checks that **Care's own suggested wording never trips its own risk flags** (it caught two bugs while building).

## Layout

```
app/analyzer.py     scoring engine (cues, adaptations, rules, score, recap)
app/customer.py     the simulated customer (5 personas, reacts to what the agent says)
app/main.py         FastAPI: /api/analyze, /api/recap, /api/customer_reply, /api/personas, static files
app/scenarios.json  the three demo calls
static/             hand-written HTML/CSS/JS front end (no framework, no build step)
tests/              unit tests + browser smoke test
docs/writeup.md     one-page write-up
```

## Limits (honest list)

- Cue detection is keyword-based English. It misses a lot (a customer can be struggling without saying any of these words) and can over-flag. Cues are prompts to listen more closely, never a judgement about a person.
- Negation is only handled locally ("nothing urgent", "never ask for your PIN").
- Browser speech recognition is not available in every browser (use Chrome or Edge), and accuracy depends on audio quality. Typing always works.
- One microphone means one speaker at a time; there is no real two-channel call integration yet.
- Pace uses the time between the first and last recognised words of an utterance, so it is approximate.
- Health and life-event words are sensitive. Care analyses text in memory only, stores nothing, and the recap carries a "not a diagnosis" note.
