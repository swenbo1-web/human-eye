# Previous batch timing clarification

The sealed M3-PAIR-SCALABILITY-001 report and original samples remain preserved at evidence commit 743a484f16f1dadff8dedcf1abad8d0a14398d17.

Its report describes separate preparation windows. The actual samples contain closed_ns, surface_ns and complete_ns. Preparation is included in closed_ns and has separate operation counts. There is no independently timed preparation window in those samples.

The Competing surface stage changes from a median 180.9047 ms to 219.4475 ms, an increase of approximately 21.31 percent. Its expensive distance leaves increase from 1048 to 1324, approximately 26.34 percent. These unfavorable observations remain part of the prior result.

The old timing includes QA function spies and a checkpoint-count dictionary. It has no instrumentation-disabled control and supplies no basis for subtracting that overhead. This batch pre-registers a fresh finite sequence without those extra timing instruments.
