package org.eclipse.pde.xmlstudy.probe;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.eclipse.core.resources.IFile;
import org.eclipse.core.resources.IMarker;
import org.eclipse.core.resources.IProject;
import org.eclipse.core.resources.IResource;
import org.eclipse.core.resources.IWorkspace;
import org.eclipse.core.resources.IncrementalProjectBuilder;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.IProgressMonitor;
import org.eclipse.core.runtime.IStatus;
import org.eclipse.core.runtime.Status;
import org.eclipse.core.runtime.jobs.Job;

/** Explicit post-start work. Never scheduled in the default startup scenario. */
final class ValidationScenario {

	private static final String SCHEMA_BUILDER = "org.eclipse.pde.SchemaBuilder";
	private static final String PDE_MARKER = "org.eclipse.pde.core.problem";

	private ValidationScenario() {
	}

	static void schedule(Activator probe) {
		IWorkspace workspace = ResourcesPlugin.getWorkspace();
		Job job = new Job("XML study post-start validation") {
			@Override
			protected IStatus run(IProgressMonitor monitor) {
				try {
					probe.validationStarted();
					List<IProject> projects = projects(workspace);
					List<IFile> schemas = schemas(projects);
					if (schemas.isEmpty()) {
						throw new IllegalStateException("No .exsd files in the selected projects");
					}
					long startUptime = ManagementFactory.getRuntimeMXBean().getUptime();
					long startCpu = Activator.processCpuNs();
					long startNanos = System.nanoTime();
					for (IProject project : projects) {
						if (monitor.isCanceled()) {
							throw new IllegalStateException("Explicit validation was cancelled");
						}
						project.build(IncrementalProjectBuilder.FULL_BUILD, SCHEMA_BUILDER, Map.of(), monitor);
					}
					long endNanos = System.nanoTime();
					long endUptime = ManagementFactory.getRuntimeMXBean().getUptime();
					long endCpu = Activator.processCpuNs();
					Map<String, Object> result = new LinkedHashMap<>();
					result.put("completed", true);
					result.put("builder", SCHEMA_BUILDER);
					result.put("buildKind", "FULL_BUILD");
					result.put("projects", projects.stream().map(IProject::getName).toList());
					result.put("schemaFiles", schemas.size());
					result.put("schemaCountMeaning", "input .exsd candidates; not measured parse attempts");
					result.put("buildStartJvmUptimeMs", startUptime);
					result.put("buildEndJvmUptimeMs", endUptime);
					result.put("buildWallMs", endUptime - startUptime);
					result.put("buildWallNs", endNanos - startNanos);
					result.put("buildProcessCpuNs", startCpu < 0 || endCpu < 0 ? -1 : endCpu - startCpu);
					result.put("markers", markers(schemas));
					probe.validationFinished(result);
					return Status.OK_STATUS;
				} catch (Exception failure) {
					probe.fail(failure);
					return new Status(IStatus.ERROR, Activator.BUNDLE_ID, "Post-start schema validation failed", failure);
				}
			}
		};
		job.setRule(workspace.getRoot());
		job.setPriority(Job.BUILD);
		job.setSystem(true);
		job.schedule();
	}

	private static List<IProject> projects(IWorkspace workspace) throws CoreException {
		Set<String> requested = new LinkedHashSet<>();
		for (String name : System.getProperty("xml.study.projects", "").split(",")) {
			if (!name.isBlank()) {
				requested.add(name.trim());
			}
		}
		List<IProject> selected = new ArrayList<>();
		for (IProject project : workspace.getRoot().getProjects()) {
			if (!requested.isEmpty() && !requested.contains(project.getName())) {
				continue;
			}
			if (project.isOpen() && project.hasNature("org.eclipse.pde.PluginNature")
					&& Arrays.stream(project.getDescription().getBuildSpec())
							.anyMatch(command -> SCHEMA_BUILDER.equals(command.getBuilderName()))) {
				selected.add(project);
			}
		}
		selected.sort((left, right) -> left.getName().compareTo(right.getName()));
		if (selected.isEmpty()) {
			throw new IllegalStateException("No open PDE projects with the schema builder were selected");
		}
		if (!requested.isEmpty()) {
			requested.removeAll(selected.stream().map(IProject::getName).toList());
			if (!requested.isEmpty()) {
				throw new IllegalStateException("Requested projects missing or not eligible: " + requested);
			}
		}
		return selected;
	}

	private static List<IFile> schemas(List<IProject> projects) throws CoreException {
		List<IFile> result = new ArrayList<>();
		for (IProject project : projects) {
			project.accept(resource -> {
				if (resource instanceof IFile file && "exsd".equals(file.getFileExtension())) {
					result.add(file);
				}
				return true;
			});
		}
		return result;
	}

	private static Map<String, Object> markers(List<IFile> schemas) throws CoreException {
		int errors = 0;
		int warnings = 0;
		int information = 0;
		List<Map<String, Object>> diagnostics = new ArrayList<>();
		for (IFile schema : schemas) {
			for (IMarker marker : schema.findMarkers(PDE_MARKER, true, IResource.DEPTH_ZERO)) {
				int severity = marker.getAttribute(IMarker.SEVERITY, -1);
				switch (severity) {
					case IMarker.SEVERITY_ERROR -> errors++;
					case IMarker.SEVERITY_WARNING -> warnings++;
					default -> information++;
				}
				diagnostics.add(Map.of("schemaPath", schema.getFullPath().toString(), "severity", severity,
						"message", marker.getAttribute(IMarker.MESSAGE, ""),
						"line", marker.getAttribute(IMarker.LINE_NUMBER, -1), "markerType", marker.getType()));
			}
		}
		diagnostics.sort(Comparator.comparing((Map<String, Object> item) -> (String) item.get("schemaPath"))
				.thenComparingInt(item -> (Integer) item.get("line"))
				.thenComparingInt(item -> (Integer) item.get("severity"))
				.thenComparing(item -> (String) item.get("message")));
		return Map.of("errors", errors, "warnings", warnings, "information", information,
				"diagnostics", diagnostics,
				"scope", "selected schema files; existing and newly reported PDE markers");
	}
}
