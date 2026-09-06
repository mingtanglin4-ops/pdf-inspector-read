# Agent-level ablation

Run with the plugin/skill and without it, several samples per case, and read
the delta rather than the absolute score:

    claude plugin eval --ablation with-without --runs 5 --threshold 0.8

Case selection rule: only put documents in here that the matrix says the
parsers actually disagree on. A case built from an ordinary text PDF measures
nothing, because every route produces the same text; running those is how you
get a 36/36 tie that tells you nothing.

Read the results as: with-arm minus without-arm, per case, with the spread
across the 5 runs. A skill whose delta is inside the run-to-run spread has no
effect on that case, and saying so is a result.
