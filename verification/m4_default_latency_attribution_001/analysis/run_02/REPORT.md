# One controlled default-latency matrix

The two matched session blocks have opposite signs for the candidate-versus-baseline difference. Attribution of the earlier regression remains unresolved. The controlled ON/OFF mode chain shows a consistent positive paired difference in these four sessions.

## Integrity and scope

The saved-record analysis passed 1502 checks with zero failures. Four fixed B,C,C,B sessions completed 88 business calls, 40 warm pairs, 92 received worker RPCs and 104 product stdio messages. Each version contributes two independent sessions. All raw warm observations remain in the machine result under each session's rows and summary distributions.

The source, exact request, facts, capture generation, profiler schedule/restoration, required kernel counters, actual process PID/exit proof and owned close gates passed. The two original product versions remain e077/53db and a81/9f28. The implementation's later schema version remains outside this experiment.

## Session observations

All times in the following table are milliseconds. ON and OFF each contain ten warm observations per session. The paired column is the median of ten individual ON-minus-OFF differences.

| Session | ON median | ON range | OFF median | OFF range | Paired difference median | Paired difference range |
| --- | ---: | --- | ---: | --- | ---: | --- |
| 01_B | 40.28690 | 38.47510–42.86160 | 32.27320 | 29.64110–34.71430 | 7.71165 | 5.83080–11.23720 |
| 02_C | 38.95905 | 37.60690–40.24970 | 30.59225 | 28.80580–32.28110 | 8.41025 | 6.69560–10.09410 |
| 03_C | 38.58540 | 36.42630–40.47810 | 30.73355 | 29.54510–32.94690 | 7.49280 | 6.56320–9.75330 |
| 04_B | 38.56500 | 37.03400–39.71010 | 30.32325 | 28.86210–34.03310 | 7.81445 | 4.77000–10.84800 |

| Session | Cold | Warmup | ON position 1 / 2 | OFF position 1 / 2 |
| --- | ---: | ---: | --- | --- |
| 01_B | 122.67310 | 33.16270 | 40.87780 / 39.69600 | 32.12770 / 32.31280 |
| 02_C | 119.81360 | 29.21330 | 39.12400 / 38.89990 | 30.91130 / 30.56450 |
| 03_C | 120.49480 | 29.97490 | 39.50310 / 37.91160 | 30.91900 / 30.70020 |
| 04_B | 119.20110 | 28.98350 | 38.80310 / 38.50820 | 30.52970 / 30.11680 |

Cold and warmup values remain separate. Each position stratum has five observations per mode. Previous-mode strata and all individual paired differences remain in RESULTS.json. Their populations follow the fixed logical state chain, including repeated ON or OFF across pair boundaries.

## Version contrasts

| Matched baseline / candidate sessions | C minus B, ON | C minus B, OFF | Interaction |
| --- | ---: | ---: | ---: |
| 01_B / 02_C | -1.32785 | -1.68095 | 0.35310 |
| 04_B / 03_C | 0.02040 | 0.41030 | -0.38990 |

Equal-weight differences of the two session medians are -0.65373 ms under ON and -0.63533 ms under OFF. The matched-block interactions have different signs. These descriptive results retain the session as the independent unit.

## Complete recorded cost

Batch wall time is 11.9622809 seconds. It includes frozen-commit verification of 889.3355 ms and input verification of 68.3031 ms. The four session walls total 10.8087924 seconds. The batch endpoint precedes its final result publication and excludes interpreter import, as recorded by the frozen entry.

| Recorded stage | Sum over four sessions, ms |
| --- | ---: |
| business_loop | 3945.01020 |
| metadata | 3095.84110 |
| native_close | 626.86610 |
| native_startup | 2639.38070 |
| product_PID_proof | 49.25850 |
| product_close | 411.07050 |
| product_startup | 29.21660 |
| runtime_exit_proof | 0.31000 |
| verification | 492.44370 |

The verification sum is already included in business_loop. Stage values and nested request spans overlap. Entry, Peer, trace, host capture, content encoding, verification and inclusive QA scope distributions remain available for every mode and session.

| Session | Stdio TX bytes | Stdio RX bytes | Product lifetime peak RSS bytes |
| --- | ---: | ---: | ---: |
| 01_B | 4782 | 134066 | 92663808 |
| 02_C | 4782 | 134676 | 92700672 |
| 03_C | 4782 | 134676 | 92827648 |
| 04_B | 4782 | 134066 | 93028352 |

Product memory records are process-lifetime OS high-water marks. Worker OS peak and isolated request allocations remain unmeasured.

## Interpretation limits and retained correction

The ON-minus-OFF difference includes callback execution, state checks and the natural dict-versus-null recording/publication path. The inclusive profile_scope starts with state construction and overlaps the before/after probes. New probe boundaries differ from the earlier experiment. Callback-only overhead remains unisolated, and observed bpy C-method names remain incomplete.

The frozen analyzer's first saved-only run stopped on a KeyError for pair_calls in warm telemetry. Its original source, error and partial checks remain unchanged in run_01. A source-bound field-contract review found that warm cache-hit telemetry emits three initialized kernel counters, while pair_calls and rank_calls are absent. The derived script checks the three required keys directly and explicitly records the absent extra counters. Nine metadata regressions cover the real sparse shape and rejection of missing/nonzero required counters. SOURCE.diff and both installed source fragments remain under field_fix_001.

The earlier sealed +3.57% observation and admission state remain part of the record. This experiment adds a controlled observation with two sessions per version. Production latency equivalence, model-task benefit and full admission remain unestablished. No additional runtime sample, image, consumer, installation or paid API call was added by analysis.
