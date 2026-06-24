"""Velith LLM access: the thin model-call seam (M1).

This subpackage holds :class:`~velith.llm.client.OllamaClient`, a thin adapter over
a local Ollama server — the single place a model call is made. It is the M5 routing
seam at its first genuine use and is kept deliberately thin in M1: no routing, no
model-selection policy, no cost guard (D16.4).
"""
