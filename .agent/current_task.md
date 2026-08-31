# Current Task

## Task

`GENERALIZE-RUNNERS`: Generalize independent framed evidence collection and parent verification across physical gates DR1 through DR15.

## Status

`READY` (`DR0-EVIDENCE-DESIGN` and `DR0-MIGRATE` completed on `implement/dr0-evidence`).
DR0 now emits framed JSON evidence with full public test buffers and device metadata; parent runner independently verifies all 24 x 256 coefficients against the independent reference oracle and strictly validates PID, nonce, timestamps, artifact hashes, and emulation exclusion.

