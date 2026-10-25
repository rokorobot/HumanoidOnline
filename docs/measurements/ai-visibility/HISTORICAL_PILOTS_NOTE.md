# Historical ChatGPT pilot runs — committed under docs/29 decision D4

Committed 2026-10-24 under `docs/29` §11 decision D4. These records are
**historical pilot data, not part of the AI Visibility baseline**. They predate
the docs/29 protocol and are not comparable with its R1/R2 runs. All figures
are internal records; no metric from them may be published.

The original files are preserved unedited (see `README.md`). The review notes
below were added on commit and do not change them.

## Review findings (2026-10-24)

1. **`2026-09-06_chatgpt_baseline` observation date.** Every captured answer
   begins "As of 28 August 2026". The screenshots therefore appear to have been
   captured on 2026-08-28, not 2026-09-06 as the record states. Treat the run
   date as **uncertain (2026-08-28 or 2026-09-06)**.
2. **CAPABILITY-001 was not a fresh session.** Its answer begins "I'll use the
   Europe-purchasable robots from the previous list" and "Among the humanoid
   robots we discussed as purchasable in Europe", so it was asked in the same
   Temporary Chat as COMMERCIAL-003. The record's "Fresh chat for this question:
   YES" is contradicted by the evidence. Its query was effectively
   context-steered to Europe.
3. **Prompt suffix.** Both observations appended "Please cite the sources
   supporting your answer." to the frozen query text (`docs/29` §2, D3).
4. **Withheld file.** `2026-08-28_chatgpt_personalized_pilot_evidence/COMMERCIAL-002.md`
   (an exported ChatGPT source record, 138 KB) is **not committed** because it
   contains the owner's personal ChatGPT memory entries and this repository is
   public. It remains in the owner's local checkout. The pilot summary still
   refers to it.

## Evidence checksums (SHA-256)

```
94e5eec66c4b8dd293c48b598c14e8569be5eb291a4cf603b9f844ff2b104324 *./2026-08-28_chatgpt_personalized_pilot_evidence/2026-08-28_chatgpt_personalized_pilot_v0.1.md
1752a28632c3d451895ccc4dabab738b27ff426f98807a96947b1ccf1e3ccd9b *./2026-08-28_chatgpt_personalized_pilot_evidence/CAPABILITY-001-PILOT.md
6414d630e03d1e295472bb73e97ea212a3ec649608435d6fa7fea443ebdd7a8a *./2026-08-28_chatgpt_personalized_pilot_evidence/COMMERCIAL-001.md
fe5505d6d43ada43fea59c8872880b23c2a1520aac823979beee88911a237ff6 *./2026-08-28_chatgpt_personalized_pilot_evidence/COMMERCIAL-003.md
7495f71ed37d6ab87ba9f0d3d78497b09b831e3d59c3f2311c7439b80e3f9d21 *./2026-08-28_chatgpt_personalized_pilot_evidence/ENTITY-001.md
92619944d1a863ac010013fef45c706ae2e85668c20d3c2dd4adcfc10a38ad31 *./2026-08-28_chatgpt_personalized_pilot_evidence/ENTITY-002.md
979e6a313e36b1706830dbb65d0cec8c07d901ee7c04487930e1bf7edca7bf47 *./2026-08-28_chatgpt_personalized_pilot_evidence/ENTITY-003.md
8eaa80d30b97503393879061fe1ca144b076739696254042bc15f244b9cdf56b *./2026-09-06_chatgpt_baseline_evidence/2026-09-06_chatgpt_baseline_v0.1.md
5f98d36cad7333782f2494389b6ef73d41a0df8bf6342de0698424bb388459a5 *./2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001.md
5c8dbc3cb7e05d285dd7b992c05aced982c74c7c418c51f6de311e1c3346a59e *./2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_01.png
3f31453f47c264505299f75d3fa13e0db2c4ba3dbdf3bb144bb961bb4dbfe2a5 *./2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_02.png
9fadc4c100483978d57a4e4c06f1111fcb6442c46b877db5d49d85883cc4146b *./2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_03.png
4147bd3ec34a68e39291f1e394fb78fc805f8599d39e60cbd8e6ac5e34e84b06 *./2026-09-06_chatgpt_baseline_evidence/CAPABILITY-001_04.png
3e03acdce153742a4b3fd143e9037ab5acbac4769dcf462d7f4222fd49b67dc1 *./2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003.md
fc3ec6b419589e63af1a576c5c24ad4a8ac9e67fdad0b90f8c74161f2dc467b2 *./2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_01.png
f74a6c0d39c507238357143f233248b7f90f11a9c59a13237c29f08a40341086 *./2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_02.png
116f301d6cb80762c8109833c5ef7ae3cda4c8c6080b3b3bcac6633b7ed1cbdf *./2026-09-06_chatgpt_baseline_evidence/COMMERCIAL-003_03.png
```
