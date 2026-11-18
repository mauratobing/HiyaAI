"""Care's scoring engine.

Stateless and deterministic: give it the whole transcript so far and it returns
the call state (care score, trust checklist, care cues, flagged moments, next
step). Everything here runs locally, with no network and no API key.

Care is built around one question: does this call notice when a customer needs
more time or support, and does the agent adapt? It tracks:

  * care cues     - what the CUSTOMER says that signals they may need extra care
                    (health, a life event, money worries, finding it hard to
                    follow, asking for a slower pace or repeat, feeling stressed)
  * adaptations   - what the AGENT does about it (acknowledges, slows down,
                    offers a pause or call-back, offers a trusted person, points
                    to specialist support)
  * pressure      - pushing on regardless: asking for payment, urgency, jargon
                    or speed after a cue was heard
  * trust basics  - things any legitimate caller should do (say who you are, why
                    you're calling, how to verify you), plus classic scam
                    patterns (PIN requests, secrecy, ...), because vulnerable
                    customers are also the ones scammers target.

Cues are signals that someone MAY need support. They are never a diagnosis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional


def _r(p: str) -> re.Pattern:
    return re.compile(p, re.I)


# --------------------------------------------------------------------------
# Trust checklist: what a legitimate caller should get across
# --------------------------------------------------------------------------

_NAME_STOP = {
    "calling", "sorry", "just", "here", "afraid", "very", "really", "so", "not",
    "going", "trying", "also", "glad", "happy", "pleased", "aware", "sure",
}
_COMPANY_STOP = {
    "your", "the", "a", "an", "last", "this", "that", "what", "earlier",
    "yesterday", "now", "then", "there", "home", "work", "before",
}

_NAME_PATTERNS = [
    _r(r"\bmy name(?:'s| is)\s+([a-z][a-z'\-]{1,14})\b"),
    _r(r"\b(?:this is|it'?s|it is)\s+([a-z][a-z'\-]{1,14})\s+(?:from|at|with|calling)\b"),
    _r(r"\b(?:i'?m|i am)\s+([a-z][a-z'\-]{1,14})\s+(?:from|at|with|calling|and i'?m calling|and i work)\b"),
]
_COMPANY_PATTERNS = [
    _r(r"\b(?:calling|ringing|phoning|contacting)(?:\s+you)?\s+(?:from|on behalf of)\s+([a-z][\w&'\-]*)"),
    _r(r"\b(?:i'?m|i am|this is|it'?s|my name(?:'s| is))\s+[a-z][a-z'\-]{1,14}(?:\s+[a-z][a-z'\-]{1,14})?"
       r"\s+(?:from|at|with)\s+([a-z][\w&'\-]*)"),
    _r(r"\bon behalf of\s+([a-z][\w&'\-]*)"),
]

_REASON = _r(
    r"\b(?:reason (?:for|of) (?:my|the) call|calling (?:about|regarding|because|to (?:talk|discuss|let|check|see|follow))"
    r"|it'?s (?:about|regarding)|regarding your|about your (?:account|payment|agreement|instal?lment|finance|lease|contract|balance|order|appointment))"
)
_PERMISSION = _r(
    r"\b(?:is (?:now|this) a (?:good|bad|convenient)|good time to (?:talk|chat)|convenient time"
    r"|have (?:a |an |five |ten |two |a few |a couple of |some )?(?:minutes?|moments?|time)"
    r"|got (?:a |five |two )?(?:minutes?|moment)|okay (?:to|if)|ok (?:to|if)|happy to (?:talk|continue|chat))"
)
_RECORDING = _r(r"\b(?:call (?:is|may be|will be|might be)(?: being)? recorded|recorded for|recording this call)")
_VERIFY = _r(
    r"\b(?:call (?:us|me|the team) back|ring (?:us|me|the number|back)|number (?:on|printed on) (?:your|the back of your) (?:card|statement|letter|bill)"
    r"|on our (?:official )?website|hang up and (?:call|ring)|you can (?:verify|check)|verify (?:this|me|who)"
    r"|call (?:back )?on (?:the )?(?:number|official)|official (?:number|website))"
)

CHECKLIST = [
    ("name", "Said your name"),
    ("company", "Named your company"),
    ("reason", "Gave the reason for the call"),
    ("permission", "Asked if it's a good time"),
    ("recording", "Mentioned the call is recorded"),
    ("verify", "Offered a way to verify you"),
]


def _checks_in(text: str) -> set[str]:
    found: set[str] = set()
    for p in _NAME_PATTERNS:
        for m in p.finditer(text):
            if m.group(1).lower() not in _NAME_STOP:
                found.add("name")
    for p in _COMPANY_PATTERNS:
        for m in p.finditer(text):
            if m.group(1).lower() not in _COMPANY_STOP:
                found.add("company")
    if _REASON.search(text):
        found.add("reason")
    if _PERMISSION.search(text):
        found.add("permission")
    if _RECORDING.search(text):
        found.add("recording")
    if _VERIFY.search(text):
        found.add("verify")
    return found


# --------------------------------------------------------------------------
# Care cues (customer speech): signs someone MAY need more time or support
# --------------------------------------------------------------------------

# (id, label, pattern, why, what the agent could say)
CARE_CUES = [
    (
        "life_event", "Care cue: a major life event",
        _r(r"\b(?:bereave\w*|passed away|died|death|funeral|widow\w*|lost my (?:husband|wife|partner|mum|mother|dad|father|job)"
           r"|redundan\w*|divorc\w*|separat(?:ed|ion)|care home|nursing home|new baby|just had a baby)\b"),
        "Big life events change what someone can take in. They need time, and often a different route to help.",
        "I'm so sorry. Please take all the time you need. We can pause this, and we have a specialist team who can help at a time like this.",
    ),
    (
        "health", "Care cue: a health issue",
        _r(r"\b(?:unwell|poorly|ill|in hospital|hospital|diagnos\w*|cancer|chemo\w*|operation|surgery|dementia|memory|medication|treatment"
           r"|not well|recovering|stroke|mental health)\b"),
        "Health problems can make a phone call tiring or confusing. Offer a lighter way to continue.",
        "I'm sorry to hear you've not been well. There's no pressure at all, and we can talk another day, or someone you trust can join us.",
    ),
    (
        "money", "Care cue: money worries",
        _r(r"\b(?:can'?t afford|cannot afford|no money|struggling (?:to pay|financially|with money|with bills)|behind on (?:everything|my bills|bills)"
           r"|on benefits|universal credit|skint|debts?|worried about (?:money|paying|bills)|can'?t pay|couldn'?t pay|cost of living)\b"),
        "Someone in financial difficulty needs options and a kind tone, not a demand.",
        "Thank you for telling me. There are options for people in difficulty, and I can put you through to our support team. Nothing needs to be decided today.",
    ),
    (
        "understanding", "Care cue: finding it hard to follow",
        _r(r"\b(?:confused|muddled|(?:don'?t|do not|didn'?t|did not) understand|can'?t follow|lost me|not following|what does that mean"
           r"|never been good with (?:this|numbers|forms|phones)|my (?:son|daughter|carer|husband|wife|nephew|niece)(?: usually| normally| always)?"
           r" (?:handles|deals with|does|helps(?: me)?(?: with)?|looks after))"),
        "If they can't follow, nothing they agree to is really informed. Simplify and offer another route.",
        "Let me explain that more simply, step by step. Please stop me whenever something isn't clear.",
    ),
    (
        "repeat", "Care cue: asked you to slow down or repeat",
        _r(r"\b(?:hard of hearing|deaf|can'?t hear|couldn'?t hear|speak up|speak louder|bad line|breaking up|say that again|repeat that"
           r"|pardon|what was that|sorry,? what|slow(?:er| down)|too fast|stammer\w*)\b"),
        "A request to repeat is a request for a different pace or channel. Treat it as important.",
        "Of course, let me say that again, more slowly. Would it be easier if I wrote to you?",
    ),
    (
        "distress", "Care cue: feeling stressed or upset",
        _r(r"\b(?:anxious|anxiety|panic\w*|overwhelm\w*|stress\w*|upset|crying|in tears|can'?t cope|cannot cope|can'?t sleep|worried sick"
           r"|frightened|scared|nervous|shaking|too much for me)\b"),
        "Strong emotion narrows attention. Slow right down and give them control.",
        "I can hear this is stressful. There's no rush, and we can stop for a moment whenever you like.",
    ),
]

# --------------------------------------------------------------------------
# Adaptations (agent speech): what a good response to a cue looks like
# --------------------------------------------------------------------------

_ADAPT = {
    "ack": _r(
        r"\b(?:i'?m (?:so |very |really )?sorry|sorry (?:to hear|for your)|that sounds (?:really |very )?(?:hard|difficult|stressful|tough)"
        r"|i understand|thank you for (?:telling|sharing|letting)|i can hear)"
    ),
    "slow": _r(
        r"\b(?:say (?:that|it|this) again|go through (?:that|it|this)|explain (?:that|it|this) (?:more )?(?:simply|again)|more (?:simply|slowly)"
        r"|slow(?:er|ly| down)|take (?:all )?(?:your|the) time|no rush|step by step|stop me|in simpler)"
    ),
    "pause": _r(
        r"\b(?:call you back|ring you back|another (?:time|day)|better time|pause (?:here|this)|come back to (?:this|it)"
        r"|speak (?:again )?(?:later|tomorrow|next week)|write to you|send (?:you )?(?:it )?in (?:writing|the post)|(?:a |the )?letter"
        r"|no pressure|nothing needs to be (?:paid|decided|done) today|stop for a moment)"
    ),
    "trusted": _r(
        r"\b(?:someone you trust|trusted (?:person|friend|family)|family member|friend or (?:a )?(?:relative|family)|a relative"
        r"|(?:your )?(?:son|daughter|carer|husband|wife|friend)(?: can| could)? (?:join|help|speak)|third party|power of attorney|(?:have|bring) someone)"
    ),
    "support": _r(
        r"\b(?:support team|specialist (?:team|support|advisers?)|extra support|financial support|bereavement (?:team|support)|customer care"
        r"|money ?advice|debt (?:charity|advice)|stepchange|citizens advice|money ?helper|options for people)"
    ),
}

ACTIONS = [
    ("ack", "Acknowledged what they said"),
    ("slow", "Slowed down or offered to repeat"),
    ("pause", "Offered a pause, call-back or letter"),
    ("trusted", "Offered a trusted person to join"),
    ("support", "Pointed to specialist support"),
]
ACTION_SAY = {
    "ack": "Thank you for telling me. I'm sorry you're dealing with that.",
    "slow": "I'll go step by step, and you can stop me whenever you like.",
    "pause": "There's no pressure. We can pick this up another time, or I can write to you instead.",
    "trusted": "You're very welcome to have someone you trust join us on the call.",
    "support": "We also have a specialist support team who can help, and I can put you through if you'd like.",
}
ACTION_WHY = {
    "ack": "Showing you've heard them is the first thing they need.",
    "slow": "A slower pace, or an offer to repeat, helps someone who is struggling to take it in.",
    "pause": "Taking the pressure off lets them decide when they are ready.",
    "trusted": "Having someone they trust alongside protects them and helps them understand.",
    "support": "Specialist teams can do things a collections agent can't.",
}
ENOUGH_ACTIONS = 3  # stop nudging once this many adaptations have been shown

_JARGON = _r(
    r"\b(?:arrears|default notice|capitali[sz]\w*|apr|settlement figure|direct debit mandate|forbearance|balloon payment|outstanding balance"
    r"|variation of terms|termination notice|repossession proceedings|early settlement)\b"
)
JARGON_SAY = "Let me put that more simply: there's an amount we haven't received yet, and I'd like to help you sort it out in a way that works for you."
NO_ACK_SAY = ACTION_SAY["ack"] + " " + ACTION_SAY["pause"]
PRESSURE_AFTER_SAY = (
    "I'm going to stop there. There's no pressure, and nothing needs to be decided today. "
    "Would you like to pick this up another time, or have someone you trust join us?"
)

# --------------------------------------------------------------------------
# Risk rules (agent speech): scam-like patterns
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    severity: str  # high | medium | low
    pattern: re.Pattern
    why: str
    say: str
    negatable: bool = True  # "nothing urgent" / "never ask for your PIN" should not trigger


_NEGATION = _r(r"\b(?:never|not|no|nothing|without|isn'?t|aren'?t|won'?t|wouldn'?t|don'?t|do not|doesn'?t)\b")


def _negated(text: str, start: int, window: int = 35) -> bool:
    # only look inside the same clause, so "don't hang up, just give me the PIN" is not "negated"
    clause = re.split(r"[,.;:!?]", text[max(0, start - window):start])[-1]
    return bool(_NEGATION.search(clause))


RULES: list[Rule] = [
    Rule(
        "credentials", "Asked for a PIN or security code", "high",
        _r(r"\b(?:pin|password|passcode|one[- ]time (?:code|passcode|password)|otp|security code|cvv|cvc|3[- ]digit|verification code)\b"),
        "Genuine firms never ask for these on an outbound call. This is the strongest scam signal there is.",
        "I will never ask for your PIN or a security code on a call like this, and please don't share one with anyone.",
    ),
    Rule(
        "remote_access", "Asked them to install or share their screen", "high",
        _r(r"\b(?:anydesk|teamviewer|remote access|screen[- ]shar\w*|download (?:this|the|an?) (?:app|software|tool|program)|install (?:this|the|an?))"),
        "Remote-access requests are a classic fraud move.",
        "Please don't install anything. You can do all of this yourself on our website if you'd prefer.",
    ),
    Rule(
        "odd_payment", "Mentioned an unusual way to pay", "high",
        _r(r"\b(?:gift ?cards?|vouchers?|bitcoin|crypto\w*|western union|moneygram|itunes|google play card|safe account|secure account)\b"),
        "Gift cards, crypto and 'safe accounts' are never a normal way to settle a bill.",
        "We only take payment through the methods on your statement or on our official website.",
    ),
    Rule(
        "secrecy", "Asked them to keep it secret or stay on the line", "high",
        _r(r"\b(?:(?:please )?(?:don'?t|do not) (?:tell|hang up|speak to|talk to|mention|contact|end|disconnect)|keep (?:this|it) (?:between us|confidential|secret|quiet)|stay on the (?:line|phone))"),
        "Isolating someone from advice is a hallmark of pressure scams.",
        "You're very welcome to speak to someone you trust, or to hang up and call us back. I'd encourage that.",
        negatable=False,
    ),
    Rule(
        "no_callback", "Discouraged a call-back", "high",
        _r(r"\b(?:no need to (?:call|ring) (?:us |me )?back|can'?t (?:call|ring) (?:us |me )?back|won'?t be able to (?:call|ring)|not possible to call back)"),
        "Refusing a call-back is the opposite of building trust.",
        "Of course. Please call us back on the number printed on your statement and quote the reference I'll give you.",
        negatable=False,
    ),
    Rule(
        "urgency", "Rushing them with urgency", "medium",
        _r(r"\b(?:right now|immediately|straight away|right away|urgent(?:ly)?|asap|today only|last chance|final (?:warning|notice|chance)"
           r"|within (?:the next )?(?:hour|\d+ minutes?|\d+ hours?)|before (?:we (?:close|end)|the office (?:closes|shuts)|end of (?:the )?day|close of business)"
           r"|act now|no time|running out of time|hurry)\b"),
        "Artificial deadlines make people decide before they can check.",
        "There's no rush. I can walk you through the options and you can decide in your own time.",
    ),
    Rule(
        "threat", "Leaned on a threat or consequence", "medium",
        _r(r"\b(?:arrest(?:ed)?|prosecut\w*|bailiffs?|warrant|police|legal action|court|(?:be|been|get|will be) (?:frozen|suspended|closed|cancelled|seized)|repossess\w*|seiz\w*)"),
        "Consequences can be explained factually, but leading with them sounds like intimidation.",
        "I'd like to help you avoid that. Here are the options available to you today.",
    ),
    Rule(
        "commanding", "Commanding tone", "low",
        _r(r"\b(?:listen (?:to me|carefully)|you (?:must|have to)|do as i say|just do it|stop (?:asking|talking))\b"),
        "Orders put people on the defensive. Invitations keep them with you.",
        "Would it help if I explained that step by step?",
    ),
]
_PRESSURE_RULES = {"urgency", "threat", "commanding"}

_PAYMENT_ASK = _r(r"\b(?:pay(?:ing|ment)?|card (?:number|details)|bank details|sort code|account number|settle (?:it|this|the))\b")
_PAYMENT_SAY = (
    "Before we talk about payment, let me tell you who I am: I'm [name] from [company], "
    "calling about [reason]. You're welcome to call us back on the number on your statement."
)

# --------------------------------------------------------------------------
# Other customer cues
# --------------------------------------------------------------------------

_DOUBT = _r(
    r"\b(?:scam|fraud|fake|fishy|suspicious|how do i know|don'?t trust|not sure (?:about|this|i)|who(?:'s| is) (?:this|calling)|who are you"
    r"|prove|how did you get my (?:number|details)|why (?:are you|did you) (?:calling|call)|(?:i'?ll|i will) (?:call|ring) (?:you )?back"
    r"|(?:i'?d|i would) (?:rather|prefer to) (?:call|ring)|can i (?:call|ring) (?:you )?back|hang up|not comfortable)"
)
_REASSURED = _r(r"\b(?:okay|ok|alright|that'?s fine|go ahead|yes please|thank(?:s| you)|that makes sense|sounds good|relief|much clearer)\b")

DOUBT_SAY = (
    "That's a fair question, and I'd rather you checked. Please ring the number on your statement and ask for "
    "the support team. I'll wait, or you can call me back."
)
PACE_SAY = "Let me slow down. Take your time and stop me if anything isn't clear."

_CHECK_SAY = {
    "name": "Hello, my name is [name] and I'm calling from [company].",
    "company": "I'm calling from [company]. You can find us on the number printed on your statement.",
    "reason": "The reason for my call is [reason]. Nothing is wrong with your account today.",
    "permission": "Is now a good time to talk for a couple of minutes?",
    "recording": "Just so you know, this call may be recorded for training and quality purposes.",
    "verify": "If you'd like to check me out, please ring the number on your statement and ask for [team].",
}
_CHECK_WHY = {
    "name": "People trust a name. Say yours first.",
    "company": "Name the company early so they can place you.",
    "reason": "Say why you're calling before asking for anything.",
    "permission": "Asking permission hands control back to them.",
    "recording": "Being upfront about recording builds credibility.",
    "verify": "Inviting verification is the single most trust-building thing you can do.",
}

SEV_WEIGHT = {"high": 18, "medium": 10, "low": 5}
ACTION_POINTS = 5
FAST_WPM = 185        # normal call
FAST_WPM_CARE = 150   # after a care cue: they need more time

# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass
class Flag:
    id: str
    label: str
    severity: str  # high | medium | low
    kind: str  # risk | doubt | care | pace | missing
    turn_index: int
    speaker: str
    evidence: str
    why: str
    say: str

    def to_dict(self) -> dict:
        return asdict(self)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _snippet(text: str, m: re.Match, pad: int = 28) -> str:
    start = max(0, m.start() - pad)
    end = min(len(text), m.end() + pad)
    s = text[start:end].strip()
    return ("…" if start > 0 else "") + s + ("…" if end < len(text) else "")


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------


def analyze_call(turns: list[dict]) -> dict:
    """turns: [{speaker: 'agent'|'customer', text: str, duration_ms: int|None}]"""
    done: set[str] = set()
    actions: set[str] = set()
    flags: list[Flag] = []
    agent_turns = 0
    wpm_samples: list[float] = []
    reassured = 0
    nudged_intro = False
    first_cue: Optional[int] = None
    pending_ack = False  # a care cue was just heard; the agent's next turn should respond to it

    for i, t in enumerate(turns):
        text = (t.get("text") or "").strip()
        if not text:
            continue
        speaker = t.get("speaker", "agent")

        if speaker == "agent":
            agent_turns += 1
            done |= _checks_in(text)
            intro_done = {"name", "company"} <= done
            care_active = first_cue is not None
            rule_hits: set[str] = set()

            for rule in RULES:
                m = next((x for x in rule.pattern.finditer(text)
                          if not (rule.negatable and _negated(text, x.start()))), None)
                if m:
                    rule_hits.add(rule.id)
                    flags.append(Flag(rule.id, rule.label, rule.severity, "risk", i, speaker,
                                      _snippet(text, m), rule.why, rule.say))

            pay = _PAYMENT_ASK.search(text)
            if pay and not intro_done:
                flags.append(Flag(
                    "pay_before_id", "Asked about payment before saying who you are", "high", "risk", i, speaker,
                    _snippet(text, pay),
                    "Payment before identity is the order a fraudster uses. A real caller identifies first.",
                    _PAYMENT_SAY))

            # ---- how the agent responds to a customer who may need more care
            adapt = {k for k, p in _ADAPT.items() if p.search(text)}
            if care_active:
                actions |= adapt
                if (pay or rule_hits & _PRESSURE_RULES) and not (adapt - {"ack"}):
                    m = pay or None
                    flags.append(Flag(
                        "pressure_after_care", "Kept pushing after they signalled they needed support", "high", "risk",
                        i, speaker, _snippet(text, m) if m else "",
                        "Once someone has said they are struggling, pressing for payment or a quick decision is the main way a legitimate call causes harm.",
                        PRESSURE_AFTER_SAY))
                jm = _JARGON.search(text)
                if jm:
                    flags.append(Flag(
                        "jargon", "Used jargon while they were finding it hard to follow", "medium", "risk", i, speaker,
                        _snippet(text, jm),
                        "Terms like these are routine for you and opaque for them.", JARGON_SAY))
                if pending_ack and not adapt:
                    flags.append(Flag(
                        "no_ack", "Didn't acknowledge what they told you", "medium", "risk", i, speaker, "",
                        "Someone who has just shared something difficult needs to hear that you heard it.", NO_ACK_SAY))
            pending_ack = False

            dur = t.get("duration_ms")
            words = _word_count(text)
            if dur and words >= 8:
                wpm = words / (max(dur, 1000) / 60000)
                wpm_samples.append(wpm)
                limit = FAST_WPM_CARE if care_active else FAST_WPM
                if wpm > limit:
                    label = (f"Speaking fast for someone who needs time (~{round(wpm)} words a minute)" if care_active
                             else f"Speaking fast (~{round(wpm)} words a minute)")
                    flags.append(Flag(
                        "pace", label, "medium", "pace", i, speaker,
                        f"{words} words in {dur / 1000:.1f}s",
                        "Fast talking sounds like a script, and it leaves no room to stop you.", PACE_SAY))

            if agent_turns >= 2 and not intro_done and not nudged_intro:
                nudged_intro = True
                flags.append(Flag(
                    "no_intro", "Still haven't said who you are", "low", "missing", i, speaker, "",
                    "Two turns in and the customer doesn't know your name or company.", _CHECK_SAY["name"]))
        else:
            heard_cue = False
            for cid, label, pattern, why, say in CARE_CUES:
                m = pattern.search(text)
                if m:
                    heard_cue = True
                    flags.append(Flag(f"care_{cid}", label, "medium", "care", i, speaker, _snippet(text, m), why, say))
            if heard_cue:
                if first_cue is None:
                    first_cue = i
                pending_ack = True
            m = _DOUBT.search(text)
            if m:
                flags.append(Flag("doubt", "Customer is unsure about the call", "medium", "doubt", i, speaker,
                                  _snippet(text, m), "They are looking for a reason to trust you, or to leave.", DOUBT_SAY))
            if _REASSURED.search(text) and not heard_cue and not m:
                reassured += 1

    # ---- score ---------------------------------------------------------
    started = any((t.get("text") or "").strip() for t in turns)
    care_active = first_cue is not None
    score = 50 + 6 * len(done)
    if care_active:
        score += ACTION_POINTS * len(actions)
    seen: dict[str, int] = {}
    for f in flags:
        if f.kind in ("risk", "pace"):
            w = SEV_WEIGHT[f.severity]
            score -= w if seen.get(f.id, 0) == 0 else w // 2
            seen[f.id] = seen.get(f.id, 0) + 1
        elif f.kind == "doubt":
            score -= 5
        elif f.kind == "missing":
            score -= 3
    score += min(reassured, 3) * 2
    score = max(0, min(100, score))

    level, pill, headline, sub = _level(score, started, care_active)

    cues_seen: dict[str, dict] = {}
    for f in flags:
        if f.kind == "care" and f.id not in cues_seen:
            short = f.label.replace("Care cue: ", "")
            cues_seen[f.id] = {"id": f.id, "label": short[:1].upper() + short[1:], "turn_index": f.turn_index}

    avg_wpm = round(sum(wpm_samples) / len(wpm_samples)) if wpm_samples else None
    return {
        "started": started,
        "score": score,
        "level": level,
        "pill": pill,
        "headline": headline,
        "sub": sub,
        "checklist": [{"id": cid, "label": label, "done": cid in done} for cid, label in CHECKLIST],
        "checks_done": len(done),
        "checks_total": len(CHECKLIST),
        "care": {
            "active": care_active,
            "cues": list(cues_seen.values()),
            "actions": [{"id": aid, "label": label, "done": care_active and aid in actions} for aid, label in ACTIONS],
            "actions_done": len(actions) if care_active else 0,
        },
        "flags": [f.to_dict() for f in flags],
        "suggestion": _suggest(turns, flags, done, actions, care_active),
        "avg_wpm": avg_wpm,
    }


def _level(score: int, started: bool, care_active: bool) -> tuple[str, str, str, str]:
    if not started:
        return ("idle", "Ready", "Ready when you are",
                "Start talking, or play a demo call. Care listens for signs a customer needs more support, and coaches you in real time.")
    if score >= 80:
        if care_active:
            return ("good", "On track", "Handling this with care",
                    "You noticed they needed more, and adapted. Keep the pace gentle.")
        return ("good", "On track", "Clear, calm and trustworthy",
                "Clear who you are and why you're calling, with no pressure. Keep listening for cues.")
    if score >= 60:
        return ("ok", "On track", "Mostly there",
                "A few things still to land. Check the lists below.")
    if score >= 35:
        return ("warn", "Needs attention", "Slow down",
                "The customer may need more time or support than this call is giving them.")
    return ("bad", "At risk", "Pause and reset",
            "This call could harm the customer, or sound like a scam to them. Use the next step to reset.")


def _suggest(turns: list[dict], flags: list[Flag], done: set[str], actions: set[str], care_active: bool) -> Optional[dict]:
    last = None
    for i in range(len(turns) - 1, -1, -1):
        if (turns[i].get("text") or "").strip():
            last = i
            break
    if last is None:
        return None

    recent = [f for f in flags if f.turn_index == last]
    order = {"high": 0, "medium": 1, "low": 2}
    if recent:
        f = sorted(recent, key=lambda x: order[x.severity])[0]
        title = {
            "doubt": "Help them check you out",
            "care": "Acknowledge and adapt",
            "pace": "Slow down",
            "missing": "Tell them who you are",
        }.get(f.kind, "Try saying this instead")
        if f.id in ("pressure_after_care", "no_ack", "jargon"):
            title = "Reset the call"
        return {"title": title, "say": f.say, "why": f.why, "flag_id": f.id, "tone": f.severity}

    if turns[last].get("speaker", "agent") == "agent":
        if care_active and len(actions) < ENOUGH_ACTIONS:
            for aid, _label in ACTIONS:
                if aid not in actions:
                    return {"title": "Something that would help them", "say": ACTION_SAY[aid], "why": ACTION_WHY[aid],
                            "flag_id": f"action_{aid}", "tone": "info"}
        for cid, _label in CHECKLIST:
            if cid not in done:
                return {"title": "Your next step", "say": _CHECK_SAY[cid], "why": _CHECK_WHY[cid],
                        "flag_id": f"check_{cid}", "tone": "info"}
    if len(done) == len(CHECKLIST):
        return {"title": "All trust checks done", "say": "", "why": "Nicely done. Stay unhurried and let them lead.",
                "flag_id": "all_done", "tone": "good"}
    return None


# --------------------------------------------------------------------------
# Recap
# --------------------------------------------------------------------------


def build_recap(turns: list[dict]) -> dict:
    state = analyze_call(turns)
    lines = ["# Care call recap", ""]
    lines.append(f"**Care score:** {state['score']}/100 ({state['headline']})  ")
    lines.append(f"**Trust checks:** {state['checks_done']} of {state['checks_total']}  ")
    if state["avg_wpm"]:
        lines.append(f"**Average pace:** ~{state['avg_wpm']} words a minute  ")
    care = state["care"]
    lines += ["", "## Care cues heard"]
    if not care["cues"]:
        lines.append("None heard.")
    for c in care["cues"]:
        lines.append(f"- {c['label']} (turn {c['turn_index'] + 1})")
    if care["active"]:
        lines += ["", "## How the agent adapted"]
        for a in care["actions"]:
            lines.append(f"- [{'x' if a['done'] else ' '}] {a['label']}")
    lines += ["", "## Trust checks"]
    for c in state["checklist"]:
        lines.append(f"- [{'x' if c['done'] else ' '}] {c['label']}")
    lines += ["", "## Moments to review"]
    moments = [f for f in state["flags"] if f["kind"] != "care"]
    if not moments:
        lines.append("Nothing flagged.")
    for f in moments:
        who = "Agent" if f["speaker"] == "agent" else "Customer"
        ev = f' "{f["evidence"]}"' if f["evidence"] else ""
        lines.append(f"- **{f['label']}** ({f['severity']}, turn {f['turn_index'] + 1}, {who}){ev}")
        if f["say"]:
            lines.append(f"  - Try: {f['say']}")
    lines += ["", "## Transcript"]
    for t in turns:
        if (t.get("text") or "").strip():
            lines.append(f"- **{'Agent' if t.get('speaker', 'agent') == 'agent' else 'Customer'}:** {t['text'].strip()}")
    lines += ["", "_Care cues are signals that someone may need extra support. They are not a diagnosis. No audio is stored._"]
    return {"state": state, "markdown": "\n".join(lines) + "\n"}
