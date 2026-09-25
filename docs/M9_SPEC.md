# M9_SPEC — Pre-registration freeze (sealed experiment design and analysis plan)

**Project:** Velith
**Milestone:** M9 — the experiment is **pre-registered**: before any comparative statistic is computed,
a single frozen, content-addressed record fixes the arms, the held-out split, the checkpoint schedule, and
the **analysis plan** (hypothesis, endpoint, statistic, and go/no-go rule) — sealed from the held-out
results — so the Stage-1 statistics and decision of M10 cannot be chosen after seeing the data.
**Document type:** Engineering contract — **architecture only**. Extracted from the ratified constitution
(`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no implementation, no
pseudocode, no code, no handoff, no commit plan, no tests, and no migration plan. Once frozen it is
immutable; the M9 implementation is *extracted from* it and never redesigns it.
**Status:** FROZEN (VM2 amendment) — M9 VM2 is frozen at the authorized repository governance commit that introduces Amendment VM2, tagged `m9-spec-frozen-oed7-vm2`; supersedes the prior freezes `m9-spec-frozen-oed7` (`c33cbb9`), `m9-spec-frozen-oed2` (`3d98a84`) and `m9-spec-frozen` (`36659cb`). Immutable; the M9 implementation is extracted from it and never redesigns it.
**Date:** 2026-07-06 (draft). **Freeze date:** 2026-09-17 (original). **Re-freeze date (OED-2):** 2026-09-18. **Re-freeze date (OED-7):** 2026-09-18. **VM2 amendment date:** 2026-09-26. **Re-freeze (VM2):** the authorized repository governance commit tagged `m9-spec-frozen-oed7-vm2`.
**Depends on:** `m8-complete` (frozen checkpointed held-out evaluation and its content-addressed
evaluation identity), atop the frozen M7 arms, M6 retrieval substrate, M5 batch runner and cold arm A0,
M4 corpus and held-out lock, M3 episode store/index, and M1/M2 loop and hardened verifier.
**Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9, D11, D12, D14, D15, D16.1, D16.7, D18, D21, D22,
D23. Future guidance D24/D25 is **not** implemented (D23).

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

> **M9 Amendment OED-2 (2026-09-18).** *Reason:* engineering identified a genuine incompatibility between
> M8's time-invariant A0 empty checkpoint and M9's K>1 longitudinal GEE — the original shared interaction
> model is unimplementable against a static baseline. *Scientific authority:* Scientific Review (final OED-2
> ruling), authorized by the Research Director. *Affected model (only):* the K>1 **A1 vs A0** comparison
> becomes the additive `verdict ~ checkpoint_id_c + arm`, with A0 time-invariant at `checkpoint_id_c = 0`
> (not replicated across checkpoints) and its gap-widens test carried by the `checkpoint_id_c` coefficient;
> the confirmatory family's second test changes from the A1/A0 interaction to the A1/A0 checkpoint trend.
> *Unchanged:* the A2 vs A1 interaction model, the K=1 McNemar path, the EMM definition and delta-method SE,
> robust sandwich covariance, the four-test Holm-Bonferroni family, α = 0.01, GO/NO-GO, checkpoint-identity
> binding, completeness, and model-failure handling — every other M9 provision remains exactly as frozen at
> `m9-spec-frozen` (`36659cb`).

> **M9 Amendment OED-7 (2026-09-18).** *Authorized by the Scientific Review Council.* Concerns only the
> `n=0` empty-dataset disposition: if complete-case exclusion (§3.5.1) leaves zero analysis tasks, the M10
> analysis halts with outcome **VOID** — a procedural halt, not an inferential NO-GO. Added as §3.5.11 below;
> all other M9 provisions, including the OED-2 amendment, remain unchanged. (Placement note: the ruling's
> "§7.5 / section 7 / §1.3" labels are Version-5 standalone numbering; in this frozen document the rule is
> §3.5.11 and the complete-case rule it references is §3.5.1 — authoritative wording preserved, labels
> adapted to this document's structure.)

> **M9 Amendment VM2 (2026-09-26).**
>
> *Reason:* the M8 evaluation identity is superseded by **M8 evaluation identity v2** (D29; `M8_IDENTITY_V2_SPEC.md`). That identity binds the verification contract into evaluation identity through `verification_manifest_hash`. Because the pre-registration is "bound to exactly the M8 evaluation identity components" (§6 item 1; §3.1), and because M10 reconstructs the evaluation identity from pre-registration fields, the pre-registration must carry the new component.
>
> *Authority:* Research Director ruling (M2-PV-R3, Q-A to Q-H); Scientific Review Council delta review, APPROVED.
>
> *Amended provisions (only):*
> - **(1) §3.1 — pre-registered experiment design.** The design components additionally include the **verification manifest hash**: `verification_manifest_hash`, the SHA-256 of the canonical mapping `task_identity → TaskSpec digest` over the **held-out evaluation population only**. It is distinct from, and not interchangeable with, the existing held-out split component `manifest_hash`, which keeps its name and meaning (the full-corpus partition manifest hash). "The components of the M8 evaluation identity (M8_SPEC §3.5)" is read as "the components of M8 evaluation identity v2 (`M8_IDENTITY_V2_SPEC.md` §4)".
> - **(2) §3.3 — content-addressed identity.** The declared components hashed into the pre-registration identity include `verification_manifest_hash`. The version component `spec_version` takes the value `"m9-spec-frozen-oed7-vm2"`. The canonical serialization is unchanged. Any change to the verification manifest yields a new pre-registration identity.
> - **(3) §6 item 1 — Definition of Done.** "Bound to exactly the M8 evaluation identity components" is read as bound to exactly the M8 evaluation identity **v2** components. A pre-registration with `spec_version = "m9-spec-frozen-oed7-vm2"` binds only to evaluations under `identity_version = "m8-evaluation-identity-v2"`.
>
> *Binding rules:*
> - The pre-registration does not store `identity_version`; a VM2 pre-registration is reconstructed only into identity-v2 provenance.
> - Mixed-version joins are rejected: a v1 (`m9-spec-frozen-oed7`) pre-registration with v2 evaluations; a VM2 pre-registration with v1 evaluations; and v2 with v2 under a different verification manifest.
> - The verification manifest is constructed under the fail-closed rules of `M8_IDENTITY_V2_SPEC.md` §3.3. An empty held-out population is **rejected** at construction (`VerificationManifestError`). This is distinct from, and does not alter, §3.5.11 (OED-7).
> - M8 identity v2, this amendment and the M10 reconstruction amendment are **one coordinated identity migration**.
> - M8 v1 (`docs/M8_SPEC.md`) remains the immutable historical specification; M8 identity v2 supersedes only its evaluation identity, by versioned supersession (D29).
>
> *Explicitly not changed by this amendment:*
> - **§3.5 in full**, i.e. the frozen M9 statistical procedure: outcome encoding (PASSED = 1, else 0), complete-case handling (§3.5.1), global-incomplete VOID, the hypothesis structure, GEE, EMM and delta-method SE, Wald inference, the trend test, robust sandwich covariance, McNemar (K = 1, §3.5.5), the Holm-Bonferroni family (§3.5.6), model-failure handling, α = 0.01, GO/NO-GO (§3.5.8), researcher degrees of freedom (§3.5.10), and OED-7 empty-dataset VOID (§3.5.11).
> - The OED-2 A0 time-invariance.
> - The arms; the checkpoint-schedule binding; the sealed-from-results invariant (§3.4).
> - This amendment changes identity and version plumbing, not statistical inference.
>
> *Classifier identity* (D27) is **not** a pre-registration component. *Available-task TaskSpec lineage* is **deferred** (an M2-PV provenance concern) and is **not solved** by this amendment. *Fixtures* use the universal v2 path, with deterministic synthetic 64-hex digest handles. *`AnalysisProvenance`* gains no plaintext `verification_manifest_hash`.
>
> *Existing artifacts:* no real M9 pre-registration exists in the repository (verified at `b14d918`). There is therefore no migration and no rehashing. Pre-registrations under `m9-spec-frozen-oed7` remain historical, and every pre-registration created after this amendment's freeze uses `m9-spec-frozen-oed7-vm2`.

---

## 1. Purpose

M8 produced **measurements**: per-task held-out outcomes for each arm, each bound to a content-addressed
evaluation identity, computing no statistic and reaching no decision. What M8 deliberately left open is
*which* statistic, over *which* endpoint, against *which* threshold, will decide the compounding
hypothesis in M10. If that choice were made **after** looking at the held-out results, the whole program
would be worthless: an analysis selected to fit the data can manufacture any conclusion (p-hacking,
HARKing, cherry-picked endpoints). M9 supplies the one thing that prevents this, and nothing more: a
**pre-registration** — a frozen, content-addressed record of the experiment design and analysis plan,
sealed from the results.

This is the anti-wireheading discipline (D21) raised from the *solution* to the *experiment* (D1/D6). Just
as the held-out secondary stops a model from gaming a single verdict, pre-registration stops the
*experimenter* from gaming the conclusion. To be worth anything, three things are non-negotiable. The plan
must be **fixed in advance** — the arms, the held-out split, the checkpoint schedule, the primary
endpoint, the statistic, and the go/no-go rule are all declared before M10 runs. It must be **sealed from
the results** — M9 reads the experiment *design*, never the held-out *outcomes* (a plan influenced by the
data it will judge is void). And it must be **immutable and content-addressed** — any change yields a
different, separately identified pre-registration, so a plan cannot be quietly altered after the fact
(D16.1/D18).

M9 is **composition, not a rewrite**. It adds no store, computes no statistic, reaches no decision, and
modifies no frozen M0–M8 contract. It is **domain-neutral** (D9/D22): the design and the endpoint are
expressed over the neutral verifier verdict, never over task content, and the record is opaque,
content-addressed data.

## 2. Scope — what M9 is

1. A **pre-registered experiment design** — the arms (A0, A1, A2), the held-out split (the M4 manifest
   hash), the **checkpoint schedule** — the ordered list of concrete, content-addressed M8 checkpoint
   identities to be evaluated (never a semantic label, name, ordinal position, or other mutable reference)
   — the base model, the evaluation seed, and the cost-guard limits: exactly the design M8's evaluation
   identity is built from, elevated to a declared, frozen plan.
2. A **pre-registered analysis plan** — the primary hypothesis (the ordered compounding comparison
   A2 ≻ A1 ≻ A0 on the held-out measure, the gap non-decreasing across the checkpoint schedule), the
   **primary endpoint** (the per task-checkpoint binary verifier outcome, `PASSED` = 1 else 0 — named and
   fully specified in §3.5.1, not computed), the **statistic/test** M10 will apply (for K > 1 a GEE with a
   four-test Holm-Bonferroni confirmatory family; for K = 1 the exact one-sided McNemar test; §3.5), and
   the **go/no-go decision rule and threshold** (§3.5.5-§3.5.8, family-wise α = 0.01) — all declared, none
   executed.
3. A **content-addressed pre-registration identity** — an immutable hash over the design and the analysis
   plan; the same plan yields the same identity, any change yields a new one.
4. The **sealed-from-results invariant** — M9 reads only the experiment design (checkpoint identities,
   manifest hash, arms, model, seed, limits, and the declared analysis choices) and **never** any held-out
   evaluation outcome or record; it computes no statistic and reaches no decision.

**Boundary of this milestone.** M9 **fixes the plan**; it does not **execute** it. It computes no
statistic, no aggregate, no effect size, and no go/no-go — those are M10 — and it evaluates nothing (that
was M8). It reads the M8 evaluation **identity/provenance** (the design), never the M8 evaluation
**records** (the outcomes): a pre-registration is the commitment made *before* the results are consulted.
The enforcement that M10 computes only the pre-registered analysis against the pre-registered design is an
M10 concern; M9 provides the immutable artifact M10 must bind to. **Research Director ruling (checkpoint
binding).** The pre-registered checkpoint schedule binds to the **concrete, content-addressed M8 checkpoint
identities**; semantic labels, names, ordinal positions, descriptions, and mutable checkpoint references
are insufficient. The ordered schedule of these identities is itself part of the content-addressed M9
pre-registration record (§3.1/§3.3), so any change to a checkpoint identity, to checkpoint membership, or to
checkpoint order yields a different M9 pre-registration identity. M10 must bind to exactly those
pre-registered checkpoint identities and must not resolve any semantic label to a checkpoint after M9 is
frozen.

## 3. Architecture

Four domain-neutral seams composing the frozen substrate. No new architecture is introduced beyond the
one instrument D12/D15 assigns to M9, and no frozen M0–M8 contract is reopened.

**3.1 The pre-registered experiment design.** The fixed inputs the analysis will be conducted over: the
**arms** (the closed set A0, A1, A2), the **held-out split** (the frozen M4 manifest hash), the
**checkpoint schedule** — the ordered list of concrete, **content-addressed M8 checkpoint identities** to
be evaluated (never a semantic label, name, ordinal position, or mutable reference) — the **base model**,
the **evaluation seed**, and the **cost-guard limits**. These are precisely the components of the M8
evaluation identity (M8_SPEC §3.5), recorded here as a declared design so that the pre-registration binds
the analysis to *exactly* the checkpoints, split, and arms M8 measures — and to nothing else. The ordered
schedule of checkpoint identities is part of the content-addressed pre-registration record (§3.3); M10
binds to exactly these identities and never resolves a semantic label to a checkpoint after the freeze. The
design is read from the experiment's identity, never from its outcomes (§3.4).

**3.2 The pre-registered analysis plan.** The declaration of how M10 will decide the hypothesis, fixed
before M10 runs:

- **Primary hypothesis** — the ordered compounding comparison: verification-filtered memory (A2)
  generalizes to held-out tasks better than unfiltered memory (A1), which beats no memory (A0), and the
  gap widens across the checkpoint schedule (D6/D7).
- **Primary endpoint** — the **per task-checkpoint binary verifier outcome**: for each arm on each
  held-out task at each pre-registered checkpoint, a `PASSED` verdict encodes `1` and every other frozen
  verdict (D16.7) encodes `0` (§3.5.1). This is the single, neutral, verifier-derived endpoint; no other
  endpoint is admitted. It is *named and fully specified* here, never computed; it is derived only from the
  deterministic verifier verdict (D3), never from a model score (D11) and never from task content (D9/D22).
- **Statistic / test** — for K > 1, a GEE (Binomial family, logit link, exchangeable working correlation,
  robust sandwich covariance) yielding, per adjacent-arm comparison, a response-scale EMM superiority test
  and a log-odds-ratio gap-widens test (the `checkpoint_id_c` coefficient for A1 vs A0; the
  `checkpoint_id_c × arm` interaction for A2 vs A1); for K = 1, the exact one-sided McNemar test. Fully
  specified in §3.5. M9 declares it, M10 applies it.
- **Go/no-go decision rule and threshold** — the pre-committed rule that maps the four confirmatory
  p-values (K > 1) or the two McNemar p-values (K = 1) to a binary program decision by Holm-Bonferroni at
  family-wise level α = 0.01 (D22), fully specified in §3.5.5-§3.5.8. The quantity it reads is the
  deterministic measurement, never a model score (D3).

M9 records these as a frozen plan; it **runs none of them**. This is the milestone that legitimately
*owns* the threshold and decision rule — declaring them in advance is the point of pre-registration — but
their **application** is deferred to M10 (M8_SPEC §5 forbade these settings precisely so they would be
fixed here, sealed from results).

**3.3 The pre-registration record and its content-addressed identity.** The design (§3.1) and the analysis
plan (§3.2) are fixed as a single **immutable pre-registration record** carrying a **content-addressed
identity** — a hash over exactly those declared components, computed by the same canonical serialization
the frozen episode and M8 evaluation identity use (sorted keys, tight separators, UTF-8, SHA-256), so the
identity is stable across processes and machines (D16.1/D18). The same plan always yields the same
identity; **any** change to **any** component (an arm, the split, a checkpoint identity, checkpoint
membership, checkpoint order, the endpoint, the statistic, the threshold) yields a **new** identity. The record is written **once** to a segregated
pre-registration location, distinct from the experience log and the evaluation sink, and is **never
mutated** thereafter — a pre-registration that could be edited after results are known is no
pre-registration at all.

**3.4 The sealed-from-results invariant.** The invariant M9 must never violate: the pre-registration is
built **only** from the experiment *design* — the M8 evaluation **identity/provenance** (checkpoint
identities, manifest hash, arm, base model, seed, cost-guard limits) and the declared analysis choices —
and **never** reads a held-out evaluation **record** or outcome. M9 does not import, open, or consult the
evaluation sink's measurements; it computes **no statistic** and reaches **no decision** (D22; M10). A
pre-registration produced with knowledge of the results is not a degradation but an **invalid
pre-registration**, and must fail loudly. This is the M9 analogue of M8's held-out lock: there, held-out
experience may never enter memory; here, held-out *results* may never enter the plan.

The four compose as: *pre-registered experiment design → pre-registered analysis plan → immutable
content-addressed pre-registration record → sealed from the held-out results (consumed by M10, never
before it is frozen)*.

**3.5 The pre-registered statistical analysis plan (the frozen M10 procedure, Version 5).** The exact,
immutable procedure M10 will execute on the frozen M8 held-out records. It supersedes all previous
statistical analysis plans. It is declared here in full and executed nowhere in M9; M10 applies it
mechanically, with no analyst discretion. M9 records only the plan and never reads a held-out outcome
(§3.4); the M8 records are consumed only at M10 time.

- **3.5.1 Data handling and unit of analysis.**
  - *Unit.* The fundamental unit of analysis is the **task-checkpoint observation** (one observation per
    task, per pre-registered checkpoint identity, per arm).
  - *Encoding.* For each such observation the frozen verifier verdict is encoded as binary: `PASSED` = 1,
    every other verdict in the frozen taxonomy (D16.7) = 0.
  - *Missing data (complete-case).* If any task in the held-out set is missing an evaluation record at any
    pre-registered checkpoint for any of the three arms (A0, A1, A2), that entire task (all `K x 3`
    observations) is excluded from all analyses (complete-case analysis). The final number of included
    tasks, `n`, is reported.
  - *Incomplete evaluation (hard stop).* If the M8 evaluation run did not complete for the full
    pre-registered held-out set, this pre-registration is void and the M10 analysis cannot be performed.
- **3.5.2 Hypothesis structure.** The analysis tests the ordered, compounding alternative
  `H_a: P(A2_pass) > P(A1_pass) > P(A0_pass)`, where the performance gap is non-decreasing across the
  ordered checkpoint schedule (§3.1). It decomposes into two component hypotheses, each combining a
  superiority claim and a non-decreasing-advantage (trend) claim:
  - `H_a1`: A1 is superior to A0, and the advantage is non-decreasing.
  - `H_a2`: A2 is superior to A1, and the advantage is non-decreasing.
- **3.5.3 Statistical model (K > 1).** A Generalized Estimating Equation (GEE) with the **Binomial**
  family, **logit** link, and **exchangeable** working correlation structure, with `task_id` as the group
  identifier. All standard errors use the **robust (sandwich) covariance estimator**; model-based standard
  errors are not used. **Model formulas (OED-2):** the **A1 vs A0** comparison uses the **additive** model
  `verdict ~ checkpoint_id_c + arm` (no interaction term); the **A2 vs A1** comparison uses
  `verdict ~ checkpoint_id_c + arm + checkpoint_id_c * arm`. Variable encoding: `arm` is treatment/dummy
  coded (for A1 vs A0: A0 = 0, A1 = 1; for A2 vs A1: A1 = 0, A2 = 1); `checkpoint_id_c` is the ordered
  checkpoint index `1, 2, ..., K` over the pre-registered content-addressed checkpoint schedule (§3.1),
  mean-centered before entering the model. **A0 is time-invariant:** A0 is evaluated once — its empty
  checkpoint identity is constant across the schedule (M8) — so exactly **one** A0 observation per task
  enters the model, **not replicated** across checkpoints, at **`checkpoint_id_c = 0`** (the mean of the
  centered index). One model is fitted per adjacent-arm comparison (A1 vs A0 additive; A2 vs A1 with
  interaction).
- **3.5.4 Estimands and tests (K > 1).** For each of the two models:
  - *Overall superiority (EMM).* The estimand is the difference in Estimated Marginal Means of passing
    probability on the **response scale**, averaged with **uniform weight 1/K** across all `K`
    pre-registered checkpoints:
    `EMM_diff = (1/K) * sum_{k=1..K} [ p_hat(arm=1, checkpoint=k) - p_hat(arm=0, checkpoint=k) ]`,
    where each `p_hat` is the inverse-logit of its fitted linear predictor. `EMM_diff` is a **nonlinear**
    function of the fitted GEE coefficients, so its standard error is computed **mechanically by the
    first-order delta method** (never left to software defaults):
    `SE(EMM_diff) = sqrt( g^T V_robust g )`, where `g` is the **gradient of `EMM_diff` with respect to the
    complete fitted coefficient vector** and `V_robust` is the robust sandwich covariance matrix from the
    same fitted GEE. The one-sided test is `Z = EMM_diff / SE(EMM_diff)`, `p = 1 - Phi(Z)`; the
    alternative is `EMM_diff > 0`.
  - *Gap-widens trend.* **A1 vs A0 (additive model):** because A0 is time-invariant, the trend estimand is
    `beta_checkpoint`, the coefficient of `checkpoint_id_c` — the per-unit-checkpoint change in A1's
    log-odds of passing while A0 stays constant. One-sided **Wald** test on the robust covariance:
    `Z = beta_checkpoint / SE(beta_checkpoint)`, `p = 1 - Phi(Z)`; the alternative is `beta_checkpoint > 0`.
    **A2 vs A1 (interaction model):** the trend estimand is `beta_interaction`, the coefficient of the
    `checkpoint_id_c * arm` interaction term — the difference in learning rate between A2 and A1. One-sided
    **Wald** test on the robust covariance: `Z = beta_interaction / SE(beta_interaction)`,
    `p = 1 - Phi(Z)`; the alternative is `beta_interaction >= 0`.
  - *Semantic lock (scale of "gap widens").* For M9, "gap widens" / "advantage is non-decreasing" is
    operationally defined **exclusively on the model's log-odds-ratio scale**: for A1 vs A0 it means
    `beta_checkpoint > 0` (the `checkpoint_id_c` coefficient); for A2 vs A1 it means `beta_interaction >= 0`
    (the `checkpoint_id_c × arm` coefficient). This does **not** assert that the raw probability difference
    is non-decreasing.
- **3.5.5 The K = 1 case.** If the pre-registered schedule contains exactly one checkpoint, GEE is **not**
  used. The analysis reverts exactly to the frozen Version-1 procedure: two **exact one-sided McNemar
  tests** on the adjacent paired arms — `H_a1: P(A1_pass) > P(A0_pass)` and
  `H_a2: P(A2_pass) > P(A1_pass)` — with the exact-binomial p-value already frozen (discordant counts `b`,
  `c`; conditional on `b + c`, `B ~ Binomial(b + c, 0.5)`; `p = P(B >= b)`; if `b + c = 0`, `p = 1.0`).
  Holm-Bonferroni is applied to these two McNemar p-values at FWER `α = 0.01`, and GO requires **both**
  McNemar tests to pass the two-test Holm procedure. The gap-widening hypothesis is **untestable when
  K = 1**: it is **not** treated as empirically tested and **not** automatically passed.
- **3.5.6 Multiplicity (K > 1).** The primary confirmatory family contains **four** p-values: (1) EMM
  A1 vs A0, (2) checkpoint trend A1 vs A0, (3) EMM A2 vs A1, (4) interaction A2 vs A1. The **Holm-Bonferroni**
  procedure controls the family-wise error rate at `α = 0.01`. Order the four p-values
  `p(1) <= p(2) <= p(3) <= p(4)` and reject sequentially, stopping at the first non-rejection: reject
  `H(1)` if `p(1) <= 0.01/4`; then `H(2)` if `p(2) <= 0.01/3`; then `H(3)` if `p(3) <= 0.01/2`; then
  `H(4)` if `p(4) <= 0.01/1 = 0.01`.
- **3.5.7 Model failures (K > 1).** If a GEE model fails to converge, produces a singular robust
  covariance matrix, or produces a non-finite required coefficient or standard error, the **two p-values
  associated with that model are defined as `1.0`**. This deterministically produces **NO-GO**.
- **3.5.8 Go/no-go decision (K > 1).** **GO iff all four** pre-registered hypothesis tests are
  statistically significant after the Holm-Bonferroni correction of §3.5.6. Every other outcome is
  **NO-GO**.
- **3.5.9 Domain neutrality.** The procedure depends only on the frozen verifier verdict encoded as
  `PASSED`/not-`PASSED` and is independent of task domain, content, or difficulty (D9/D22); a non-software
  design analyses through the identical path.
- **3.5.10 Researcher degrees of freedom — zero.** All of the following are fixed by this specification
  before M10 runs and cannot be selected, tuned, or altered after any result is observed: the
  task-checkpoint observation unit and `PASSED` = 1 / else = 0 encoding (§3.5.1); complete-case handling
  and the incomplete-run void (§3.5.1); the ordered compounding hypothesis and its two components
  (§3.5.2); the GEE with Binomial family, logit link, and exchangeable working correlation, the robust
  sandwich covariance, treatment coding, and the mean-centered checkpoint index (§3.5.3); the uniform 1/K
  response-scale EMM superiority estimand and its delta-method standard error, the trend estimands (the
  A1-vs-A0 `checkpoint_id_c` coefficient and the A2-vs-A1 `checkpoint_id_c × arm` interaction), and the
  one-sided Z / Wald tests (§3.5.4); the K = 1 exact one-sided McNemar procedure and its
  two-test Holm rule (§3.5.5); the four-test confirmatory Holm-Bonferroni family at `α = 0.01` (§3.5.6);
  the deterministic model-failure handling (`p = 1.0` -> NO-GO, §3.5.7); and the deterministic GO/NO-GO
  rule (§3.5.8). M10 is thereby a deterministic function from the frozen M8 records to a single GO or
  NO-GO verdict.
- **3.5.11 Empty dataset (OED-7).** If, after applying the complete-case exclusion rule (§3.5.1), the
  resulting analysis dataset contains `n=0` tasks, the statistical procedure cannot be computed. In this
  event, the M10 analysis will halt and the final outcome for the pre-registration will be recorded as
  **VOID**. This is a procedural halt, not an inferential NO-GO verdict.

## 4. Interfaces (composition contract — shape only)

Stated as responsibilities and composition, not signatures or code.

**Consumes (frozen, unchanged):**

- **M8** — the content-addressed **evaluation identity / provenance** (checkpoint identity, manifest hash,
  arm, base model, evaluation seed, cost-guard limits): the *design*, read-only. **The M8 evaluation
  records / outcomes are deliberately NOT consumed** — reading them would void the seal (§3.4).
- **M7 / M4** — the closed arm set and the frozen held-out manifest hash, as the design's arms and split.
- **The frozen verdict taxonomy (D16.7)** — the vocabulary in which the primary endpoint is *named*
  (never computed here).

**Provides (new, domain-neutral):**

- The **pre-registered experiment design** (§3.1) and **analysis plan** (§3.2).
- The **immutable, content-addressed pre-registration record and identity** (§3.3).
- The **sealed-from-results guarantee** (§3.4) — the artifact M10 binds to.

**Invariants.** The pre-registration is fixed before M10 runs, is content-addressed and immutable, and is
built only from the experiment design — never from the held-out results. It computes no statistic and
reaches no decision (D22). The endpoint is verifier-derived, never a model score (D3/D11), and neutral
(D9/D22). No held-out record is read; the evaluation sink, the experience log, and every frozen M0–M8
contract are untouched; A0 remains memoryless.

## 5. Configuration

Additive, validated settings only (M0 invariant: safe defaults, loads with no `.env`). No setting alters
any frozen behaviour.

- **Pre-registration record location** — where the single immutable pre-registration record is written;
  distinct from the experience log and the evaluation sink.
- **Declared statistic identifier** — the pre-specified statistical procedure M10 will apply: for K > 1 a
  GEE (Binomial family, logit link, exchangeable working correlation, robust sandwich covariance) with the
  four-test Holm-Bonferroni confirmatory family, and for K = 1 the exact one-sided McNemar test (§3.5). A
  fixed identifier validated against a closed set; M9 records it, M10 applies it.
- **Declared decision threshold** — the pre-committed family-wise go/no-go level `α = 0.01`
  (§3.5.5-§3.5.8); M9 records it, M10 applies it.

**Deliberately absent (and forbidden):** any setting that would **compute** a statistic or **apply** the
decision rule (that is M10); any setting that would route the pre-registration through the experience path
or read the evaluation records; and any change to the M8 evaluation settings, which remain the single
source of the design.

## 6. Definition of Done

M9 is complete when all of the following hold (verified in-container and in CI at Verification):

1. A **pre-registration record** fixes the experiment design — the arms (A0, A1, A2), the held-out split
   (manifest hash), the **checkpoint schedule as an ordered list of concrete content-addressed M8
   checkpoint identities** (no semantic labels), the base model, the evaluation seed, and the cost-guard
   limits — bound to exactly the M8 evaluation identity components.
2. The record fixes the **analysis plan** in full (§3.5) — the primary hypothesis, the primary
   **verifier-derived** binary endpoint (§3.5.1, named and fully specified, not computed), the K > 1 GEE
   with its response-scale EMM superiority test and log-odds-ratio gap-widens test (the `checkpoint_id_c`
   coefficient for A1 vs A0; the `checkpoint_id_c × arm` interaction for A2 vs A1) (§3.5.3-§3.5.4), the K = 1 exact one-sided McNemar procedure (§3.5.5), the four-test Holm-Bonferroni
   family at family-wise α = 0.01 (§3.5.6), and the deterministic model-failure handling and GO/NO-GO rule
   (§3.5.7-§3.5.8) — all declared, none executed.
3. The pre-registration carries a **content-addressed, immutable identity**: the same plan yields the same
   identity, and any change to any design or analysis component yields a new identity; the record is
   written once and never mutated.
4. The pre-registration is **sealed from the results**: it is built only from the experiment design and
   **never reads any held-out evaluation record or outcome**; a pre-registration reflecting observed
   results is refused loudly.
5. M9 **computes no statistic and reaches no decision** (D22; M10 out of scope); the endpoint is
   verifier-derived, never a model score or LLM-as-judge (D3/D11).
6. The pre-registration **binds to the M8 evaluation identities** — the checkpoints, split, and arms it
   registers — so M10 can only analyze the pre-registered design; it reaches the evaluation records
   through neither M9 nor its record.
7. **Domain-neutrality and determinism hold** — a non-software design/endpoint pre-registers through the
   identical path; no frozen M0–M8 file is modified, the only additions being the M9 pre-registration
   seams and additive configuration; all four gates (`ruff check`, `ruff format --check`, `mypy --strict`,
   `pytest`) are green in the container and CI, with zero M9-attributable skips (the seam is pure,
   in-process, deterministic recording — no model, no network); the milestone is tagged `m9-complete`.

## 7. Prototype Gate assessment (conditional pipeline stage)

M9 introduces **no unproven environmental mechanism.** Its seams are pure, in-process, deterministic
recording and content-addressing over declared design components and the already-proven M8 evaluation
identity — the same canonical hashing already established for the frozen episode (D16.1) and the M8
evaluation provenance. Nothing new depends on the environment, the filesystem, or a model.

**Assessment: the Prototype Gate is not required (no-op).** It fires only if Scientific Review judges some
M9 assertion a load-bearing unknown — the plausible candidate being whether the pre-registered analysis
plan is expressive enough to fully determine M10's computation without later interpretation, which is a
*scientific* ratification question (settled in review) rather than a feasibility one. Absent such a
finding, engineering proceeds directly from the frozen specification.

## 8. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M9 boundary:

- **Any statistic, aggregate, effect size, comparison, or go/no-go computation** — M9 *declares* the
  analysis plan; **Stage-1 statistics and the go/no-go decision are M10**, which applies the pre-registered
  rule to the M8 results.
- **Reading, aggregating, or computing over any held-out evaluation record or outcome** — the
  pre-registration is sealed from the results (§3.4); consuming the evaluation sink is forbidden.
- **Re-evaluating, re-running arms, or producing any new measurement** — evaluation is frozen at M8; M9
  adds none.
- **Any change to the M8 evaluation settings, the held-out lock, the guarded boundary, or the A0 runner.**
- **Any new arm** beyond A0/A1/A2 — the anti-grounding arm A3 and the ablation arm A4 (D7) remain
  deferred.
- **Any LLM-as-judge or model-derived endpoint** — the primary endpoint is verifier-derived alone
  (D3/D11).
- **Editing or re-issuing a frozen pre-registration in place** — a changed plan is a new, separately
  identified pre-registration (§3.3), never a mutation.
- **Multi-model routing, concrete real-dataset adapters, calibration (I6), the second vertical (D5 rung
  2), and everything in D15.**
- **Future principles D24/D25** — recorded guidance only, not implemented (D23).

---

## Freeze

On the Research Director's freeze this document becomes immutable. The M9 implementation handoff is
produced next, extracted from this specification, and the M9 engineering that follows manufactures only
what is written here. This specification stops at the M9 architectural boundary and does not speculate
beyond M9.
