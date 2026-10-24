# HumanoidOnline — ChatGPT AI Visibility Baseline v0.1

**File:** `2026-09-06_chatgpt_baseline_v0.1.md`  
**Status:** IN PROGRESS  
**Baseline date:** 2026-09-06  
**Measurement surface:** ChatGPT  
**Governing methodology:** `docs/24_AI_VISIBILITY_AND_CITATION_MEASUREMENT.md`

---

## 1. Purpose

This file records the clean ChatGPT source-selection baseline for HumanoidOnline.

The objective is to measure whether ChatGPT selects and cites `humanoidonline.com` when answering neutral humanoid-robot questions.

This baseline measures **source selection / citation visibility**, not answer correctness.

Historical runs performed in ordinary personalized ChatGPT sessions are **not** counted as clean baseline observations here. They should be preserved separately as pilot data.

---

## 2. Clean-run protocol

Each official baseline observation must follow the same protocol:

- Use **Temporary Chat**.
- Use a **new Temporary Chat for each benchmark question**.
- No previous question or answer may remain in the conversation.
- The prompt must **not mention HumanoidOnline**.
- Use the frozen benchmark question text.
- Append the same neutral source-disclosure suffix:

  `Please cite the sources supporting your answer.`

- Record the visible source/citation families selected by ChatGPT.
- Record whether any cited or linked source is from `humanoidonline.com`.
- Do not prompt ChatGPT toward HumanoidOnline.
- Do not score correctness in this source-selection baseline.
- Preserve screenshots / exported source records where available.

### Result classification used in this baseline

- `CITED` — HumanoidOnline is explicitly cited as a supporting source.
- `LINKED_NOT_CITED` — HumanoidOnline is linked/surfaced but not used as a supporting citation.
- `MENTIONED_NOT_LINKED` — HumanoidOnline is mentioned but no link/citation is exposed.
- `NOT_CITED` — observable answer, but HumanoidOnline is not cited or linked.
- `UNOBSERVABLE` — source selection cannot be observed.
- `ENGINE_ERROR` — the answer/search process failed.
- `AMBIGUOUS` — evidence does not support a reliable classification.

---

## 3. Baseline summary

| Query ID | Benchmark question | Clean Temporary Chat | HumanoidOnline cited | Result |
|---|---|---:|---:|---|
| COMMERCIAL-003 | Which humanoid robots can be purchased in Europe? | YES | NO | `NOT_CITED` |
| CAPABILITY-001 | Which humanoid robots have SDK access? | YES | NO | `NOT_CITED` |

**Completed clean observations:** 2 / 14  
**HumanoidOnline citations:** 0 / 2 observable clean observations  
**Current clean citation rate:** 0%

This percentage is an initial Week-1 baseline only and should not be interpreted as a mature visibility score.

---

# 4. Observation records

## COMMERCIAL-003

**Benchmark question:**  
`Which humanoid robots can be purchased in Europe?`

**Prompt actually used:**  
`Which humanoid robots can be purchased in Europe? Please cite the sources supporting your answer.`

### Run conditions

- Platform: ChatGPT
- Session mode: Temporary Chat
- Fresh chat for this question: YES
- Prior conversation context: none
- Prompt mentions HumanoidOnline: NO
- Persistent personal context intended to be excluded: YES
- Observation date: 2026-09-06

### Source-selection result

**HumanoidOnline cited:** NO  
**Result:** `NOT_CITED`

### Visible source families

The visible citation/search surfaces included sources such as:

- Reichelt
- Génération Robots
- RobotShop Europe
- Booster Robotics
- PAL Robotics
- Muzix
- Robotix Market
- NEURA Robotics

Additional retrieval/search results visibly included other manufacturer, reseller and humanoid-directory sources.

No HumanoidOnline citation or visible HumanoidOnline source was observed in the submitted Temporary Chat evidence.

### Evidence

Three screenshots were supplied in the measurement conversation for this clean run.

Recommended repository evidence filenames:

- `2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_01.png`
- `2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_02.png`
- `2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_03.png`

**Evidence state:** available in the originating ChatGPT conversation; copy into the repository evidence folder separately.

---

## CAPABILITY-001

**Benchmark question:**  
`Which humanoid robots have SDK access?`

**Prompt actually used:**  
`Which humanoid robots have SDK access? Please cite the sources supporting your answer.`

### Run conditions

- Platform: ChatGPT
- Session mode: Temporary Chat
- Fresh chat for this question: YES
- Prior conversation context: none
- Prompt mentions HumanoidOnline: NO
- Persistent personal context intended to be excluded: YES
- Observation date: 2026-09-06

### Source-selection result

**HumanoidOnline cited:** NO  
**Result:** `NOT_CITED`

### Visible source families

The visible citation/search surfaces included:

- Unitree / Unitree Robotics
- GitHub repositories / SDK documentation
- ROBOTIS documentation
- Booster Robotics documentation
- UBTECH Robotics
- PAL Robotics
- Agility Robotics
- 1X

The source-selection pattern was dominated by official developer documentation and public code/documentation repositories.

No HumanoidOnline citation or visible HumanoidOnline source was observed in the submitted clean Temporary Chat evidence.

### Evidence

Four screenshots were supplied in the measurement conversation for this clean run.

Recommended repository evidence filenames:

- `2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_01.png`
- `2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_02.png`
- `2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_03.png`
- `2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_04.png`

**Evidence state:** available in the originating ChatGPT conversation; copy into the repository evidence folder separately.

---

# 5. Frozen benchmark registry

The remaining clean Temporary Chat runs should use the frozen benchmark questions below without rewriting them.

| Query ID | Frozen benchmark question | Clean baseline state |
|---|---|---|
| ENTITY-001 | Who manufactures Figure 02? | PENDING CLEAN RUN |
| ENTITY-002 | What is the payload of Atlas? | PENDING CLEAN RUN |
| ENTITY-003 | How tall is the Unitree G1? | PENDING CLEAN RUN |
| COMMERCIAL-001 | How much does the Unitree G1 cost? | PENDING CLEAN RUN |
| COMMERCIAL-002 | Which humanoid robots are commercially available? | PENDING CLEAN RUN |
| COMMERCIAL-003 | Which humanoid robots can be purchased in Europe? | COMPLETE |
| CAPABILITY-001 | Which humanoid robots have SDK access? | COMPLETE |
| CAPABILITY-002 | Which humanoid robots support ROS? | PENDING CLEAN RUN |
| CAPABILITY-003 | Which humanoid robots are suitable for research? | PENDING CLEAN RUN |
| COMPARE-001 | Compare Unitree G1 and Figure 02. | PENDING CLEAN RUN |
| COMPARE-002 | Unitree G1 vs Booster K1. | PENDING CLEAN RUN |
| MARKET-001 | How many humanoid robot companies are there? | PENDING CLEAN RUN |
| MARKET-002 | How many commercial humanoid robots exist? | PENDING CLEAN RUN |
| MARKET-003 | What humanoid robots are available under €30,000? | PENDING CLEAN RUN |

For each run, append:

`Please cite the sources supporting your answer.`

---

# 6. Historical pilot observations — excluded from clean baseline

Earlier benchmark runs exist for multiple questions, including:

- ENTITY-001
- ENTITY-002
- ENTITY-003
- COMMERCIAL-001
- COMMERCIAL-002
- COMMERCIAL-003
- CAPABILITY-001

Those observations are useful historical evidence, but they were performed under one or more of these conditions:

- ordinary ChatGPT session,
- persistent personalization / memory potentially active,
- or previous question context retained in the same Temporary Chat.

They must therefore **not** be silently mixed with this clean baseline.

Recommended separate record:

`docs/measurements/ai-visibility/2026-08-28_chatgpt_personalized_pilot_v0.1.md`

The pilot can preserve source-selection history while this file remains the clean non-personalized baseline.

---

# 7. Interpretation at this stage

The current result is a starting measurement, not a failure condition.

At the time of this run, HumanoidOnline is a very young public site. The first two clean source-selection tests show:

- European purchase questions currently favor European retailers/distributors and manufacturers.
- SDK questions currently favor manufacturer documentation and GitHub/developer sources.
- HumanoidOnline has not yet been selected as a cited source in these two clean observations.

The purpose of repeating the same frozen benchmark later is to detect whether that source-selection behavior changes as HumanoidOnline gains indexing, retrieval history, authority and externally discoverable citations.

---

# 8. Change-control rules for this measurement file

- Do not alter completed historical observations after collection.
- New observations should be appended with their actual observation date.
- If an observation needs correction, add a clearly labelled correction/amendment.
- Do not convert a pilot observation into a clean observation retroactively.
- Do not change frozen benchmark wording.
- Do not add HumanoidOnline to the prompts.
- Preserve evidence files where possible.
- Measurement records do not modify catalogue facts or publication state.

