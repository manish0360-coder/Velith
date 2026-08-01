"""Unit tests for the M8 deterministic context assembly (M8-C4).

Scope: the assembly in isolation (M8_SPEC §3.3) — determinism, empty-memory bit-for-bit
identity across arms, the task portion depending only on the task, arms differing only in
the memory portion, and domain-neutrality (no parsing). The attempt (C5) and runner (C8)
are not under test here.
"""

from __future__ import annotations

from velith.episodes.episode import Episode, VerdictState
from velith.evaluation.context import assemble_context


def _episode(
    prompt: str, patch: str = "diff", state: VerdictState = VerdictState.PASSED
) -> Episode:
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch=patch,
        verdict_state=state,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def test_assembly_is_deterministic() -> None:
    """The same task and retrieved memory always yield the same prompt (§3.3)."""
    retrieved = (_episode("alpha"), _episode("beta"))
    first = assemble_context("solve X", retrieved)
    second = assemble_context("solve X", retrieved)
    assert first == second
    assert first.prompt == second.prompt


def test_empty_memory_is_bit_identical_across_arms() -> None:
    """A0 and empty A1/A2 assemble byte-for-byte identical prompts (§3.3)."""
    # Each arm's retrieval at an empty checkpoint yields no episodes.
    a0 = assemble_context("solve X", ())
    a1 = assemble_context("solve X", ())
    a2 = assemble_context("solve X", ())
    assert a0.prompt == a1.prompt == a2.prompt
    # And the empty memory contributes nothing: the prompt is the task portion alone.
    assert a0.memory_portion == ""
    assert a0.prompt == a0.task_portion


def test_task_portion_depends_only_on_the_task() -> None:
    """The task portion is a function of the task material alone, not the memory (§3.3)."""
    no_memory = assemble_context("solve X", ())
    with_memory = assemble_context("solve X", (_episode("alpha"),))
    assert no_memory.task_portion == with_memory.task_portion

    other_task = assemble_context("solve Y", ())
    assert other_task.task_portion != no_memory.task_portion


def test_arms_differ_only_in_the_memory_portion() -> None:
    """Over the same task, two memories change only the memory-context suffix (§3.3)."""
    task = "solve X"
    a1 = assemble_context(task, (_episode("alpha"), _episode("beta")))
    a2 = assemble_context(task, (_episode("alpha"),))

    # Task portion is byte-identical; only the memory portion differs.
    assert a1.task_portion == a2.task_portion
    assert a1.memory_portion != a2.memory_portion
    # The prompts share the identical task-portion prefix and differ only after it.
    assert a1.prompt.startswith(a1.task_portion)
    assert a2.prompt.startswith(a2.task_portion)
    assert a1.prompt.removeprefix(a1.task_portion) == a1.memory_portion
    assert a2.prompt.removeprefix(a2.task_portion) == a2.memory_portion


def test_assembly_is_domain_neutral() -> None:
    """A non-software task and memory assemble deterministically through the same path."""
    music_memory = (_episode("melody:C-E-G;bpm=120", patch="score:do-mi-sol"),)
    first = assemble_context("compose:cheerful;key=C", music_memory)
    second = assemble_context("compose:cheerful;key=C", music_memory)
    assert first.prompt == second.prompt
    # The opaque material is carried verbatim, never parsed.
    assert "compose:cheerful;key=C" in first.task_portion
    assert "melody:C-E-G;bpm=120" in first.memory_portion


def test_more_memory_extends_only_the_memory_portion() -> None:
    """Adding a retrieved episode changes the memory portion, never the task portion."""
    task = "solve X"
    one = assemble_context(task, (_episode("alpha"),))
    two = assemble_context(task, (_episode("alpha"), _episode("beta")))
    assert one.task_portion == two.task_portion
    assert "beta" in two.memory_portion
    assert "beta" not in one.memory_portion
