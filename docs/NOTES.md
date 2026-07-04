Phase 0: Development environment ready (Git, WSL2, Docker, Ollama)

## M2-C2 — verifier network-isolation capability (CAP_SYS_ADMIN)

The verifier isolates the Phase-2 hidden-test step from the network with `unshare -n`
(M2_SPEC §10, D19 / Fallback B), granted via `cap_add: [SYS_ADMIN]` in
`docker-compose.yml`. The R3 feasibility prototype confirmed unprivileged `unshare -rn`
is blocked by the Docker Desktop / WSL2 seccomp profile, so the capability is mandatory.

Capability-gating is permanent and honest: isolation-dependent tests **run** where
CAP_SYS_ADMIN is present and **skip-with-reason** where it is not — never silently
passed. The verifier refuses to run untrusted code unisolated: if isolation is required
but the capability is absent, `verify` raises `SandboxExecutionError` (→ `INFRA_ERROR`).

Environment support — record for future contributors:

- Local Docker Desktop / WSL2: **SUPPORTED** (R3 prototype, Fallback B passed). At the M2
  freeze, `docker compose run --rm verifier pytest -q` ran with **zero skips**, so
  `test_phase2_blocks_network_egress` **executed and passed** under CAP_SYS_ADMIN — the
  Phase-2 no-egress control is verified locally.
- GitHub Actions CI: **CONFIRMED GREEN (RM-CI RESOLVED).** All five M2 workflow runs are
  green on `main` — CI #19 (`d75f641`, pinned env), #20 (`b800394`, two-phase isolation),
  #21 (`8a8d171`, flake detection), #22 (`baed002`, held-out secondary), #23 (`a315dea`,
  docs). The isolation-dependent test is permanently capability-gated (runs where
  CAP_SYS_ADMIN is granted, skip-with-reason otherwise — never silently passed, M2_SPEC
  §11); the local Docker Desktop run above is the authoritative CAP_SYS_ADMIN acceptance
  gate. M2 verification gates (M2_SPEC §3/§14) are satisfied.
