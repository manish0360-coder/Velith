# Fixtures under tests/fixtures/ are task DATA, not part of the test suite. They
# model buggy repositories whose hidden tests are meant to FAIL on the unpatched
# code, and are executed only by the verifier (C4) against a disposable copy —
# never collected by the main pytest run (which would turn an intentional failure
# into a red suite). collect_ignore_glob excludes everything beneath this folder.
collect_ignore_glob = ["*"]
