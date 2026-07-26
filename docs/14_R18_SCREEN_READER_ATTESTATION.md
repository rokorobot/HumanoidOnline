# WS8.4 / R18 — Screen-reader attestation checklist

> **STATUS: PREPARED — NOT ATTESTED.** This is the repeatable manual checklist
> for the R18 gate. It is **Attested** by frozen contract (WS8 §9.4, WS8-L8): a
> green automated axe run (R17) does **not** satisfy it. An automated tool is an
> oracle for *detectable* defects, not for accessibility itself — a screen
> reader driven by a person is the only way to confirm the experience is
> coherent.
>
> **This gate is PASS only when the record at the bottom is completed by a named
> operator with a date, against a specific commit.** No agent may self-attest it.

## How to run

Drive each flow with a real screen reader and keyboard only (no mouse). Suggested
pairings — at least one desktop and one mobile:

- **Desktop:** NVDA + Firefox/Chrome (Windows), or VoiceOver + Safari (macOS).
- **Mobile:** VoiceOver + Safari (iOS), or TalkBack + Chrome (Android).

Run against the production-like build (the verified WS2B catalogue), the same
surface the automated gates use.

## Checklist

For each item, record Pass / Fail / N-A and a note. A single Fail blocks R18.

### 1. Heading & landmark structure
- [ ] Each page exposes one `<h1>` and a sensible heading outline (no skipped levels that break navigation-by-heading).
- [ ] Landmarks are present and named: banner/nav (`Primary`), `main`, contentinfo/footer. Navigating by landmark reaches the main content directly.
- [ ] The "Skip to content" link is the first focus stop and moves focus to `#main-content`.

### 2. Accessible names
- [ ] Every link and button has a meaningful accessible name out of context (no bare "Compare +" ambiguity: the compare control announces "Add to compare" / "Remove from compare").
- [ ] The logo/home link announces "HumanoidOnline home".
- [ ] Icon-only controls (dialog close ✕) announce their purpose ("Close").

### 3. Forms — labels & instructions (Find-a-Humanoid wizard, Lead dialog)
- [ ] Every field has a programmatic label; required fields are announced as required.
- [ ] The country select and the wizard task select are operable and announce their current value.
- [ ] Instructions / help text are associated (`aria-describedby`) and read with the field.

### 4. Validation announcement
- [ ] Submitting the lead form with an empty/invalid email announces the error (the `role="alert"` message is spoken without moving focus away unexpectedly), and the field is announced invalid (`aria-invalid`).
- [ ] The error text is understandable read aloud (not just a symbol/color).

### 5. Focus progression
- [ ] Tab order follows visual/reading order on catalogue, detail, compare, wizard, matches.
- [ ] Opening the lead dialog moves focus into the dialog; focus is trapped inside while open (Tab/Shift-Tab cycle, do not escape to the page behind).
- [ ] Closing the dialog (Escape or Close) returns focus to the control that opened it.

### 6. Dialog / modal entry & exit
- [ ] The dialog is announced as a dialog with its title (`aria-labelledby`), and `aria-modal` hides the background from the screen reader.
- [ ] Escape closes the dialog; the success ("Request received") state is announced (`aria-live`).

### 7. Results / status announcement
- [ ] The match-results heading and each card's score/reasons/warnings are readable in a sensible order.
- [ ] The compare matrix is navigable: the scroll region is reachable and labelled ("Comparison matrix"); the spec table is labelled ("Specifications table").
- [ ] "Copied link" / "Saved view" status changes are perceivable.

### 8. Imagery & the IMAGE UNAVAILABLE state
- [ ] Verified robot images have meaningful alt text.
- [ ] A robot with no verified image announces the governed unavailable state ("No verified image available for {robot}") — never silence, never a decorative placeholder announced as an image.

### 9. Responsive / mobile screen reader
- [ ] On the mobile screen reader, the primary "Find a Humanoid" action is reachable and operable.
- [ ] The catalogue, a robot detail, and the wizard are navigable without horizontal panning traps.

## Known automated coverage (context, not a substitute)

R17 (`e2e/accessibility-axe.spec.ts`) runs axe WCAG 2.2 AA on the major surfaces
and interactive states (dialog open, validation error) on **both** desktop and
Pixel-7 projects, with **zero violations**. That covers detectable rule failures
only. The items above are the human-judgement layer axe cannot check
(announcement quality, focus coherence, reading order sense).

## Attestation record (complete to PASS R18)

```
Attested by:        (name / role — REQUIRED)
Date:               (REQUIRED)
Commit:             (the exact release head under test — REQUIRED)
Screen readers:     (e.g. NVDA+Firefox; VoiceOver+Safari iOS)
Result:             (PASS / FAIL)
Notes / exceptions: (any Fail or N-A, with detail)
```

> Until this record is filled by a person, R18 is **PENDING**, and the Release
> Invariant Matrix must show it as such. WS8.4 delivers the checklist and the
> automated R17 layer; it does not — and cannot — self-certify R18.
