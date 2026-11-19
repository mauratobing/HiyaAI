"""A simulated customer for practice calls.

Rule-based and deterministic, with no model and no network. The customer reacts
to what the agent actually said, using the same detectors as the coach:

  * agent doesn't say who they are      -> "who is this?" (hangs up if it continues)
  * agent introduces themselves         -> "what's it about?", then the customer shares what's going on
  * agent adapts (slows down, offers a  -> the customer softens, and eventually accepts
    pause, a trusted person, support)
  * agent pushes (payment, urgency)     -> the customer pulls back, then ends the call
  * agent uses jargon                   -> the customer says they don't follow
  * scam-like requests (PIN, secrecy)   -> the customer hangs up
"""

from __future__ import annotations

from . import analyzer as an

END_SCAM = "This sounds like a scam. I'm going to hang up now."
END_NO_ID = "I'm sorry, I don't know who you are. I'm going to put the phone down."

PERSONAS: dict[str, dict] = {
    "bereaved": {
        "label": "Recently bereaved",
        "blurb": "Her husband passed away in the spring and used to handle everything.",
        "name": "Mrs Evans",
        "context": "Collections · Missed payment",
        "ask": "Oh, hello. What's it about?",
        "who": ["Sorry, who is this?", "I'm sorry, who did you say you were?"],
        "reveal": "Oh dear. I'm sorry, it's been a difficult few months. My husband passed away in the spring and he used to deal with all of this.",
        "confused": ["I do get a bit muddled with the paperwork. My daughter usually helps me.", "I'm sorry, I'm afraid I don't really understand."],
        "pushed": ["Oh, I don't know. I really can't think about this today.", "I'm not comfortable doing this now. I'd rather call you back."],
        "end_pushed": "I'm sorry, I can't do this. I'm going to put the phone down.",
        "jargon": ["I'm sorry, I don't understand those words. Could you say it more simply?", "I'm afraid you've lost me again."],
        "soft": ["Thank you, that's kind.", "Yes, that's helpful, thank you.", "That makes sense, thank you."],
        "neutral": ["Mm. Go on.", "I see. And what happens then?", "Right. Yes, I'm listening."],
        "end_ok": "Thank you, that's a relief. I'll talk to my daughter and we can speak another time.",
    },
    "hearing": {
        "label": "Hard of hearing",
        "blurb": "Finds it hard to hear and follow on the phone.",
        "name": "Mr Hassan",
        "context": "Collections · Failed direct debit",
        "ask": "Hello? Sorry, what's it about?",
        "who": ["Sorry, who? I can't hear you very well.", "Pardon? Who is this?"],
        "reveal": "Sorry, what was that? I'm a bit hard of hearing and the line's not great.",
        "confused": ["I'm sorry, you've lost me. Could you say that again, a bit slower?", "Sorry, could you repeat that?"],
        "pushed": ["I really can't follow all this on the phone. Can you write to me instead?", "I can't hear properly and I'm not agreeing to anything like this."],
        "end_pushed": "I can't hear you properly and I'm not comfortable. I'm going to hang up.",
        "jargon": ["I'm sorry, I didn't catch any of that. Could you say it plainly?", "I'm afraid that went right over my head."],
        "soft": ["Yes, that's much clearer, thank you.", "Thank you, I can follow that.", "That's better, thank you."],
        "neutral": ["Sorry, could you say that again?", "Mm, go on."],
        "end_ok": "Thank you, that's much clearer. Please write to me, and my son can help me read it.",
    },
    "money": {
        "label": "Money worries",
        "blurb": "Recently lost her job and is worried about bills.",
        "name": "Ms Clarke",
        "context": "Collections · Missed payments",
        "ask": "Oh, hi. What's this about?",
        "who": ["Sorry, who is this?", "Who did you say you were?"],
        "reveal": "To be honest I'm struggling at the moment. I lost my job in September and I can't afford much.",
        "confused": ["I'm just overwhelmed with bills at the moment. I don't know what I'm supposed to do.", "I'm so worried about it all."],
        "pushed": ["I've told you, I can't pay anything right now.", "This is making me really stressed. I might have to go."],
        "end_pushed": "I can't do this. I'm going to hang up now.",
        "jargon": ["I'm sorry, I don't understand any of these terms. What does that mean for me?", "Sorry, what does that actually mean?"],
        "soft": ["Thank you for not rushing me. That helps.", "Okay. That does sound more manageable, thank you.", "Yes please, that would help."],
        "neutral": ["Right. Go on.", "I see. What are my options?"],
        "end_ok": "Thank you, that's a relief. Please put me through to the support team.",
    },
    "anxious": {
        "label": "Anxious and overwhelmed",
        "blurb": "Gets very stressed by letters and calls about money.",
        "name": "Mr Singh",
        "context": "Collections · Late instalment",
        "ask": "Oh. Hello. What's this about?",
        "who": ["Sorry, who is this? Why are you calling me?", "I don't know who you are. Who's this?"],
        "reveal": "Sorry, I'm feeling quite anxious. I get really stressed about letters and calls like this, and I'm a bit overwhelmed.",
        "confused": ["I'm sorry, I can't take it all in. I'm a bit confused.", "My head's all over the place, sorry."],
        "pushed": ["Please, I'm panicking a bit. I can't decide anything right now.", "I'm really not comfortable with this. I need to stop."],
        "end_pushed": "I'm sorry, I can't do this. I'm putting the phone down.",
        "jargon": ["I'm sorry, I don't understand. What do those words mean?", "That sounds frightening. What does that mean?"],
        "soft": ["Thank you. That helps me calm down a bit.", "Okay. Thank you for being gentle about it.", "Yes, that's helpful, thank you."],
        "neutral": ["Mm. Okay.", "Right. Go on, I'm listening."],
        "end_ok": "Thank you, that's a relief. Can you write it all down and I'll read it when I'm calmer?",
    },
    "wary": {
        "label": "Wary after a scam warning",
        "blurb": "Her bank warned her about scam calls, so she needs a way to check you.",
        "name": "Mrs Taylor",
        "context": "Customer service · Account review",
        "ask": "Hello? What's this about?",
        "who": ["Sorry, who is this?", "Who did you say you were?"],
        "reveal": "Sorry, I have to be careful. My bank warned me about scam calls. How do I know you're who you say you are?",
        "confused": ["I'm just not sure. Can I check with my bank first?", "I don't give details over the phone any more."],
        "pushed": ["No, I'm not giving anything over the phone. Not like this.", "That's exactly what a scammer would say."],
        "end_pushed": "I'm sorry, I'm not comfortable. I'm hanging up.",
        "jargon": ["I'm sorry, I don't follow. Can you put that plainly?"],
        "soft": ["Okay, that does reassure me, thank you.", "Right, thank you for being patient with me.", "Yes, that seems fair."],
        "neutral": ["Mm. Go on.", "I see. And what do you need from me?"],
        "end_ok": "Okay, thank you. I'll ring the number on my statement and call you back.",
    },
}


def list_personas() -> list[dict]:
    return [{"id": k, **{f: v[f] for f in ("label", "blurb", "name", "context")}} for k, v in PERSONAS.items()]


def reply(persona_id: str, turns: list[dict]) -> dict:
    """Return {"text": str | None, "ended": bool} for the customer's next line."""
    p = PERSONAS[persona_id]
    cust = [t["text"] for t in turns if t.get("speaker") == "customer"]
    enders = {p["end_pushed"], p["end_ok"], END_SCAM, END_NO_ID}
    if any(c in enders for c in cust):
        return {"text": None, "ended": True}

    last = max((i for i, t in enumerate(turns) if t.get("speaker", "agent") == "agent"), default=None)
    if last is None:  # the agent speaks first; nothing to answer yet
        return {"text": None, "ended": False}

    state = an.analyze_call(turns)
    ids = {f["id"] for f in state["flags"] if f["turn_index"] == last}
    text = turns[last]["text"]
    adapt = {k for k, pat in an._ADAPT.items() if pat.search(text)}
    if ids & {"urgency", "threat", "commanding"}:
        adapt -= {"pause"}
    checks = an._checks_in(text)
    done = {c["id"] for c in state["checklist"] if c["done"]}
    intro_done = {"name", "company"} <= done
    helped = bool(adapt) or "verify" in checks
    help_offer = bool(adapt & {"pause", "trusted", "support"}) or "verify" in checks

    def pick(key: str) -> tuple[str, int]:
        lst = p[key]
        used = sum(1 for c in cust if c in lst)
        return lst[used % len(lst)], used

    # scam-like requests: hang up
    if ids & {"credentials", "remote_access", "odd_payment", "secrecy", "no_callback"}:
        return {"text": END_SCAM, "ended": True}

    # the customer hasn't opened up yet
    if p["reveal"] not in cust:
        if not intro_done or "pay_before_id" in ids:
            line, used = pick("who")
            if used >= len(p["who"]):
                return {"text": END_NO_ID, "ended": True}
            return {"text": line, "ended": False}
        if "reason" not in done and p["ask"] not in cust:
            return {"text": p["ask"], "ended": False}      # "what's it about?"
        return {"text": p["reveal"], "ended": False}

    # they have: respond to how the agent is handling it
    pushing = bool(ids & {"pressure_after_care", "urgency", "threat", "commanding", "pay_before_id"}) or bool(an._PAYMENT_ASK.search(text))
    if pushing and not (adapt - {"ack"}) and "verify" not in checks:
        line, used = pick("pushed")
        if used >= len(p["pushed"]):
            return {"text": p["end_pushed"], "ended": True}
        return {"text": line, "ended": False}
    if "jargon" in ids or an._JARGON.search(text):
        return {"text": pick("jargon")[0], "ended": False}
    if helped:
        line, used = pick("soft")
        if help_offer and used >= 1:
            return {"text": p["end_ok"], "ended": True}
        return {"text": line, "ended": False}
    line, used = pick("confused")
    if used < len(p["confused"]):
        return {"text": line, "ended": False}
    return {"text": pick("neutral")[0], "ended": False}
