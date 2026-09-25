# DECISIONS

**Project:** Velith
**Document type:** Permanent engineering decision record. This is a *record*, not a discussion. Each entry states a decision that has already been ratified, its rationale, the alternatives that were rejected, and its consequences.
**Status of this document:** Authoritative. A ratified decision is changed only by a new dated entry that explicitly supersedes the prior one, with justification. Decisions are never edited away silently.
**Last updated:** 2026-09-26

**Naming lineage (for the record):** This program was discussed during its review phase under the working names *PrometheusLite* / *Mini Prometheus* (program) and *Noetica* (system). The ratified flagship name is **Velith**. Where earlier internal documents (`VISION.md`, the architecture/cognitive/theory papers) use the older names, they refer to this same project unless explicitly stated otherwise.

---

## How to read this record

Each decision carries:
- **ID & title**
- **Status** (Accepted / Superseded / Postponed)
- **Decision** — what was decided, stated flatly
- **Rationale** — why
- **Alternatives rejected** — what was considered and not chosen
- **Consequences** — what this commits or forecloses

The narrative sections requested (vision, vertical, philosophy, migration, non-goals, postponements) are expressed *through* these decisions, not separately, so there is one source of truth and no drift between a summary and the record.

---

## Decision index

| ID | Title | Status |
|---|---|---|
| D1 | Project vision and research mission | Accepted |
| D2 | Verification-first philosophy | Accepted |
| D3 | Deterministic verification is mandatory at V0.1 | Accepted |
| D4 | First engineering vertical: repository-level software (SWE) | Accepted |
| D5 | Migration ladder toward manufacturing intelligence | Accepted |
| D6 | The core falsifiable experiment (the compounding hypothesis) | Accepted |
| D7 | Differential experiment design (grounding isolated as the causal variable) | Accepted |
| D8 | Methodological conditions for the experiment | Accepted |
| D9 | State-centric architecture; LLMs are components, not the architecture | Accepted |
| D10 | Free-energy theoretical framework is a research hypothesis, not a build constraint | Accepted |
| D11 | MiniNoetica is a separate, completed reference project — not a dependency | Accepted |
| D12 | M0–M10 implementation roadmap ratified; implementation has priority | Accepted |
| D13 | Engineering environment baseline | Accepted |
| D14 | Non-goals (explicitly out of scope) | Accepted |
| D15 | Decisions intentionally postponed | Postponed (by design) |
| D16 | M1 ratification clarifications (Q1–Q7) | Accepted |
| D17 | Verdict taxonomy unchanged; flakiness is metadata (M2) | Accepted |
| D18 | Determinism Levels; M2 targets Level 4 (M2) | Accepted |
| D19 | Two-phase hardened sandbox; isolation mechanism (M2) | Accepted |
| D20 | M2 explicit out-of-scope set (M2) | Accepted |
| D21 | `flaky` is provenance, not identity (M2) | Accepted |
| D22 | Binary decisions control workflow; quantitative measurements drive learning (P4) | Accepted |
| D23 | M4 architecture frozen as written; Scientific-Review enhancements deferred (M4) | Accepted |
| D24 | Future Principle A — engineering-task decomposition (InitialState/Context/Objective) | Accepted (future guidance — deferred) |
| D25 | Future Principle B — held-out evolves toward distance-based exclusion | Accepted (future guidance — deferred) |
| D26 | Real-task verification execution boundary; scoped supersession of D19 (M2-PV-R) | Accepted |
| D27 | Real-task verdict source-of-truth; clarifies M0 §6 and D13 (M2-PV-R) | Accepted |
| D28 | TaskSpec digest transport — Option D (M2-PV-R) | Accepted |
| D29 | M8 evaluation identity v2 (supersedes M8 v1 evaluation identity; resolves CX-A1) | Accepted |

---

## D1 — Project vision and research mission

**Status:** Accepted.

**Decision.** Velith's long-term objective is to build AI systems that **learn, reason, verify, remember, improve, and make decisions in grounded environments**. Its flagship instantiation is a **grounded, verification-first engineering intelligence** whose decade-scale north star is **manufacturing intelligence** — turning product intent into verified, manufacturable designs. The near-term substrate is a *General Engineering Intelligence* loop, not the manufacturing endpoint itself.

**Rationale.** The mission is one process: minimize the description length of *grounded* engineering experience over a hierarchical model, under a finite budget, against an immutable verifier, by composing typed transformations over one shared state. Manufacturing is named as the hardest, latest milestone precisely because its verification economics are the worst; a system that reaches it has demonstrably solved the loop rather than avoided it.

**Alternatives rejected.** Framing Velith as a chatbot, an agent framework, a CAD generator, or an LLM wrapper. All were rejected as identity-defeating (see D14).

**Consequences.** Every decision below is judged against whether it increases the probability of a grounded, compounding engineering intelligence — not against short-term capability or demo value. Full vision text lives in `VISION.md`; this record governs the decisions that implement it.

---

## D2 — Verification-first philosophy

**Status:** Accepted.

**Decision.** Truth in Velith is **exogenous and grounded**. No claim is trusted because a model produced it fluently; a claim is true only when an external verifier admits it. Verification is the load-bearing principle of the system, not a feature bolted on.

**Rationale.** A confidently wrong answer is the primary failure mode of generative systems. Grounding is also what makes the program *falsifiable* (the model can be wrong against external evidence) and what prevents the system from "improving" by corrupting its own success criterion. The verifier, and the human-oversight boundary, are fixed points outside the domain of any self-modification.

**Alternatives rejected.** Treating LLM self-assessment or verbalized confidence as a proxy for correctness; treating verification as a single trusted oracle that is always cheap and always right.

**Consequences.** Calibration, learning, and self-improvement are all defined *relative to* the verifier. The experiment (D6) is specifically designed to test whether external verification — not self-confidence — is what produces competence.

---

## D3 — Deterministic verification is mandatory at V0.1

**Status:** Accepted.

**Decision.** The V0.1 verifier must be **deterministic and have zero model-gap**: a result is computed by `compile + run hidden tests + static analysis`, with no model in the loop judging correctness. The verdict must be bit-for-bit reproducible given identical inputs, seed, and environment.

**Rationale.** The experiment that justifies the entire program (D6) measures whether *grounded* experience compounds. That measurement is only interpretable if the grounding signal is exact. Any model-based judgment in the verifier reintroduces the very model-gap the program exists to eliminate, and would make a failure-to-compound uninterpretable (architecture flaw, or just verifier noise?). In software, the verifier and the ground truth are the *same object* — a passing hidden test suite *is* correctness for the specified behavior, not a model of it.

**Alternatives rejected.** LLM-as-judge verification (this is the explicit anti-pattern; see D11). Approximate/model-based verification (FEA, SPICE) as the V0.1 ground truth — deferred to later rungs of the migration ladder where the model-gap is introduced *deliberately and after* the loop is proven (D5).

**Consequences.** Model-based judgment is permitted in the experiment **only** as the dedicated anti-grounding control arm (A3), whose entire purpose is to be beaten by deterministic verification. It is never the verifier itself.

---

## D4 — First engineering vertical: repository-level software (SWE)

**Status:** Accepted.

**Decision.** The first vertical is **repository-level software engineering**, evaluated against SWE-bench-Verified-style task sets with hidden, held-out test suites. Algorithmic problem sets (contamination-controlled, post-cutoff) are used **only as a warm-up harness**, never as the ratifying benchmark.

**Rationale.** Software uniquely satisfies the four properties the V0.1 experiment requires simultaneously: (1) zero model-gap grounding (D3); (2) an external, un-authored, held-out benchmark, defeating Goodhart; (3) high episode throughput at low cost, needed to observe a trend; (4) unsaturated headroom at the repository level, so the loop's lift is visible above noise. No other candidate vertical satisfies all four at V0.1.

**Alternatives rejected.**
- *Algorithmic-only (HumanEval/MBPP):* saturated → no headroom → compounding cannot be observed. Demoted to warm-up.
- *Electronics/PCB:* strong long-term fit, but no public held-out benchmark (re-introduces self-authoring) and functional verification (SPICE) is model-approximate. Designated the **natural second** vertical (D5), not the first.
- *HDL/firmware:* rigorous (formal/exhaustive) verification but immature benchmarks; deferred.
- *Mechanical/FEA and full manufacturing:* slow, brittle, and — fatally — the ground truth is itself approximate and partial. This is the *destination*, not the starting line. Using it first would confound the compounding signal with verifier intractability.

**Consequences.** V0.1 tests **loop mechanics, not domain knowledge**. Low *immediate* manufacturing transfer is accepted in exchange for maximum experimental cleanliness; transfer is recovered structurally via D5.

---

## D5 — Migration ladder toward manufacturing intelligence

**Status:** Accepted.

**Decision.** Generality is reached by a pre-committed migration ladder, so "software-first" can never quietly become "software-only":

1. **Software (repo-level SWE)** — prove the loop compounds; zero model-gap; external benchmark.
2. **Electronics / PCB** — first *deliberate* model-gap (approximate SPICE ground truth) and a literally manufacturable artifact (Gerbers); first internally-authored benchmark under held-out discipline.
3. **HDL / firmware** — exhaustive formal verification plus first contact with physical/timing constraints.
4. **Mechanical / FEA → manufacturing** — the north star, attempted only after the loop has survived progressively widening model-gaps.

**Rationale.** This sequence traces the verification-first thesis from *zero model-gap* to *full physical approximation* — precisely the gradient a manufacturing intelligence must climb. Starting at the bottom of that gradient is the disciplined path to the goal, not an avoidance of it. The architecture (D9) is kept domain-agnostic so each new vertical is a registration, not a rewrite.

**Alternatives rejected.** Choosing a high-transfer-but-unmeasurable vertical first (couples the hypothesis test to domain difficulty and confounds the experiment).

**Consequences.** Transfer is structural, not abandoned. Each rung reuses the measurement discipline established in D6–D8.

---

## D6 — The core falsifiable experiment (the compounding hypothesis)

**Status:** Accepted.

**Decision.** The single question V0.1 exists to answer: *Can a grounded, verification-first engineering agent measurably improve its held-out performance through verified experience?*

- **H1:** for a fixed base model and fixed per-task budget, an agent retaining **verification-filtered** experience achieves strictly higher **held-out** pass-rate after N grounded episodes than (a) the same agent at episode 0, **and** (b) control agents accumulating experience *without* the verification filter; and held-out pass-rate increases monotonically in expectation with accumulated verified experience.
- **H0:** verification-filtered experience produces no greater held-out improvement than unfiltered experience or no experience; any apparent gain is attributable to retrieval of near-duplicates, base-model variance, or benchmark noise.

**Rationale.** Every later layer (causal models, self-improvement, the cognitive plane) is *premised on compounding being real*. This experiment tests that single load-bearing assumption at the smallest, cheapest scale, in the vertical where the verifier has zero model-gap so a negative result is unambiguous. A negative result is the highest-value output: it blocks years of building on unverified ground.

**Alternatives rejected.** An absolute before/after design with no ungrounded control — rejected because it can be passed by ordinary retrieval (RAG) and would prove nothing about grounding (see D7).

**Consequences.** A negative result does not kill the project; it falsifies *this retention design* and forces re-derivation before further architecture is built. Kill criteria are pre-committed in the protocol (`RESEARCH.md`/protocol, to be recorded when written), not negotiated after seeing results.

---

## D7 — Differential experiment design (grounding isolated as the causal variable)

**Status:** Accepted.

**Decision.** The experiment is **differential**, with the experience-retention policy as the single manipulated variable, across arms:
- **A0 — Cold:** no memory (baseline + variance).
- **A1 — Unfiltered memory:** all attempts retained regardless of correctness (the RAG/null control).
- **A2 — Verified memory (treatment):** only verification-passing solutions and *verified* failure signatures retained.
- **A3 — Anti-grounding (falsification arm):** retains solutions the model *believed* correct, without running the verifier (self-confidence control).
- **A4 — Verified-success-only (ablation):** isolates the contribution of grounded *failure* learning.

The decisive criterion is **A2 strictly beats A1**. A2≈A1 is the RAG verdict (grounding adds nothing over retrieval). A2≈A3 is the self-assessment verdict (external verification adds nothing over self-confidence) and would put the entire verification-first premise (D2) in question.

**Rationale.** "Does experience help" has a cheap, useless, true answer (retrieval). The real claim is that the *verification signal* converts experience into competence. Only a control that holds retrieval identical and varies *only the write-filter* isolates grounding as the cause. The A3 arm — built to disprove our own premise — is the design's strongest credibility signal.

**Alternatives rejected.** Omitting A1 (cannot attribute improvement to grounding); omitting A3 (cannot show external verification beats self-confidence).

**Consequences.** A1 and A2 must share the *identical* retriever, embedder, and top-k; the only legal difference is the write-filter. If their retrievers ever differ, the experiment is void. This invariant is enforced as a permanent test (roadmap M6/M7).

---

## D8 — Methodological conditions for the experiment

**Status:** Accepted.

**Decision.** The experiment runs under these conditions:
1. **Fixed, deliberately non-saturating base model** — a weaker/cheaper model with headroom, measuring the *delta* the loop contributes, not absolute score. A frontier model at ceiling would mask the effect.
2. **Pre-registration freeze** of N, seed count, minimum effect size, exact arm contrasts, and metrics, hash-tagged *before* the first real Stage-1 run.
3. **Mechanically-enforced held-out lock** — held-out tasks can never enter any arm's memory; enforced in code (hash-checked exclusion), not by discipline.
4. **Frozen, checkpointed held-out evaluation** — measurement is on the *frozen* agent with memory read-only, so memorization cannot counterfeit learning.
5. **Staged spending** — Stage 1 (A0 vs A2) is a cheap go/no-go; Stage 2 (add A1, A3) is the decisive run; ablation (A4) and second-model replication follow. A Stage-1 win is explicitly *necessary-but-not-sufficient* and may never be mis-sold as confirmation.
6. **Effect size reported, not just significance** — with few seeds, magnitude and seed-spread are the primary evidence; an underpowered or noisy positive is treated as uninterpretable, not as a weak win.

**Rationale.** These are the conditions that make the result credible to a serious reviewer and that prevent the experiment from confirming itself. They also install the *measurement method* every later rung of the migration ladder (D5) will reuse.

**Consequences.** The harness is built to run all arms from the start (staging is a scheduling/spend decision, not an architectural one). Pre-registration is written against a *running* harness, never an imagined one (gate at roadmap M9).

---

## D9 — State-centric architecture; LLMs are components, not the architecture

**Status:** Accepted.

**Decision.** Velith is **state-centric**, not control-flow-centric. A persistent, typed, provenance-tracked representation of the artifact is the substrate; generators, verifiers, planners, and learners are typed transformations over that shared state. **LLMs are one mechanism among several**, never the architecture itself. Cognition (when added) is a **control plane over shared state**, never a central homunculus.

**Rationale.** Intelligence does not emerge from orchestrating stateless text-passing calls; it requires persistent state, grounding, and a loop that compounds. The state-centric inversion is what turns "a script that calls an LLM" into an operating system whose identity does not depend on any single model or vendor.

**Alternatives rejected.** Agent-graph-as-architecture; LLM-as-mind; a central reasoning engine that everything serves.

**Consequences.** Provenance and observability are first-class, non-negotiable deliverables from the first commit. The full layered design (L1–L8) and cognitive plane (C0–C10) are conceptual maps; the *code* follows a minimal V0.1 decomposition (roadmap M0–M10), with deeper layers added only after D6 is validated.

---

## D10 — Free-energy theoretical framework is a research hypothesis, not a build constraint

**Status:** Accepted.

**Decision.** The active-inference / expected-free-energy framework (in the theoretical-foundations paper) is retained as a **decade-scale falsifiable research hypothesis and a conceptual filter**. It is **forbidden from constraining any V0.1 mechanism**. No V0.1 line of code depends on the variational machinery being correct.

**Rationale.** The framework is elegant and gives the program long-term coherence, but exact free-energy minimization over a hybrid symbolic-continuous hierarchy is intractable; what gets built are approximations that stand on their own as ordinary engineering mechanisms (MDL compression + Bayesian updating + a compute budget). Until a running spike exists, the formalism drives zero implementation decisions and must not be allowed to shape the codebase prematurely.

**Alternatives rejected.** Treating the free-energy objective as a build specification (would risk years fitting engineering into a possibly-wrong abstraction); discarding it entirely (loses long-term coherence and the decade-scale falsifiable claim).

**Consequences.** The framework lives in `VISION.md`/`RESEARCH.md` as theory. The compounding experiment (D6) *is* its small-scale falsifiable test. Both the coherence the theory provides and the unblocked building the program needs are preserved.

---

## D11 — MiniNoetica is a separate, completed reference project — not a dependency

**Status:** Accepted.

**Decision.** MiniNoetica remains a **completed learning project and read-only reference repository**. It is **not a dependency of Velith** and shares no import paths with it. Velith is a new repository, side by side with MiniNoetica on disk, with zero coupling.

**Rationale.** MiniNoetica is an *education / learning-intelligence* system (it models a *student's* knowledge — theory-of-mind, the highest-risk component Velith explicitly defers). Velith is an *engineering-intelligence* system that improves *its own* verified competence. Different domain, different subject, different architecture. Critically, MiniNoetica's `judge.py` is an **LLM-as-judge**, which is the precise anti-pattern Velith's deterministic verification (D3) exists to eliminate; carrying it in would silently reintroduce the model-gap.

The value MiniNoetica delivered was the **engineering experience and reusable implementation patterns** it produced, not its educational domain. It succeeded as a 20-day learning vehicle: the deliverable of a learning sprint is the engineer it produces, not the repo it leaves behind.

**Patterns harvested (copied and adapted, never imported):**
- The LLM-call *shape* (single owner for model calls) — extended in Velith with routing + a hard cost guard.
- The episode-to-JSONL *pattern* — seeds Velith's episode store; the schema changes (engineering provenance, not student fields), the technique transfers.
- Test discipline (mocked-model integration tests, contract-between-components thinking).
- Logging pattern.

**Left behind explicitly:** all `phase2_memory/*` (student-modeling), `judge.py` (LLM-as-judge anti-pattern), and `agent_zero/step1–9` (learning archive).

**Alternatives rejected.** Extending MiniNoetica into Velith, or wiring the repos together. Rejected as negative value: dragging education-domain memory semantics into an engineering verification experiment costs more than a clean rebuild, and the boundary would erode.

**Consequences.** If a Velith file ever imports from MiniNoetica, that is the signal the boundary has been crossed and must be reverted. Pattern reuse is done by reading the old file and retyping an adapted version, not by cross-repo imports.

---

## D12 — M0–M10 implementation roadmap ratified; implementation has priority

**Status:** Accepted.

**Decision.** The M0–M10 milestone roadmap is ratified **as written**. From this point, implementation has priority over further architectural discussion unless implementation itself reveals a flaw. The roadmap delivers, in order: a runnable skeleton (M0); **one reproducible propose→verify→log episode (M1)**; a deterministic hardened verifier (M2); a provenance-complete episode store (M3); dataset loader + mechanically-enforced held-out lock (M4); batch runner + cold baseline A0 (M5); shared retrieval substrate (M6); A1/A2 write-filter policies (M7); frozen checkpointed evaluation (M8); the Stage-1 orchestrator + full A0/A2 run (M9); and Stage-1 statistics + go/no-go report (M10).

**Rationale.** The program had accumulated four conceptual frameworks and zero code; the marginal framework had negative value. The discipline now is validation-driven engineering: every milestone produces a *running system*, no milestone exists solely to produce documentation, and the first milestone ends at a real, logged, reproducible episode.

**Alternatives rejected.** Producing a fifth conceptual framework; designing all 19 module interfaces up front (abstraction-too-early — only the 2–3 interfaces the V0.1 loop exercises are built; the rest are named placeholders).

**Consequences.** Stage 2 (A1/A3), ablations (A4), and replication are specified in the same format *only after* M10's go/no-go verdict is in hand — deferred, not pre-built, per D8's staged-spending discipline.

---

## D13 — Engineering environment baseline

**Status:** Accepted.

**Decision.** Velith is built on: **WSL2 + Ubuntu** (Linux build/runtime), **Docker** (containerized deterministic verifier), **Python** (3.12 target for the Velith repo), **Git**, and **Ollama** (local model serving). The deterministic verifier (D3, roadmap M2) runs inside a Linux container for bit-for-bit reproducibility.

**Rationale.** M2's entire premise is reproducible verdicts; Linux containers make that tractable in a way native Windows does not. WSL2 + Docker + Ubuntu are verified present, removing the environment as a blocker before M0.

**Alternatives rejected.** Native-Windows build (reproducibility of the verifier would be materially harder). Note: the MiniNoetica reference repo runs on Windows + Python 3.10; Velith does not inherit that environment.

**Consequences.** M0's setup steps target WSL2/Ubuntu + Docker; a fresh clone must go green in that environment with one documented command.

---

## D14 — Non-goals (explicitly out of scope)

**Status:** Accepted.

**Decision.** The following are out of scope for Velith's identity. Moving any of them in requires a new superseding entry in this record.

| Non-goal | Why |
|---|---|
| Training foundation models | Consume frontier/open-weight models; small task models (embeddings, rerankers, distilled experts) are in scope when justified |
| Building physics engines, CAD kernels, or solvers | Wrap, never rebuild |
| Multi-discipline breadth on day one | Generality is earned by deepening one vertical, via the D5 ladder |
| Chatbot / general-assistant framing | Velith is a reasoning-and-verification system that *uses* LLMs |
| A homunculus / central reasoning engine | Cognition is a control plane over shared state (D9) |
| Premature scale infrastructure (Kubernetes, microservices, multi-tenant, web-scale) | Single-machine discipline for years |
| Verification-as-free-oracle | Any design assuming cheap, perfect ground truth is rejected by D2/D3 |
| Fixed benchmark optimized as the goal | Invites Goodharting; held-out, generalization-tested measurement only (D8) |
| LLM-as-judge as the verifier | The deterministic-verification anti-pattern (D3, D11) |

**Consequences.** These boundaries are load-bearing. They are what keep Velith from collapsing into "another agent framework."

---

## D15 — Decisions intentionally postponed

**Status:** Postponed by design.

**Decision.** The following are deliberately **not** decided now. They are postponed until the experiment (D6) validates the compounding premise, because deciding them earlier would architect for capabilities the program has not yet earned the right to build.

- **Cognitive control plane (C0–C10)** — global workspace, executive, meta-cognition, etc. Named as conceptual map; not built in V0.1.
- **Causal / structural model (L3 causal)** — postponed until after compounding is validated.
- **Self-model and social/theory-of-mind model (C2)** — highest research risk; postponed.
- **Scientific-discovery loop (C5)** — postponed.
- **Self-improvement loops (C9)** — postponed; when built, the fixed-verifier and human-oversight boundary are immutable from day one.
- **Calibration mechanism (I6)** — calibration is a *measured property we will try to force*, with a concrete method to be specified before it is claimed; not asserted as a guaranteed invariant yet.
- **Second vertical (electronics, D5 rung 2)** — postponed until the software loop is proven.
- **Any agent-framework dependency for the core spine** — the V0.1 orchestration loop is plain, testable code; a framework is adopted only if a concrete need appears.
- **Free-energy computation in code** — postponed indefinitely; theory only (D10).
- **Stage 2 / ablation / replication milestone details** — specified only after M10's verdict (D12).

**Rationale.** Postponement is a positive engineering act here: it prevents building cathedrals on an unverified foundation. Each postponed item is gated on a specific validation result, so the program knows exactly what earns the right to decide it.

**Consequences.** This list is the explicit boundary between "decided" and "deferred." An attempt to build any postponed item before its gate is a deviation that must be recorded here with justification.

---

## D16 — M1 ratification clarifications (Q1–Q7)

**Status:** Accepted (clarifications). **Date:** 2026-06-22.
**Scope:** These entries clarify the application of existing decisions (D2, D3, D4, D6, D8, D9, D12, D13) to milestone M1. None supersedes or alters D1–D15; each is a clarification, not a redesign. Where a clarification touches the M0–M10 roadmap acceptance text ratified under D12, it refines wording without changing the ratified substance.

### D16.1 — M1 reproducibility is scoped to the verify→log path
The roadmap's M1 acceptance ("same seed + temperature 0 → same verdict") is clarified: M1's **blocking** reproducibility criterion is that, **given a recorded proposal (fixed patch), the verify→log path produces the same verdict and the same content hash**. Proposal-level model determinism (seed + temperature 0) is attempted and recorded but is **not** a blocking criterion, because local model generation cannot be honestly guaranteed bit-identical across runs/hardware. This *locates determinism in the verifier*, consistent with and strengthening D3. (Clarifies D12; does not alter D3.)

### D16.2 — M1 orchestration runs in-container; Ollama reached via host
The M1 spike orchestrator runs **inside the container** (Python 3.12 target, D13), network-enabled, reaching the host Ollama service via `host.docker.internal` (WSL2 + Docker Desktop). The **verdict is produced in-container** (D3/M0 invariant preserved). The host Python (3.10) is never an execution target. Transient network access during the M1 run is an accepted, documented condition; isolating the test-execution step from the network is a later hardening step, not an M1 concern. (Clarifies D13.)

### D16.3 — M1 uses a minimal representative fixture task, not real SWE-bench
M1 exercises the loop with a **minimal, self-contained fixture task** of the same shape as a SWE-bench task (small repo + hidden test). Real SWE-bench Verified integration is deferred to M4. The fixture is **not a benchmark** and must never be used as the ratifying measurement (D8 held-out discipline is unaffected). (Clarifies D4/D6; does not alter D8.)

### D16.4 — M1 introduces a thin LLM adapter, not routing
M1 adds a **thin `llm/client.py` adapter** (generate + call metadata) so the proposer depends on a model capability, not on a vendor (D9). Model routing, selection policy, and the cost guard remain out of scope until M5; the adapter must not grow into a routing framework in M1. (Implements D9.)

### D16.5 — D8's non-saturating base-model condition binds from M5, not M1
The non-saturating base-model methodological condition (D8) governs the **compounding experiment (M5+)**. M1 may use any small local code-capable Ollama model that can emit diff-shaped output; the model and version are recorded in every episode for provenance and swappability. (Clarifies the scope of D8.)

### D16.6 — M1 episode persistence
Episodes persist to host `./data/episodes/` via a bind mount, gitignored, as an append-only JSONL store. The indexed/queryable store is M3. (Implementation clarification; consistent with I2/observability.)

### D16.7 — M1 verdict taxonomy and the outcome/error distinction
M1 verdict states are: `PASSED`, `FAILED`, `PATCH_APPLY_FAILED`, `NO_PATCH` (all **logged grounded outcomes**, process exit 0) and `INFRA_ERROR` (the **only** error state, non-zero exit). A test failure is a valid grounded outcome and first-class learning data, never an error. No model judges any verdict (D3). `secondary_passed` is null in M1 (populated at M2) and is not a verdict state. (Operationalizes D2/D3.)

> **Provenance note (2026-06-25):** D16 above is restored **verbatim** from commit `b8d458e` ("docs: ratify M1 engineering clarifications (D16)"), which originally recorded it. It was inadvertently removed by commit `cc4a1b4` ("docs: finalize M1 implementation contracts") and was absent from the record until this restoration. No wording was changed.

---

## D17 — M2: verdict taxonomy unchanged; flakiness is metadata

**Status:** Accepted. **Date:** 2026-06-25. **(Ratifies M2 R1.)**

**Decision.** M2 introduces no new verdict state. The closed taxonomy remains `PASSED`, `FAILED`, `PATCH_APPLY_FAILED`, `NO_PATCH`, `INFRA_ERROR` (D16.7). Test flakiness is *measurement quality*, recorded as a boolean `flaky` on the `Verdict` and persisted as episode provenance — never a verdict state.

**Rationale.** A verdict names the grounded outcome; flakiness names the trustworthiness of the measurement. Conflating them would pollute a closed outcome taxonomy with a quality signal and burden every downstream consumer.

**Alternatives rejected.** A `FLAKY` verdict state (mixes outcome and measurement quality in one field).

**Consequences.** Downstream memory policies (M5+) may consume the `flaky` provenance to down-weight or exclude unstable episodes. See D21 for the hash treatment of `flaky`.

---

## D18 — M2: Determinism Levels; M2 targets Level 4

**Status:** Accepted. **Date:** 2026-06-25. **(Ratifies M2 R2.)**

**Decision.** Verifier reproducibility is graded: **L1** same verdict ⊂ **L2** same content hash ⊂ **L3** same verifier output ⊂ **L4** same execution environment. M2 targets **Level 4** via a pinned interpreter environment (`PYTHONHASHSEED`, `TZ`, `LC_ALL`), network-isolated test execution, and the pinned base image, so L1–L3 hold structurally.

**Rationale.** M1 reached L2 incidentally (via output normalization). Pinning the environment makes reproducibility structural — which the compounding experiment (D6) requires of its grounding signal (D2/D3), strengthening D3 and D16.1.

**Alternatives rejected.** Relying on post-hoc output normalization alone (incidental and fragile).

**Consequences.** The verifier injects a fixed environment and isolates the test step; cross-machine equality follows from the pinned image and is asserted same-machine in CI.

---

## D19 — M2: two-phase hardened sandbox; isolation mechanism

**Status:** Accepted. **Date:** 2026-06-25. **(Ratifies M2 R3.)**

**Decision.** The verifier executes tests in two phases — Phase 1 network **ON** (dependency preparation), Phase 2 network **OFF** (test execution). A feasibility prototype determined that unprivileged `unshare -rn` is blocked by the Docker Desktop/WSL2 default seccomp profile, while `cap_add: SYS_ADMIN` + `unshare -n` succeeds; the latter is the **supported mechanism**. Isolation is mandatory: if the mechanism is unavailable, the verifier raises (`SandboxExecutionError` → `INFRA_ERROR`) rather than running untrusted code unisolated. The spike remains single-container.

**Rationale.** Closes the accepted M1 network-exposure risk (R3 / D16.2): untrusted generated code must not reach the network. Two phases preserve the proposal step's required network while isolating the test step.

**Alternatives rejected.** Unprivileged `unshare -rn` (blocked by seccomp, proven by prototype); a `--network none` sidecar (reintroduces a second container and a Docker-socket dependency, contradicting the single-container model).

**Consequences.** `docker-compose.yml` grants `cap_add: [SYS_ADMIN]` to the disposable verifier container; CI runs the isolation tests where the capability is available and capability-skips them (with an explicit reason) otherwise — never silently passed.

---

## D20 — M2: explicit out-of-scope set

**Status:** Accepted. **Date:** 2026-06-25. **(Ratifies M2 R4.)**

**Decision.** Property-based testing, resource profiling, streaming generation, richer proposer prompts, and git-ref provenance are out of scope for M2.

**Rationale.** M2 is verifier hardening; these are unrelated enhancements that would expand scope and risk.

**Alternatives rejected.** Folding any of these into M2 (scope creep).

**Consequences.** The M2 held-out secondary suite is explicit example-based cases; the proposer and the episode provenance fields are otherwise unchanged.

---

## D21 — M2: `flaky` is provenance, not identity (excluded from the content hash)

**Status:** Accepted. **Date:** 2026-06-25. **(Ratifies M2 R5.)**

**Decision.** The `flaky` flag is persisted in the episode but **excluded from the canonical `content_hash`**. The content hash covers reproducible *identity* only; a field belongs inside it iff it is a reproducible function of `(task, patch, environment)`. `flaky` is the observed output of a non-deterministic sampling process and may differ across re-verifications of a fixed proposal, so it is *provenance*, recorded alongside the timing fields outside the hash. `secondary_passed`, by contrast, is deterministic and therefore *identity* (inside the hash).

**Rationale.** Including `flaky` in the hash would make the Determinism Level 2 / D16.1 "same hash on re-verification" criterion unsatisfiable for the very episodes `flaky` exists to flag. Reproducible identity and full-record integrity are distinct concerns served by distinct digests.

**Alternatives rejected.** `flaky` inside the content hash (breaks D16.1 reproducibility); `flaky` left unpersisted (loses provenance needed by M5+ memory policies). Full-record tamper-evidence, if ever required, is a separate record-level digest (an M3 storage concern), never the content hash.

**Consequences.** `episodes/episode.py` adds `flaky` to `HASH_EXCLUDED_FIELDS`; a test asserts a varying `flaky` leaves the content hash unchanged.

---

## D22 — Binary decisions control workflow; quantitative measurements drive learning (P4)

**Status:** Accepted. **Date:** 2026-07-06. **(Ratifies P4; binds the M3 episode-store design.)**

**Decision.** Two distinct kinds of signal flow through Velith and must never be conflated:

- **Binary (categorical) decisions control workflow.** The closed verdict taxonomy (D16.7) and the boolean identity/provenance signals (`secondary_passed`, `flaky`) gate what happens next — retain or reject a patch, admit or exclude an episode from memory, pass or fail a gate. Control flow is driven by categorical outcomes, not by magnitudes.
- **Quantitative measurements drive learning.** Scalar or vector magnitudes — held-out pass-rate deltas, effect sizes, and, on later rungs of the migration ladder (D5), approximate-verifier scores such as SPICE or FEA residuals — inform *how* memory and policy are weighted and *how* the compounding experiment (D6/D8) is evaluated. They tune learning; they do not, by themselves, gate the workflow.

**D3 guard (binding and permanent).** Any quantitative signal admitted as grounded evidence must be a **deterministic verifier output, never a model-produced score**. A number a model emits about its own work is not evidence; it is the model-gap the program exists to eliminate (D2/D3, D11).

**Rationale.** Overloading a closed outcome taxonomy with a magnitude, or letting a magnitude silently gate control flow, reintroduces exactly the confusion verification-first is built to avoid. Keeping the two channels separate keeps control flow crisp and auditable while leaving learning free to consume rich, graded, *grounded* signal. Concretely for storage: the episode store must be **outcome-representation-flexible** — it records the categorical verdict that governs control flow today, and must not foreclose a future deterministic quantitative measurement field that later milestones will use for learning. Fixing the store to a binary-only worldview now would force a schema-breaking migration later.

**Alternatives rejected.** A single scored verdict that collapses measurement into the categorical outcome (reintroduces the model-gap D3 forbids and burdens a closed taxonomy). Admitting any model-emitted number as evidence (violates D2/D3). Pre-building the quantitative field now (premature; expands scope before a milestone requires it — see Consequences).

**Consequences.** The M3 episode store (D12/D16.6) is kept outcome-representation-flexible: it indexes only neutral, domain-agnostic fields and makes no design choice that would foreclose a *future, additive, non-identity, deterministic* quantitative field. That field is **not built in M3** — it is added only when a milestone requires it. The D3 guard binds any such field permanently, on every rung of the ladder.

---

## D23 — M4 architecture frozen as written; Scientific-Review enhancements deferred

**Status:** Accepted. **Date:** 2026-07-06. **(Freezes `docs/M4_SPEC.md`.)**

**Decision.** `docs/M4_SPEC.md` is ratified and **frozen exactly as written**. M4 ships the minimal domain-neutral **task corpus loader** plus the **mechanically-enforced, identity-based held-out lock**, composed onto the frozen M3 store — and nothing more. The two enhancements raised in M4 Scientific Review are recorded below as **D24** and **D25**; they are valuable long-term guidance but are **not implemented in M4**, because doing so would introduce abstraction ahead of a demonstrated need, which D12 (implementation-first roadmap) and D15 (deliberate postponement) forbid.

**Rationale.** The freeze protects the no-premature-abstraction discipline at the exact moment it is under pressure: a reviewer's good idea is the most common source of scope creep. M4's job is to make the loop corpus-scale and generalization-honest with the smallest possible domain-neutral surface; both deferred principles are gated on a multi-domain need that does not exist at M4 (the first vertical is software alone, D4). Recording them now preserves the insight without paying its cost early.

**Alternatives rejected.** Folding the task decomposition (D24) or distance-based held-out (D25) into M4 — premature abstraction that a single (software) domain cannot validate, expanding M4 scope and risk. Re-opening the ratified M4 architecture — the specification passed Scientific Review and the Research Director ordered it frozen as written.

**Consequences.** The M4 implementation handoff is extracted from the frozen `M4_SPEC.md` unchanged. D24 and D25 remain **future guidance** until their triggering conditions occur, at which point each is promoted to a build constraint by a **new dated decision** (the amendment procedure), never by silently reinterpreting M4. D12 and D15 are preserved and reinforced. See [[D15]].

---

## D24 — Future Principle A: engineering-task decomposition (InitialState / Context / Objective)

**Status:** Accepted as **FUTURE GUIDANCE — deferred**. **Not a build constraint for M4 or any current milestone.** **Date:** 2026-07-06.

**Decision.** In the future, an engineering task's identity/material should decompose into three explicit parts — **InitialState**, **Context**, and **Objective**. This decomposition is introduced **only when multiple engineering domains** (software, electronics, CAD, manufacturing) actually require a shared task representation. It is expressly **not** an M4 build constraint: M4 treats a task's materials and its verification handle as **opaque** (D9, D22, M4_SPEC §3.2/§4), and the current single-domain context (D4) does not justify the structure.

**Rationale.** The tri-part decomposition is the natural **domain-neutral** shape a task takes once heterogeneous domains must share one representation — an initial artifact/state, the surrounding constraints, and the target to be verified. Introducing it before that need exists is premature abstraction (D12/D15): software alone cannot validate a structure whose whole purpose is cross-domain generality, and building it early risks fitting later domains to a possibly-wrong shape.

**Alternatives rejected.** Building the decomposition into M4's corpus/task representation now (premature; unvalidated by a single domain; expands scope). Discarding the idea (loses durable long-term guidance the record exists to keep).

**Consequences.** When a milestone first requires **≥ 2 engineering domains** to share task representation (a D5 rung beyond software), this principle is the ratified starting point and is promoted to a build constraint then, via a new dated decision. Until that trigger, the opaque-materials contract (D9/D22) stands and M4 remains as frozen. See [[D15]], [[D23]].

---

## D25 — Future Principle B: held-out evolves from identity exclusion toward distance-based exclusion

**Status:** Accepted as **FUTURE GUIDANCE — deferred**. **Not a build constraint for M4 or any current milestone.** **Date:** 2026-07-06.

**Decision.** In the future, held-out evaluation should evolve from **identity-based exclusion** toward **state-space or parameter-space distance** exclusion **where appropriate** — specifically for **continuous** engineering domains (CAD, FEA, robotics, manufacturing), where near-duplicates in a continuous space can defeat identity exclusion. The **current identity-based held-out lock is correct and sufficient for M4** (M4_SPEC §3.3): M4's corpus is discrete and content-addressed, so exact identity exclusion fully enforces the D8 anti-Goodhart guarantee.

**Rationale.** Identity exclusion is exact for discrete tasks; continuous domains admit near-duplicate leakage that only a distance metric detects. But a distance criterion requires a **domain-specific** state/parameter space that does not exist at M4 and cannot be validated on software — adding it now would be premature abstraction (D12/D15) **and** would inject the very domain-specific assumption M4's architecture forbids.

**Alternatives rejected.** Implementing distance-based exclusion in M4 (premature; no continuous domain present; violates M4 domain-neutrality). Weakening the identity lock now (unnecessary and unsafe — it would trade an exact guarantee for an unvalidated heuristic).

**Consequences.** When a continuous engineering domain enters the corpus (a D5 rung beyond software), the held-out lock is **extended** with a distance-based criterion via a new dated decision, preserving the exact identity-based path for discrete domains. The invariant both mechanisms must satisfy is D8's: held-out experience never leaks into any arm's memory. See [[D8]], [[D15]], [[D23]].

---

## D26 — Real-task verification execution boundary (scoped supersession of D19 for real repository tasks)

**Status:** Accepted. **Date:** 2026-09-25. **(Ratified by the Research Director at M2-PV-R.)** **Supersedes:** D19, **only** for the verification of real repository-level tasks. D19 remains authoritative and unchanged for the legacy synthetic-fixture verifier (`VerifierSandbox`: two-phase `unshare -n` under `CAP_SYS_ADMIN`, single container), including `M2_SPEC.md:232` ("Single-container — no orchestrator/compose split"), which D26 scopes identically.

**Evidence / flaw (amendment procedure, `DECISIONS.md:479`).**
- Real tasks require task-specific interpreters, native libraries and dependency sets that cannot co-reside in the single Velith image.
- The M2 feasibility prototype (`b14d918`, evidence manifest `30c59a45db9e06556bc0a0529b290d43c7a4163066b3b3a4c138f97eaa6255f7`) demonstrated, for one task and benign candidates only, sealed digest-pinned network-less execution in separate task containers driven by a host-side orchestrator.

**Decision.**
1. **Placement (AR-2):** trusted host verifier orchestrator → digest-pinned task container → candidate execution.
2. **Before execution:** the image digest (`image@sha256:…`) and the declared platform are verified. On mismatch the orchestrator raises.
3. **Fresh container per execution:** baseline, candidate, confirmation re-run and admission runs each use a new container from the pinned digest, removed unconditionally. No container is reused after candidate code executed in it.
4. **Mandatory constraints:**
   - `--network none`; `--cap-drop ALL`; `--security-opt no-new-privileges`;
   - bounded memory (swap disabled), CPU, PID count and wall time;
   - bounded disk and captured output where the runtime supports it.
5. **Prohibited:** `--privileged`; any Docker socket or container-runtime access from a task container; Docker-in-Docker; host filesystem (bind) mounts. Inputs are copied into a created, not-started container; outputs are copied out only after full teardown.
6. **No candidate access** to the trusted experience/episode store, evaluation sink, pre-registration, corpus, TaskSpec registry or evidence ledger. None of these exists inside any task container, nor in any namespace shared with one.
7. **No install, build or network activity** during verification. The published image is the complete environment. D19's two-phase intent is preserved by construction: the proposer's network is outside every task container.
8. **Fail closed:** if any required constraint cannot be applied and verified (runtime inspection of the created container), the orchestrator raises `SandboxExecutionError` and never executes candidate code under weaker isolation.
9. **Classification (SRC-mandated amendment):** the host orchestrator **shall execute verdict classification only through the hash-locked verifier classifier environment specified by D27.**
10. **Role of the host:** the host is the **process manager**. It is **not** the scientific source of candidate test-execution evidence; that evidence originates only inside task containers (D27 A).

**Trust boundary.**
- **Trusted:** the orchestrator and its D27 environment; the container runtime (stated assumption: root-equivalent host access); the TaskSpec registry; the evidence ledger; trusted runner artifacts; the task image as an environment after admission.
- **Untrusted:** the candidate patch, and everything in a candidate or rerun container from the first execution of candidate code.
- **Evidence:** untrusted-side evidence may lower a verdict. It may support `PASSED` only through the integrity checks the frozen M2-PV specification will define, and then only with the accepted E12/E13 residuals recorded in the M2-PV-R ratification record.

**Alternatives rejected:**
- AR-1, in-container execution: environment infeasibility, and co-location with the experience store.
- AR-3, socket-mounted sibling containers: root-equivalent host control reachable from a container.
- AR-4, Docker-in-Docker or privileged mode.

Rootless and hardened runtimes (AR-5/AR-6) are deferred options, not rejected.

**Consequences.**
- `docker-compose.yml` and `docker/verifier.Dockerfile` are unchanged.
- The legacy verifier is confined to synthetic fixtures.
- CI exercises real-task verification only where a runtime and the images are available; elsewhere it capability-skips with an explicit reason, never a silent pass.

**Not decided by D26:** runner mechanics; R_b, R_g, R_c; limit values; non-root, read-only-root and hardened runtime; protected-surface policy; TaskSpec schema (open questions of the M2-PV-R ratification record).

---

## D27 — Real-task verification: evidence, classification and orchestration (clarifies M0 §6 and D13's verifier sentence)

**Status:** Accepted. **Date:** 2026-09-25. **(Ratified by the Research Director at M2-PV-R.)** **Clarifies, for real-task verification under D26 only:**
- `M0_SPEC.md:120` ("…never as the source of truth for a verdict");
- `PROJECT_STATE.md:127`;
- `DECISIONS.md:263` (D13: "The deterministic verifier … runs inside a Linux container").

None is edited. All three remain authoritative for the Velith image, CI gates and the legacy fixture verifier.

**Decision.** A real-task verdict is produced by three strictly separated functions:
- **A. Task execution evidence.** Produced **only** inside the admitted, digest-pinned task container, plus the container runtime's inspection of it. This is the sole empirical input about candidate behavior.
- **B. Verdict classification.** Performed **only** by the trusted, hash-locked Velith verifier classifier: a deterministic mapping from trusted evidence + TaskSpec + frozen rules → `Verdict`.
- **C. Host orchestration.** A process-management function only: create, constrain, feed, tear down and collect. It contributes no evidence and no judgment.

**The classifier MUST:**
1. run from a clean git tree at a recorded commit;
2. run under the exact locked Python environment (D13 target 3.12; hash-locked dependencies);
3. verify its own environment identity before classifying;
4. refuse evaluation-of-record execution if required identity cannot be verified;
5. use only explicit, recorded inputs;
6. prohibit ambient host state (host packages, environment variables, user configuration, working directory, locale or time zone) from affecting classification;
7. record classifier identity (commit, lock hash, interpreter version) in the evidence of every verification;
8. deterministically map trusted evidence + TaskSpec + frozen rules to a `Verdict`.

**Source of truth.** The scientific source of truth is **A interpreted by B**. The host is **not** the scientific source of truth.

**Determinism.** **Cross-machine deterministic classification is a mandatory acceptance requirement to be demonstrated by the M2-PV validation matrix.** It is an acceptance requirement. It has **not** yet been demonstrated: M2 showed one-host reproducibility for one task only.

**Consequences.** Classifier identity becomes part of verification provenance. Whether it also enters evaluation identity remains open (M2-PV-R ratification record, OQ-9).

---

## D28 — TaskSpec digest transport (handle-carried, registry-resolved)

**Status:** Accepted. **Date:** 2026-09-25. **(Ratified by the Research Director at M2-PV-R, subject to D-1 to D-4.)**

**Decision.**
- Transport chain: `CorpusTask.handle` → content-addressed TaskSpec registry → TaskSpec digest → real-task adapter (registered behind the frozen M5 `TaskAdapter` seam) → `Task`.
- The digest is recomputed at the registry read, at the adapter and at the verifier. Any mismatch is fail-closed.
- Grounded in frozen semantics: "a *verification handle* owned by the verifier" (`M4_SPEC.md:34`); the adapter turns "a `CorpusTask`'s opaque handle into the concrete inputs the frozen proposer and verifier consume" (`M5_SPEC.md:56-57`); `repo_path` + `hidden_test_command` are the `Task`'s verification handle (`batch/adapter.py:8`).

**Mandatory conditions.**
- **D-1:** `Task.task_id` remains spec-independent and stable. Re-pinning a TaskSpec never changes `task_id`.
- **D-2:** `Task.prompt` is a pure function of `material`. TaskSpec test data, hidden tests, gold patches and protected-surface details must never enter `material` or `prompt`.
- **D-3:** a static wiring guard prevents real-task `Task` instances from reaching the legacy `VerifierSandbox`. Real-task `Task` instances use only the production container verifier/orchestrator.
- **D-4:** the `Task.repo_path` interpretation is formally documented as follows.

**Interpretation note — D-4, proposed wording for the future M2-PV specification:**
"For real-task verification, `Task.repo_path` is the path of the verified, content-addressed TaskSpec bundle, i.e. *the source bundle copied by the verifier* (`task.py:50`: 'the source the verifier copies — it never operates on this path in place'). It is not a git working copy. The legacy fixture interpretation is unchanged."

**Invariants:**
- Option D does **not** modify `CorpusTask.material`, does **not** alter task identity (`manifest.py:39-46`), and does **not** modify retrieval semantics.
- Retrieval inputs are exactly `CorpusTask.material` (`evaluation/attempt.py:125`) and `episode.prompt` (`retrieval/retriever.py:27`). Neither is touched.
- The TaskSpec used at evaluation **excludes the gold patch**, which exists only in admission evidence.

---

## D29 — M8 evaluation identity v2 (supersedes M8 v1 evaluation identity; resolves CX-A1)

**Status:** Accepted. **Date:** 2026-09-26. **Supersedes:** the M8 v1 evaluation identity (M8_SPEC §3.5; `EvaluationProvenance`), **for evaluations created after the v2 freeze only**. M8 v1 is not edited and remains the immutable historical specification. **Resolves:** CX-A1 (M8 declared immutable, yet the ratified VerificationManifest binding requires a changed evaluation identity). **Builds on:** D8, D18, D26, D27, D28.

**Evidence / flaw justifying the change (amendment procedure).**
- Evaluations conducted under different verification contracts (TaskSpecs: e.g. different image digests, required tests or protected-surface inputs) are different measurements.
- Under M8 v1 they receive the **same** evaluation identity: v1 identity covers the checkpoint, the corpus partition manifest, arm, base model, evaluation seed and cost guard, but no verification component (`src/velith/evaluation/provenance.py`).
- M8_SPEC declares itself immutable ("Once frozen it is immutable"). The change is therefore made by **versioned supersession**, not by editing M8 v1.
- M8 v1 status: `docs/M8_SPEC.md` as committed at `49d9f75` ("docs: add frozen M8 specification…"), certified at `m8-complete` (`fe2b3d7`). The file's "Status: DRAFT" header is a stale label contradicted by that governance record. The header is not edited by this decision (see Consequences).

**Decision.**

1. **VerificationManifest.**
   - Definition: the canonical mapping `task_identity → TaskSpec digest` over the **held-out evaluation population only** (the tasks of the `HeldOutEvaluationSet` under evaluation).
   - Hash: `verification_manifest_hash` = SHA-256 of its canonical serialization. This reuses the repository's existing canonical rule (`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, UTF-8, lowercase hex), with no new format.
   - Construction **rejects**, raising `VerificationManifestError` (for use by the M8 runner check): an empty population; any duplicate task identity (whether its digests are equal or differ); a missing TaskSpec; an invalid digest (not 64 lowercase hex); and TaskSpec content that does not re-hash to its digest.
2. **M8 evaluation identity v2.**
   - The hashed `EvaluationProvenance` payload gains exactly two keys:
     - `identity_version = "m8-evaluation-identity-v2"`;
     - `verification_manifest_hash`.
   - The eight v1 components are unchanged in name and meaning: `checkpoint_identity`, `manifest_hash`, `arm`, `base_model`, `eval_seed`, `max_tasks`, `max_attempts_per_task`, `max_tokens`.
   - The v2 payload therefore has exactly ten keys: `identity_version`, `checkpoint_identity`, `manifest_hash`, `arm`, `base_model`, `eval_seed`, `max_tasks`, `max_attempts_per_task`, `max_tokens`, `verification_manifest_hash`.
   - `manifest_hash` keeps its name and its meaning (the full-corpus partition manifest hash). It is distinct from `verification_manifest_hash`, and the two are not interchangeable.
3. **M9 binding.**
   - `PreRegistration` gains `verification_manifest_hash` and carries `spec_version = "m9-spec-frozen-oed7-vm2"`. This is the existing M9 version concept, bumped; no new global version system is introduced.
   - A pre-registration with that `spec_version` binds only to identity-v2 evaluations.
4. **Coordinated migration.** M8 identity v2, the M9 pre-registration amendment and the M10 reconstruction amendment form **one identity migration**: specified, frozen and implemented together. M10 rebuilds the evaluation identity from pre-registration fields at two sites (`analysis/binder.py`, `analysis/executor.py`); both must reconstruct identity v2.
5. **Mixed-version joins are rejected:**
   - v1 pre-registration with v2 code or records;
   - v2 pre-registration with v1 records;
   - v2 with v2 under a different VerificationManifest.
6. **Consistency check.** Before any attempt, the M8 runner requires:
   - `identity_version == "m8-evaluation-identity-v2"`;
   - `verification_manifest_hash` equal to the hash computed from the evaluated held-out set.

   Any mismatch, missing or changed TaskSpec, missing or extra task, or duplicate identity halts with no record written.
7. **Fixtures (universal v2).** There is one v2 identity path for all evaluations, including synthetic fixtures. Fixture corpora supply deterministic synthetic 64-hex digest handles (a test-data change only). No dual v1/v2 code path exists.
8. **Classifier identity** (D27: commit, lock hash, interpreter) enters **neither** `PreRegistration.identity` nor `EvaluationProvenance.identity`. It is recorded in verification evidence. One evaluation of record (every arm and checkpoint under one pre-registration) runs under one classifier identity, enforced through the evidence ledger.
9. **Available-task TaskSpec lineage** is **deferred** as an M2-PV provenance concern and is **not solved** by this decision. The VerificationManifest binds held-out TaskSpecs only. Available-task verification affects evaluation only through memory content, which `checkpoint_identity` binds. A TaskSpec change that leaves every memory episode byte-identical is not reflected in any identity.
10. **No statistical change.**
    - M9 statistical formulas and decision rules are unchanged: outcome encoding (PASSED = 1, else 0), complete-case handling, global-incomplete VOID, OED-7 empty-dataset VOID, GEE, EMM, Wald inference, McNemar (K = 1), Holm correction, α = 0.01, the decision rule, and A0 time-invariance (OED-2).
    - This decision changes identity and version plumbing, not statistical inference.

**Rationale.**
- Binding the verification contract into evaluation identity ensures that differently verified evaluations cannot share an identity and so cannot be joined or pooled. This holds except with negligible probability under the standard SHA-256 collision-resistance assumption.
- Versioned supersession honors M8's immutability.
- Held-out-only scope matches exactly the population M8 evaluates, without widening M8's read surface into the available partition.
- Excluding classifier identity keeps pre-registration sealable before execution.

**Alternatives rejected:**
- A procedural-only verification manifest outside identity (rejected by RD and SRC at M2-PV-R).
- In-place editing of M8 v1 (violates M8 immutability).
- The full-corpus population (widens M8 into the available partition; conservative but unnecessary for held-out identity).
- Actually-evaluated tasks as the population (not pre-registrable).
- Dual v1/v2 code support, or fixtures kept on v1 (a permanent second path, or tests exercising an identity no longer used).
- Classifier identity inside evaluation identity (breaks pre-run sealing).
- A plaintext `verification_manifest_hash` in `AnalysisProvenance` (redundant: covered by the pre-registration and evaluation identities).

**Consequences.**
- **M8 v1** (`docs/M8_SPEC.md`, code at `b14d918` / `m8-complete`) remains historically reproducible. Its identities are never edited, rehashed or converted.
- **No migration.** No real M8 evaluation, M9 pre-registration or M10 analysis artifact exists in the repository (verified at `b14d918`), so there is no migration procedure, no rehashing and no v1→v2 conversion. Every evaluation of record created after the v2 freeze uses identity v2.
- **`EvaluationRecord` is unchanged:** `evaluation_identity` carries the binding by hash inclusion.
- **`AnalysisProvenance` is unchanged:** no plaintext `verification_manifest_hash`.
- **Checkpoint identity and the corpus manifest are unchanged.**
- **The stale "DRAFT" header** of `docs/M8_SPEC.md` is **not** corrected by this decision. It may be corrected only by a separate, explicitly authorized documentation task.
- **Successor texts:** the M8 identity v2 specification (`docs/M8_IDENTITY_V2_SPEC.md`) and the M9 Amendment VM2 block in `docs/M9_SPEC.md` (`m9-spec-frozen-oed7-vm2`) are the normative texts of this decision. Proposed freeze tags: `m8-identity-v2-frozen`, `m9-spec-frozen-oed7-vm2` (created only at the separately authorized repository gate).
- **Acceptance cases.** The 18 identity cases of the successor specification are **specification-level** cases. They become implementation acceptance tests. None has been implementation-validated.
- **Implementation** requires its own handoff and authorization. This decision authorizes none.

---

## Amendment procedure

A ratified decision is changed only by appending a new dated entry that:
1. names the decision it supersedes,
2. states the implementation evidence or flaw that justifies the change, and
3. records the new decision in the same format.

Decisions are never edited in place or removed. This record is the project's memory of *why* it is shaped as it is, and that memory must remain intact for reviewers who join in year three.