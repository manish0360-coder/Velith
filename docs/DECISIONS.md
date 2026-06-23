# DECISIONS

**Project:** Velith
**Document type:** Permanent engineering decision record. This is a *record*, not a discussion. Each entry states a decision that has already been ratified, its rationale, the alternatives that were rejected, and its consequences.
**Status of this document:** Authoritative. A ratified decision is changed only by a new dated entry that explicitly supersedes the prior one, with justification. Decisions are never edited away silently.
**Last updated:** 2026-06-20

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

## Amendment procedure

A ratified decision is changed only by appending a new dated entry that:
1. names the decision it supersedes,
2. states the implementation evidence or flaw that justifies the change, and
3. records the new decision in the same format.

Decisions are never edited in place or removed. This record is the project's memory of *why* it is shaped as it is, and that memory must remain intact for reviewers who join in year three.