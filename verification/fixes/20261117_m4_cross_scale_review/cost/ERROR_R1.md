# Independent checker corrections

The first independent program expected per-scope timing records under scopes[0].stages. Actual producer records store them in the top-level stages dictionary using explicit global/local name prefixes. The original program and KeyError remain in recompute_R0.py and ERROR_R0.txt. The corrected checker sums only render_and_publish_global_* and feedback_global_*.

The next run produced three false failures, preserved in recompute_R1.py and RESULT_R1.json.

- The Git closure check compared the qualification namespace with every changed path. The actual commit also contains the five intended product files. The corrected check verifies exact namespace closure and separately verifies that exact five-file product change set.
- Legacy unittest failures use temporary module names whose numerical suffix depends on the suite composition. The corrected comparison normalizes only that suffix and separately compares all seven AssertionError lines.
- Schema assertion failures occur in test code, so their tracebacks do not record imported product paths. The corrected checker uses the saved baseline flag, pinned runner selection and identical failure text, and checks the accepted baseline's existing brief-v5 assignment. Actual imported module paths were not recorded during that historical suite. The final report retains this provenance limitation.

No product, original record, threshold, geometry, model call, Blender call or raster was changed by these corrections.
