# Preserved first input set

This is the complete manifest and output of the initial uniform-dimension run.
It was run before input set version 2 was created.

It used 30 separately identified graph inputs, but repeated room counts only changed
GUIDs/seeds. The placement implementation does not consume Seed, so these records do
not establish 30 geometrically distinct arrangements. This limitation prompted the
dimension formula in the final manifest; the generation implementation was unchanged.

All original failures are preserved: 30 room placements succeeded, ten chain geometries
and navigation queries succeeded, and twenty branching/ring cases stopped at overlapping
doors. The ten Local/Full benchmark pairs passed equivalence.

These records are historical and are not combined with the final results in
`Experiments/results`. Source hashes describe the source/scripts at this earlier run;
the current manifest builder subsequently changed. The original complete inputs remain
in both this manifest and `results/raw_results.json`.
