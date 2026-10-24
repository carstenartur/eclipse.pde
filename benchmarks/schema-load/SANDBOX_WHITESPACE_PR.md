Title: Preserve meaningful whitespace during XML cleanup

XML cleanup currently strips whitespace-only text globally and rewrites indentation without knowing whether it belongs to content. This can remove separators in mixed content, change `xml:space="preserve"` subtrees, or turn whitespace-only EXSD documentation into an empty element.

Limit whitespace formatting to known structural XSD/EXSD containers and the enclosing PDE descriptor containers. Preserve documentation, appinfo, mixed content and unknown payloads as complete subtrees. Indented output retains readable separation of declaration, comments, processing instructions and root, and ends with a newline. Marker locations fall back to file level when the candidate source line survives unchanged in the prepared output.

Updated regression tests and the README, architecture document and installed Help describe that conservative scope. Both compact and indented output are idempotent; arbitrary XML payloads are not promised to be reformatted.

Validation:

- Focused Maven/Tycho `verify` passed for all seven reactor modules: 1,336 shared-core tests, 51 test-commons tests and 103 XML tests, with zero failures/errors. Two existing optional pinned-JDT-corpus tests were skipped because their external paths were not configured. SpotBugs reported zero bugs/errors.
- The whitespace, prolog and marker-location regressions were observed failing before their corresponding corrections.
- Direct real-helper/corpus checks: 76 passed. Across 50 real `org.eclipse.ui` files, both modes are idempotent and preserve all 1,066 documentation elements, including 45 whitespace-only leaves, plus appinfo and extension payloads.
- Independent full PDE-model comparison: all 49 schema models match the original files, including 15 additional include loads and 229 elements. This also passes against unmodified PDE, so the cleanup does not rely on the separate empty-documentation fix.

Command: `./mvnw -s <local-settings> -pl sandbox_target,sandbox_common,sandbox_test_commons,sandbox_xml_cleanup_test -am --batch-mode verify`, Java 25. A TCP-only Xvfb display was used because this environment cannot expose X11 Unix sockets. No test-skip or failure-ignore switches were used.

Related context: eclipse-pde/eclipse.pde#2535 and eclipse-platform/eclipse.platform.ui#4518 motivated measuring the schema corpus. No Eclipse startup speedup is claimed by this safety fix.

Assisted-by: OpenAI ChatGPT
