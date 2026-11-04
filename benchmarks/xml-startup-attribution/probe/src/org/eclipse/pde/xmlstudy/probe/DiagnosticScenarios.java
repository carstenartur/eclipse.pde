package org.eclipse.pde.xmlstudy.probe;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BiConsumer;

import org.eclipse.core.resources.*;
import org.eclipse.core.runtime.*;
import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.ui.*;
import org.eclipse.ui.part.FileEditorInput;

/** Small, explicit diagnostic workloads; none belongs in primary timing cells. */
final class DiagnosticScenarios {
    static final String PROVIDER = "org.eclipse.pde.xmlstudy.control";
    static final String CONSUMER = "org.eclipse.pde.xmlstudy.consumer";
    static final String MANIFEST_EDITOR = "org.eclipse.pde.ui.manifestEditor";
    static final String SCHEMA_EDITOR = "org.eclipse.pde.ui.schemaEditor";

    private DiagnosticScenarios() { }

    static Map<String, Object> automaticBuild(BiConsumer<String, Map<String, Object>> phase) throws Exception {
        IWorkspace workspace = ResourcesPlugin.getWorkspace();
        CountDownLatch built = new CountDownLatch(1);
        AtomicInteger autoBuilds = new AtomicInteger();
        IResourceChangeListener listener = event -> {
            if (event.getType() == IResourceChangeEvent.POST_BUILD
                    && event.getBuildKind() == IncrementalProjectBuilder.AUTO_BUILD) {
                autoBuilds.incrementAndGet();
                built.countDown();
            }
        };
        workspace.addResourceChangeListener(listener, IResourceChangeEvent.POST_BUILD);
        try {
            phase.accept("automatic_build_trigger_started", Map.of("trigger", "enable auto build and touch provider schema plus consumer plugin.xml"));
            IWorkspaceDescription settings = workspace.getDescription();
            settings.setAutoBuilding(true);
            workspace.setDescription(settings);
            workspace.run(monitor -> {
                workspace.getRoot().getProject(PROVIDER).getFile("schema/control.exsd").touch(monitor);
                workspace.getRoot().getProject(CONSUMER).getFile("plugin.xml").touch(monitor);
            }, null, IWorkspace.AVOID_UPDATE, new NullProgressMonitor());
            phase.accept("automatic_build_fixture_changed", Map.of());
            if (!built.await(45, TimeUnit.SECONDS)) throw new IllegalStateException("No AUTO_BUILD completion event after changing fixture");
            Job.getJobManager().join(ResourcesPlugin.FAMILY_AUTO_BUILD, new NullProgressMonitor());
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("automaticBuildEvents", autoBuilds.get());
            result.put("autoBuildEnabled", workspace.getDescription().isAutoBuilding());
            result.put("trigger", "resource touches; no explicit workspace.build call");
            List<Map<String, Object>> errors = new ArrayList<>();
            for (String name : List.of(PROVIDER, CONSUMER)) {
                IProject project = workspace.getRoot().getProject(name);
                for (IMarker marker : project.findMarkers(IMarker.PROBLEM, true, IResource.DEPTH_INFINITE)) {
                    if (marker.getAttribute(IMarker.SEVERITY, 0) == IMarker.SEVERITY_ERROR) {
                        errors.add(Map.of("project", name, "type", marker.getType(), "message", marker.getAttribute(IMarker.MESSAGE, "")));
                    }
                }
            }
            result.put("errorMarkers", errors);
            phase.accept("automatic_build_finished", result);
            if (!errors.isEmpty()) throw new IllegalStateException("Automatic build produced error markers: " + errors);
            return result;
        } finally {
            workspace.removeResourceChangeListener(listener);
        }
    }

    static void scheduleAutomaticBuild(Activator probe) {
        Job job = new Job("XML diagnostic automatic-build trigger") {
            @Override protected IStatus run(IProgressMonitor monitor) {
                try {
                    Map<String, Object> result = automaticBuild(probe::diagnosticPhase);
                    probe.diagnosticFinished(result);
                    return Status.OK_STATUS;
                } catch (Exception failure) {
                    probe.fail(failure);
                    return new Status(IStatus.ERROR, Activator.BUNDLE_ID, "Automatic-build diagnostic failed", failure);
                }
            }
        };
        job.setSystem(true);
        job.schedule();
    }

    static void seedEditors(Activator probe, IWorkbench workbench) throws PartInitException {
        probe.diagnosticPhase("editor_seed_started", Map.of());
        IWorkbenchPage page = workbench.getActiveWorkbenchWindow().getActivePage();
        IWorkspaceRoot root = ResourcesPlugin.getWorkspace().getRoot();
        page.openEditor(new FileEditorInput(root.getProject(CONSUMER).getFile("META-INF/MANIFEST.MF")), MANIFEST_EDITOR);
        page.openEditor(new FileEditorInput(root.getProject(PROVIDER).getFile("schema/control.exsd")), SCHEMA_EDITOR);
        Map<String, Object> result = snapshot(workbench);
        probe.diagnosticPhase("editor_seed_finished", result);
        probe.diagnosticFinished(result);
    }

    static Map<String, Object> snapshot(IWorkbench workbench) {
        List<Map<String, Object>> editors = new ArrayList<>();
        for (IWorkbenchWindow window : workbench.getWorkbenchWindows()) {
            for (IWorkbenchPage page : window.getPages()) {
                for (IEditorReference reference : page.getEditorReferences()) {
                    IEditorPart materialized = reference.getEditor(false);
                    Map<String, Object> editor = new LinkedHashMap<>();
                    editor.put("id", reference.getId());
                    editor.put("name", reference.getName());
                    editor.put("materialized", materialized != null);
                    if (materialized != null) editor.put("class", materialized.getClass().getName());
                    editors.add(editor);
                }
            }
        }
        return Map.of("autoBuildEnabled", ResourcesPlugin.getWorkspace().getDescription().isAutoBuilding(),
                "editors", editors, "editorObservation", "getEditor(false); no forced restoration");
    }
}
