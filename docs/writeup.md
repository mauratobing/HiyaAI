# Care: a live coach for calls with customers who may need more support

**Track:** Real-Time Assistance

## What I built
A working web prototype that listens to a business phone call and coaches the person making it, live. It transcribes speech in the browser and does three things. It hears **care cues** in what the customer says (a bereavement, a health issue, money worries, finding it hard to follow, asking the agent to slow down or repeat, feeling stressed). It tracks whether the agent **adapts**: acknowledges, slows down, offers a pause or call-back, offers a trusted person, points to specialist support. And it flags **pushing on regardless**, for example asking for payment, using jargon or rushing after a cue was heard, with a gentler line to say instead. A gauge, a trust checklist (name, company, reason, a way to verify you) and a downloadable recap sit alongside. Three realistic demo calls play with no setup, including the same bereavement call handled well and handled badly. In **practice mode** a simulated customer (five personas) answers back to what the agent says or types, so people can rehearse: the call opens with the agent's introduction, the customer asks what it's about, opens up once you say why you're calling, softens when you adapt, and pulls back or hangs up if you push.

## Who it's for and what problem it solves
Agents and call-centre teams at firms that need customers to pick up and stay on the line: lenders, utilities, healthcare, delivery. Caller-ID branding answers *who is calling* before the customer picks up. But the person who answers is sometimes grieving, unwell, anxious about money, or struggling to follow, and regulators such as the FCA expect firms to spot that and adapt. Today that depends on each agent's judgement in the moment and on after-the-fact call sampling, which is slow and patchy. A polite, well-meaning agent can still cause harm by pressing on with a payment after a customer says their husband has died. Care closes that gap *during* the conversation.

## Why voice is the right interface
The call is already audio. The agent's eyes and hands are busy with the customer and their systems, and the signs that matter (hesitation, "sorry, could you say that again?", pace, how a customer reacts to a request) live in how things are said, not in a form. A report after the call arrives too late to help the person on it. Nudges are short enough to read at a glance or hear as a whisper.

## Choices I made
- **Narrow over broad:** my first version leaned on obvious scam phrases, and the demo calls felt unrealistic. Real harm is subtler, so I focused on what a legitimate agent does *after* a customer signals they need support.
- **Explainable over clever:** a rule engine scores each turn instantly and every point maps to a flag the agent can open. An LLM adds an optional, asynchronous second opinion on subtle issues, so latency and failures never hurt the live call.
- **Coach, don't police:** the product gives a better sentence to say, not just a red light. Care cues never reduce the score; only the agent's response does.
- **Cues, not diagnoses, and private by default:** no audio stored, no server state, text only, and a "not a diagnosis" note on the recap.

## What I'd do next
1. Validate and tune on real, consented call recordings with input from vulnerable-customer specialists; the rule weights are hand-picked judgements and the keyword cues will miss a lot and over-flag.
2. Replace keywords with a small classifier trained on labelled calls, and measure false positives and false negatives separately.
3. Use acoustic features (pauses, interruptions, pitch, "emotion in the voice"), not just words and pace, and connect to a real two-channel telephony stream so agent and customer are separated.
4. Hand over to a human: warm-transfer to a specialist team, or schedule a call-back, from inside the tool.
5. Close the loop with branded calling: tie each call's care score to answer, complaint and outcome rates, so teams can see which scripts cost them trust.
6. Replace the rule-based simulated customer with an LLM-driven one, so practice calls vary and test more situations, and use it for team training.
7. Multilingual support and team-level coaching dashboards.
