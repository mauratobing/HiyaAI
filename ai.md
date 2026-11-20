# AI usage

## Tools used to build this

- **Claude (Anthropic), via Claude Code**: used as a coding agent to write most of the code in this repo (FastAPI backend, rule engine, HTML/CSS/JS front end, tests, README), working from a spec I steered.
- **Claude (chat)**: used earlier to brainstorm the idea, narrow it down, and map it to the challenge track.

## What I directed vs. what the AI wrote

- **Mine:** the problem choice (extend Hiya's "identity before the call" with "care during the call"), the decision to narrow it to customers who may need more support after judging my first scenarios too extreme, the track, the visual direction (a soft teal card UI with a chat-style transcript and a friendly mascot, instead of a default Streamlit look), and the rename to Care.
- **AI-written, then reviewed and tested:** the code. The test suite covers the scoring engine, and a headless-Chrome script plays each demo and checks the UI for errors. Testing found real bugs, which were fixed:
  - the rules flagged the app's own suggested wording (for example "I will never ask for your PIN") as risky;
  - "nothing urgent" was flagged as urgency;
  - a suggested plain-English line contained the word "payment", so it tripped the "pushing after a cue" rule.
  A test now asserts that none of Care's own suggested lines trigger a risk flag.

## AI inside the product

- **Speech-to-text:** the browser's built-in speech recognition (Web Speech API; in Chrome this is a cloud service run by the browser vendor).
- **Text-to-speech:** the browser's built-in speech synthesis, for demo playback and optional spoken "whisper" nudges.
- **Scoring and cue detection:** a deterministic, rule-based engine, with no model involved, so every score is explainable.
- **Simulated customer (practice mode):** also rule-based, not a model. It reuses the coach's detectors to react to what the agent says and picks from written lines per persona.

## Data and sensitivity

Care turns live speech into text using the browser’s built-in speech recognition (a cloud service run by the browser vendor in Chrome), then analyses that text on the machine it runs on. It looks for words that can signal health, bereavement or money problems. It does this in memory only: no audio is recorded or stored by Care, the server keeps no state, and the recap is generated on request and not saved. Cues are treated as prompts to listen more closely, never as a diagnosis.
