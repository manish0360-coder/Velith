"""The write-filter / arm layer (M7).

Holds the experiment's **single manipulated variable**: the *experience-retention
policy* deciding which grounded experience is retained in an arm's memory
(M7_SPEC §1). The arms differ **only** by their write-filter; every arm retrieves
through the identical frozen M6 substrate, and if their retrievers ever differ the
experiment is void (D7).

M7 defines *what each arm's memory is*. It does not execute the arms and does not
condition proposals on retrieved memory (M7_SPEC §2). The layer is domain-neutral
(D9/D22): admission is decided from the episode's neutral, already-grounded outcome
provenance, never by interpreting task content. Standard library only.
"""
