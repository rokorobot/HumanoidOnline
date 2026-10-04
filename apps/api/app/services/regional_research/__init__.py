"""Regional Research Resource read model (ADR-027, Step 2).

`readmodel.build_regional_availability` is the pure aggregation (no I/O, clock,
randomness or LLM); `inputs` holds the plain dataclasses it consumes and the
outputs it returns. A database loader and any presentation layer are separate,
later steps.
"""
