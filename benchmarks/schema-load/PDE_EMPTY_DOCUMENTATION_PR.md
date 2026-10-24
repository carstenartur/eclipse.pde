Title: Handle empty extension point documentation

Valid empty documentation elements such as `<documentation/>` currently fail while PDE builds an extension-point schema model. Both the schema-annotation and element-annotation paths dereference a missing first child; `Schema.load()` catches the resulting exception and leaves the model unloaded.

Normalize an absent text node to the empty string before the existing whitespace normalization. This covers overview documentation, named sections such as `apiinfo`, and element documentation without changing non-empty text handling.

Validation: focused `mvn clean verify` for `org.eclipse.pde.core` and `org.eclipse.pde.ui.tests` with `-Dtest=SchemaDocumentationTest`: **4 tests, no failures or errors**. Three empty-documentation cases failed against the original source; the non-empty normalization case passed before and after. The local two-bundle run used the headless test harness and temporarily omitted the binary PDE feature requirement so the tests resolved the built core bundle; no POM changes are included.

The defect was exposed while checking full schema models during follow-up work related to #2535 and eclipse-platform/eclipse.platform.ui#4518. This is a separate correctness fix; it does not claim to fix the already resolved schema-distribution issue or to improve startup time.

Assisted-by: OpenAI ChatGPT
