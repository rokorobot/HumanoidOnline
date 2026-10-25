# HumanoidOnline — ChatGPT Personalized Pilot v0.1

**File:** `2026-08-28_chatgpt_personalized_pilot_v0.1.md`  
**Status:** HISTORICAL PILOT / NON-CLEAN BASELINE  
**Pilot date:** 2026-08-28  
**Measurement surface:** ChatGPT  
**Governing methodology:** `docs/24_AI_VISIBILITY_AND_CITATION_MEASUREMENT.md`

---

## 1. Purpose

This file preserves the first HumanoidOnline ChatGPT source-selection observations collected before the clean Temporary Chat protocol was adopted.

These runs are useful as historical evidence of early source selection, retrieval patterns, and citation behavior, but they are **not part of the clean non-personalized baseline**.

The reason is methodological:

- some runs were made in ordinary ChatGPT sessions where persistent personalization / memory may have been active;
- one later Temporary Chat SDK run reused prior conversation context;
- therefore these observations cannot be treated as independent clean-discovery measurements.

The official clean baseline is recorded separately in:

`docs/measurements/ai-visibility/2026-09-06_chatgpt_baseline_v0.1.md`

---

## 2. Pilot protocol status

The pilot questions used neutral benchmark wording and did **not intentionally prompt toward HumanoidOnline**.

The recurring source-disclosure suffix used was:

`Please cite the sources supporting your answer.`

However, because persistent personalization / memory could have influenced answers or retrieval, these observations are preserved as:

`PERSONALIZED_PILOT`

They must not be merged into clean Temporary Chat citation-rate calculations.

---

## 3. Pilot summary

| Query ID | Benchmark question | Main source families observed | HumanoidOnline cited | Pilot result |
|---|---|---|---:|---|
| ENTITY-001 | Who manufactures Figure 02? | Figure official, Figure launch announcement, BMW Group | NO | `NOT_CITED` |
| ENTITY-002 | What is the payload of Atlas? | Boston Dynamics | NO | `NOT_CITED` |
| ENTITY-003 | How tall is the Unitree G1? | Unitree official | NO | `NOT_CITED` |
| COMMERCIAL-001 | How much does the Unitree G1 cost? | Unitree official, Unitree store, RobotShop Europe | NO | `NOT_CITED` |
| COMMERCIAL-002 | Which humanoid robots are commercially available? | Unitree, Booster, Engineered Arts, Agility, 1X, Boston Dynamics, Apptronik, Figure, directories/resellers | NO | `NOT_CITED` |
| COMMERCIAL-003 | Which humanoid robots can be purchased in Europe? | RobotShop Europe, Engineered Arts | NO | `NOT_CITED` |
| CAPABILITY-001-PILOT | Which humanoid robots have SDK access? | Unitree, GitHub, ROBOTIS, Booster, UBTECH, PAL and others | NO | `NOT_CITED` |

**Pilot observations preserved:** 7  
**HumanoidOnline citations observed:** 0 / 7

This pilot citation rate must **not** be compared directly with the clean baseline without preserving the protocol difference.

---

# 4. Observation records

## ENTITY-001

**Benchmark question:**  
`Who manufactures Figure 02?`

**Prompt used:**  
`Who manufactures Figure 02? Please cite the sources supporting your answer.`

### Observed source selection

Visible / named supporting sources included:

- Figure official company page
- Figure official launch announcement
- BMW Group as independent confirmation

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

Historical ChatGPT conversation record is available.

No repository screenshot file is currently guaranteed to survive for this observation.

Recommended evidence classification:

`historical conversation record`

---

## ENTITY-002

**Benchmark question:**  
`What is the payload of Atlas?`

**Prompt used:**  
`What is the payload of Atlas? Please cite the sources supporting your answer.`

### Observed source selection

Visible citation cards were from:

- Boston Dynamics

User clarification at the time confirmed the visible citation cards were Boston Dynamics sources.

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

Historical ChatGPT conversation record available. Screenshot was supplied during the original run, but raw screenshot recovery should be verified before adding a repository evidence file.

---

## ENTITY-003

**Benchmark question:**  
`How tall is the Unitree G1?`

**Prompt used:**  
`How tall is the Unitree G1? Please cite the sources supporting your answer.`

### Observed source selection

Visible source families included:

- Unitree official G1 specification / product page
- Unitree official product information

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

Historical ChatGPT conversation record available. Screenshot was supplied during the original run, but raw screenshot recovery should be verified before adding a repository evidence file.

---

## COMMERCIAL-001

**Benchmark question:**  
`How much does the Unitree G1 cost?`

**Prompt used:**  
`How much does the Unitree G1 cost? Please cite the sources supporting your answer.`

### Observed source selection

Visible source families included:

- Unitree official G1 / specification page
- Unitree Robotics official online store
- RobotShop Europe

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

Historical ChatGPT conversation record available. Screenshot was supplied during the original run, but raw screenshot recovery should be verified before adding a repository evidence file.

---

## COMMERCIAL-002

**Benchmark question:**  
`Which humanoid robots are commercially available?`

**Prompt used:**  
`Which humanoid robots are commercially available? Please cite the sources supporting your answer.`

### Observed source selection

The answer used or surfaced source families including:

- Unitree Robotics
- Booster Robotics
- Engineered Arts
- Agility Robotics
- 1X
- Boston Dynamics
- Apptronik
- Figure

The broader retrieved source pool also contained multiple humanoid directories, databases, resellers and aggregators, including examples such as:

- Humanoza
- RoboZaps
- Deploy Report
- The Bot Scout
- Sourcebotics
- Humanoid Network
- HumanoidHub
- Rivet Index

The exported source record contained a large retrieved source set and **no HumanoidOnline source**.

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

A full exported source record survives.

Recommended repository path:

`docs/measurements/ai-visibility/2026-08-28_chatgpt_personalized_pilot_evidence/COMMERCIAL-002.md`

This file should be preserved unchanged as raw evidence.

### Methodological note

The exported source record also showed that persistent Memory / personalization context was present during the run.

That is one of the main reasons this observation remains in the personalized pilot rather than the clean Temporary Chat baseline.

---

## COMMERCIAL-003

**Benchmark question:**  
`Which humanoid robots can be purchased in Europe?`

**Prompt used:**  
`Which humanoid robots can be purchased in Europe? Please cite the sources supporting your answer.`

### Observed source selection

The answer was dominated by:

- RobotShop Europe
- Engineered Arts

The answer text also mentioned HumanoidOnline in prose, despite the prompt not mentioning HumanoidOnline.

However, the actual visible supporting citations did **not** cite HumanoidOnline.

This behavior strongly suggested persistent personalization / context could be reaching the answer.

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Evidence state

A full exported source record survives.

Recommended repository path:

`docs/measurements/ai-visibility/2026-08-28_chatgpt_personalized_pilot_evidence/COMMERCIAL-003.md`

### Methodological note

Because HumanoidOnline appeared in answer prose without being requested in the prompt, this run became an important trigger for switching the official benchmark protocol to a fresh Temporary Chat per question.

---

## CAPABILITY-001-PILOT

**Benchmark question:**  
`Which humanoid robots have SDK access?`

**Prompt used:**  
`Which humanoid robots have SDK access? Please cite the sources supporting your answer.`

### Observed source selection

Visible source families included:

- Unitree / Unitree support
- GitHub SDK repositories
- ROBOTIS documentation
- Booster Robotics documentation
- UBTECH documentation
- PAL Robotics
- other manufacturer/developer sources

**HumanoidOnline cited:** NO  
**Pilot result:** `NOT_CITED`

### Why this run remains pilot

This SDK question was asked in the **same Temporary Chat** as the earlier Europe-purchase query.

The answer explicitly referred back to the previous robot list.

Therefore:

- Temporary Chat personalization isolation: YES
- fresh standalone conversation for this query: NO
- prior conversation context: YES

This observation is useful, but it is not eligible for the clean standalone baseline.

A later CAPABILITY-001 run was repeated in a brand-new Temporary Chat and is recorded in the clean baseline.

---

# 5. Why the pilot is kept

This pilot should not be deleted.

It preserves:

1. the earliest observed ChatGPT source-selection behavior around HumanoidOnline;
2. the source families competing for citation before HumanoidOnline had meaningful search visibility;
3. evidence that persistent personalization could affect answer wording;
4. the methodological reason the clean Temporary Chat protocol was adopted;
5. source-export evidence for broad commercial and Europe-availability queries.

This creates a transparent progression:

`personalized pilot → clean Temporary Chat baseline → future repeated clean measurements`

---

# 6. Evidence directory

Recommended repository structure:

```text
docs/
└── measurements/
    └── ai-visibility/
        ├── 2026-08-28_chatgpt_personalized_pilot_v0.1.md
        └── 2026-08-28_chatgpt_personalized_pilot_evidence/
            ├── COMMERCIAL-002.md
            ├── COMMERCIAL-003.md
            └── other historical evidence if recoverable
```

Only evidence that genuinely survives should be added.

Do not create placeholder screenshots that do not exist.

For observations where only the historical conversation record survives, keep that evidence state explicitly documented.

---

# 7. Relationship to clean baseline

The clean baseline is:

`docs/measurements/ai-visibility/2026-09-06_chatgpt_baseline_v0.1.md`

That file uses stricter rules:

- Temporary Chat
- fresh chat for every question
- no prior conversation context
- prompt does not mention HumanoidOnline
- fixed neutral source-disclosure suffix
- source-selection classification only

Pilot observations must never be silently promoted into clean observations.

---

# 8. Change-control rules

- Preserve historical pilot observations as originally classified.
- Do not rewrite pilot runs as clean Temporary Chat runs.
- Do not delete personalization/context limitations.
- Do not modify raw exported source evidence.
- Corrections should be added as explicit amendments.
- Pilot results do not alter catalogue facts, publication state, or governance contracts.
- This file is a measurement record, not a source of canonical robot facts.
