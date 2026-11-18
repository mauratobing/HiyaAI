import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analyzer as an  # noqa: E402
from app.analyzer import analyze_call  # noqa: E402
from app.llm import parse_concerns  # noqa: E402

SCENARIOS = {s["id"]: s for s in json.loads((Path(__file__).parent.parent / "app" / "scenarios.json").read_text())}


def run(scenario_id, upto=None):
    turns = SCENARIOS[scenario_id]["turns"]
    return analyze_call(turns[:upto] if upto else turns)


def ids(state):
    return {f["id"] for f in state["flags"]}


def agent(text, **kw):
    return {"speaker": "agent", "text": text, **kw}


def customer(text):
    return {"speaker": "customer", "text": text}


INTRO = agent("Hello, my name is Sam and I'm calling from Northbridge Finance about your account.")


def test_empty_call_is_idle():
    s = analyze_call([])
    assert s["level"] == "idle" and s["suggestion"] is None and not s["care"]["active"]


def test_handled_with_care_scores_top_and_is_clean():
    s = run("bereavement_good")
    assert s["score"] >= 90 and s["level"] == "good"
    assert s["headline"] == "Handling this with care"
    assert s["care"]["active"] and s["care"]["actions_done"] == 5
    assert not [f for f in s["flags"] if f["kind"] in ("risk", "pace")]


def test_same_call_rushed_scores_low_and_flags_pressure():
    s = run("bereavement_rushed")
    assert s["score"] < 35
    assert {"pressure_after_care", "jargon", "pace", "no_ack", "doubt"} <= ids(s)
    assert {"care_life_event", "care_understanding"} <= ids(s)


def test_hard_to_hear_recovers():
    s = run("hard_to_hear")
    assert {"care_repeat", "care_understanding"} <= ids(s)
    early = run("hard_to_hear", upto=3)
    assert {"pressure_after_care", "jargon", "no_ack"} <= ids(early)
    assert s["care"]["actions_done"] >= 3
    assert s["score"] > early["score"]


def test_each_cue_category_is_detected():
    samples = {
        "care_life_event": "My husband passed away last month.",
        "care_health": "I've been unwell and in hospital.",
        "care_money": "I can't afford this at the moment.",
        "care_understanding": "I'm confused, I don't understand.",
        "care_repeat": "Sorry, what was that? Could you speak up?",
        "care_distress": "I'm feeling really anxious about this.",
    }
    for want, text in samples.items():
        assert want in ids(analyze_call([INTRO, customer(text)])), want


def test_care_cue_alone_does_not_cost_points():
    base = analyze_call([INTRO, customer("Okay, go on.")])["score"]
    with_cue = analyze_call([INTRO, customer("I'm a bit confused.")])["score"]
    assert with_cue >= base - 2  # only the missing reassurance bonus differs


def test_acknowledgement_alone_does_not_excuse_pushing_payment():
    s = analyze_call([INTRO, customer("My wife passed away in May."),
                      agent("I'm sorry to hear that. Can I take a payment today?")])
    assert "pressure_after_care" in ids(s)


def test_pause_offer_excuses_a_payment_mention():
    s = analyze_call([INTRO, customer("My wife passed away in May."),
                      agent("I'm so sorry. No pressure at all, we can talk about payment another time.")])
    assert "pressure_after_care" not in ids(s)


def test_payment_after_intro_without_cue_is_fine():
    s = analyze_call([INTRO, agent("Would you like to talk about how you'd like to pay?")])
    assert not ({"pay_before_id", "pressure_after_care"} & ids(s))


def test_payment_before_intro_is_flagged():
    s = analyze_call([agent("Can I take a payment from you today?")])
    assert "pay_before_id" in ids(s)


def test_fast_speech_threshold_is_lower_after_a_cue():
    text = "I just wanted to quickly run through the details of your agreement and the options that are open to you"
    # 19 words in 8s is about 142 wpm: fine normally, but not for someone who needs time
    assert "pace" not in ids(analyze_call([INTRO, agent(text, duration_ms=8000)]))
    assert "pace" in ids(analyze_call([INTRO, customer("I'm confused."), agent(text, duration_ms=7000)]))
    assert "pace" in ids(analyze_call([agent(text, duration_ms=4000)]))


def test_ignoring_a_cue_is_flagged_and_coached():
    s = analyze_call([INTRO, customer("I'm confused."), agent("Okay, so about your account.")])
    assert "no_ack" in ids(s) and s["suggestion"]["flag_id"] == "no_ack"


def test_next_step_after_cue_is_to_adapt_not_a_trust_check():
    s = analyze_call([INTRO, customer("I'm confused."), agent("Let me take you through it step by step.")])
    assert s["suggestion"]["flag_id"] == "action_ack"


def test_next_step_suggests_missing_check_without_cue():
    s = analyze_call([agent("Hello, my name is Sam and I'm calling from Northbridge Finance.")])
    assert s["suggestion"]["flag_id"] == "check_reason"


def test_scam_patterns_still_detected():
    s = analyze_call([agent("Pay your balance right now and give me the security code. Don't tell anyone about this call.")])
    assert {"pay_before_id", "urgency", "credentials", "secrecy"} <= ids(s)
    assert s["score"] < 35


def test_name_not_confused_by_ordinary_phrases():
    s = analyze_call([agent("It's urgent and I'm calling about your account.")])
    assert not any(c["done"] for c in s["checklist"] if c["id"] in ("name", "company"))


def test_negation_ignores_nothing_urgent():
    s = analyze_call([INTRO, agent("Nothing urgent, I will never ask for your PIN.")])
    assert not ({"urgency", "credentials"} & ids(s))


def test_score_is_bounded():
    s = analyze_call([agent("pin password otp gift card urgent right now police")] * 20)
    assert 0 <= s["score"] <= 100


def test_every_suggested_line_is_itself_safe_to_say():
    """Care's own suggested wording must never trip a risk flag."""
    care_lines = [c[4] for c in an.CARE_CUES] + list(an.ACTION_SAY.values()) + [
        an.DOUBT_SAY, an.PACE_SAY, an.JARGON_SAY, an.NO_ACK_SAY, an.PRESSURE_AFTER_SAY]
    plain_lines = [r.say for r in an.RULES] + [an._PAYMENT_SAY] + list(an._CHECK_SAY.values())
    for line in care_lines:      # said after a customer has shown a care cue
        state = analyze_call([INTRO, customer("I'm confused."), agent(line)])
        bad = [f["id"] for f in state["flags"] if f["turn_index"] == 2 and f["kind"] in ("risk", "pace")]
        assert not bad, (bad, line)
    for line in plain_lines:     # said on an ordinary call
        state = analyze_call([INTRO, agent(line)])
        bad = [f["id"] for f in state["flags"] if f["turn_index"] == 1 and f["kind"] in ("risk", "pace")]
        assert not bad, (bad, line)


def test_recap_mentions_cues_and_adaptations():
    from app.analyzer import build_recap
    md = build_recap(SCENARIOS["bereavement_good"]["turns"])["markdown"]
    assert "Care cues heard" in md and "How the agent adapted" in md and "not a diagnosis" in md


def test_llm_parse_is_robust():
    raw = 'Sure! {"concerns": [{"label": "Implied threat", "severity": "weird", "quote": "q", "why": "w", "say": "s"}, {"nolabel": 1}]}'
    out = parse_concerns(raw)
    assert len(out) == 1 and out[0]["severity"] == "low"
    assert parse_concerns("no json here") == []


# ---------------------------------------------------------------- simulated customer
from app import customer as sim  # noqa: E402


def talk(persona, agent_lines):
    """Run a practice call: the agent opens, and the customer replies to each agent line."""
    turns = []
    for line in agent_lines:
        turns.append(agent(line))
        r = sim.reply(persona, turns)
        if r["text"]:
            turns.append(customer_turn(r["text"]))
        if r["ended"]:
            return turns, True
    return turns, False


def customer_turn(text):
    return {"speaker": "customer", "text": text}


def test_customer_asks_who_when_agent_does_not_introduce():
    turns, ended = talk("bereaved", ["I'm calling about your account."])
    assert turns[-1]["text"] in sim.PERSONAS["bereaved"]["who"] and not ended


def test_customer_asks_what_its_about_then_opens_up():
    turns, ended = talk("bereaved", ["Hi, it's Sam from Northbridge Finance."])
    assert turns[-1]["text"] == sim.PERSONAS["bereaved"]["ask"] and not ended
    turns, ended = talk("bereaved", ["Hi, it's Sam from Northbridge Finance.", "I'm calling about your car finance agreement."])
    assert turns[-1]["text"] == sim.PERSONAS["bereaved"]["reveal"] and not ended


def test_customer_does_not_speak_before_the_agent():
    assert sim.reply("bereaved", []) == {"text": None, "ended": False}


def test_the_opening_line_counts_as_name_and_company():
    s = analyze_call([agent("Hi, it's Sam from Northbridge Finance.")])
    done = {c["id"] for c in s["checklist"] if c["done"]}
    assert {"name", "company"} <= done


def test_pushing_makes_the_customer_pull_back_then_hang_up():
    turns, ended = talk("bereaved", [
        "Hi, it's Sam from Northbridge Finance.",
        "I'm calling about your agreement.",
        "Can I take a payment today?",
        "I do need a payment today, it can't wait.",
        "We really do have to sort the payment today.",
    ])
    # two pull-backs first, then they end the call
    assert ended and turns[-1]["text"] == sim.PERSONAS["bereaved"]["end_pushed"]
    assert sum(t["text"] in sim.PERSONAS["bereaved"]["pushed"] for t in turns) == 2


def test_adapting_softens_the_customer_and_gets_a_good_ending():
    turns, ended = talk("bereaved", [
        "Hi, it's Sam from Northbridge Finance.",
        "I'm calling about your agreement.",
        "I'm so sorry to hear that. There's no pressure at all, and someone you trust is welcome to join us.",
        "Of course, I'll call you back whenever suits you.",
    ])
    assert ended and turns[-1]["text"] == sim.PERSONAS["bereaved"]["end_ok"]
    assert analyze_call(turns)["score"] >= 70


def test_jargon_is_met_with_confusion():
    turns, _ = talk("hearing", [
        "Hello, my name is Tom and I'm calling from Northbridge Finance about your account.",
        "The direct debit mandate was returned and there is an outstanding balance.",
    ])
    assert turns[-1]["text"] in sim.PERSONAS["hearing"]["jargon"]


def test_scam_like_requests_end_the_call():
    turns, ended = talk("wary", [
        "Hi, it's Sam from Northbridge Finance.",
        "Please read me the security code.",
    ])
    assert ended and turns[-1]["text"] == sim.END_SCAM


def test_ended_call_stays_ended():
    turns, ended = talk("bereaved", ["I'm calling about your account."] * 3)
    assert ended
    assert sim.reply("bereaved", turns + [agent("Hello?")]) == {"text": None, "ended": True}


def test_every_persona_has_complete_lines_and_endings_are_distinct():
    need = {"label", "blurb", "name", "context", "ask", "who", "reveal", "confused", "pushed", "end_pushed", "jargon", "soft", "neutral", "end_ok"}
    for pid, p in sim.PERSONAS.items():
        assert need <= set(p), pid
        assert p["end_ok"] != p["end_pushed"]
        # the opening line must actually contain a cue (or doubt) so Care reacts to it
        st = analyze_call([INTRO, customer_turn(p["reveal"])])
        assert any(f["id"].startswith("care_") or f["id"] == "doubt" for f in st["flags"]), pid
