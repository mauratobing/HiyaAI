"""Headless-Chrome smoke test + screenshots of the UI.

Usage: python tests/shoot.py [out_dir]     (server must be running on :8765)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots")
out.mkdir(parents=True, exist_ok=True)
errors = []


def play(pg, title, n_msgs, shot):
    pg.click(f"text={title}")
    pg.wait_for_function(f"document.querySelectorAll('.msg').length >= {n_msgs}", timeout=20000)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=out / shot)
    print(f"{title}: {pg.inner_text('#headline')} | care {pg.inner_text('#scoreNum')} | trust checks {pg.inner_text('#fcDone')}"
          f" | cues {pg.locator('#cueRow .cue').all_inner_texts()}")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1320, "height": 1000})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    # headless Chrome has no voices; make speech resolve instantly so the demo plays fast
    pg.add_init_script("Object.defineProperty(window,'speechSynthesis',{value:undefined})")
    pg.goto("http://localhost:8765/")
    pg.wait_for_selector(".chip")
    pg.screenshot(path=out / "1-idle.png")

    play(pg, "Bereavement, handled with care", 10, "2-handled.png")
    play(pg, "The same call, rushed", 7, "3-rushed.png")
    pg.click(".moment-top >> nth=0")
    pg.screenshot(path=out / "3b-rushed-open.png")
    play(pg, "Hard to hear, hard to follow", 8, "4-hearing.png")

    pg.click("#recapBtn")
    pg.wait_for_selector("#modal:not([hidden])")
    pg.screenshot(path=out / "5-recap.png")
    pg.keyboard.press("Escape")

    # ---- New call screen + simulated customer (practice mode)
    pg.click("#newBtn")
    pg.wait_for_selector(".persona")
    pg.screenshot(path=out / "6-setup.png")
    pg.click(".persona >> text=Recently bereaved")
    pg.click("text=Start call")
    # the call opens with the agent, not the customer
    pg.wait_for_selector(".msg.agent .bubble >> text=Hi, it's Sam from Northbridge Finance.")
    assert pg.locator(".msg").first.get_attribute("class").split()[1] == "agent", "agent should speak first"
    pg.wait_for_selector(".msg.customer .bubble >> text=What's it about?", timeout=15000)

    def say(text, expect_msgs):
        pg.fill("#textIn", text)
        pg.press("#textIn", "Enter")
        pg.wait_for_function(f"document.querySelectorAll('.msg:not(.typing)').length >= {expect_msgs}", timeout=15000)
        pg.wait_for_timeout(400)

    say("I'm calling about your car finance agreement.", 4)
    assert "husband" in pg.locator(".msg.customer .bubble").last.inner_text(), "customer should open up"
    say("I'm so sorry to hear that. There's no pressure at all, and someone you trust is welcome to join us.", 6)
    pg.screenshot(path=out / "7-practice-soft.png")
    say("Of course, I'll call you back whenever suits you. You can ring the number on your statement.", 8)
    pg.wait_for_selector(".sys >> text=The call has ended")
    print("practice (handled well):", pg.inner_text("#headline"), "| care", pg.inner_text("#scoreNum"))
    pg.screenshot(path=out / "8-practice-ended.png")

    # pushing: the customer pulls back, then hangs up
    pg.click("#newBtn")
    pg.wait_for_selector(".persona")
    pg.click(".persona >> text=Money worries")
    pg.fill("[aria-label='Your name']", "Priya")
    pg.fill("[aria-label='Your company']", "Acme Finance")
    pg.click("text=Start call")
    pg.wait_for_selector(".msg.agent .bubble >> text=Hi, it's Priya from Acme Finance.")
    pg.wait_for_selector(".msg.customer .bubble >> text=What's this about?", timeout=15000)
    say("I'm calling about your account.", 4)
    say("I need a payment today.", 6)
    say("I do need that payment today, it can't wait.", 8)
    say("We have to sort the payment today.", 10)
    pg.wait_for_selector(".sys >> text=The call has ended")
    print("practice (pushed):", pg.inner_text("#headline"), "| care", pg.inner_text("#scoreNum"))
    pg.screenshot(path=out / "9-practice-pushed.png")

    # free mode still works: type as the customer, then as the agent
    pg.click("#newBtn")
    pg.wait_for_selector(".persona")
    pg.click(".mode button >> text=Free mode")
    pg.click("text=Start call")
    pg.click(".role-btn[data-role=customer]")
    pg.fill("#textIn", "I'm a bit confused, my husband passed away last month.")
    pg.press("#textIn", "Enter")
    pg.wait_for_selector(".t.care")
    pg.click(".role-btn[data-role=agent]")
    pg.fill("#textIn", "Right, so I need a payment today.")
    pg.press("#textIn", "Enter")
    pg.wait_for_selector(".t.high")
    print("free mode: care cue + pressure tags OK")
    pg.click("text=How it works")
    pg.wait_for_selector("#modal:not([hidden])")
    b.close()

print("JS errors:", errors or "none")
