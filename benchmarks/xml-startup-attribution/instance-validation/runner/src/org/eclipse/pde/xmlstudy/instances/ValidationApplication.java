package org.eclipse.pde.xmlstudy.instances;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.eclipse.core.resources.IFile;
import org.eclipse.core.resources.IMarker;
import org.eclipse.core.resources.IProject;
import org.eclipse.core.resources.IProjectDescription;
import org.eclipse.core.resources.IResource;
import org.eclipse.core.resources.IWorkspace;
import org.eclipse.core.resources.IWorkspaceDescription;
import org.eclipse.core.resources.ProjectScope;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.core.runtime.Platform;
import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;
import org.eclipse.pde.core.plugin.IPluginExtensionPoint;
import org.eclipse.pde.core.plugin.IPluginModelBase;
import org.eclipse.pde.core.plugin.PluginRegistry;
import org.eclipse.pde.internal.core.PDECore;
import org.eclipse.pde.internal.core.builders.CompilerFlags;
import org.eclipse.pde.internal.core.builders.DefaultSAXParser;
import org.eclipse.pde.internal.core.builders.ExtensionsErrorReporter;
import org.eclipse.pde.internal.core.builders.IncrementalErrorReporter.VirtualMarker;
import org.eclipse.pde.internal.core.builders.PDEMarkerFactory;
import org.eclipse.pde.internal.core.ischema.ISchema;
import org.eclipse.pde.internal.core.natures.BaseProject;
import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.SchemaRegistry;
import org.osgi.service.prefs.Preferences;
import org.w3c.dom.Element;
import org.xml.sax.SAXException;

/** Calls the installed PDE validator. No schema rules are reimplemented here. */
public final class ValidationApplication implements IApplication {

	private static final String CONTROL_PROJECT = "org.eclipse.pde.xmlstudy.validationcontrols";
	private static final Map<String, Integer> FLAGS = flags();
	private final NullProgressMonitor monitor = new NullProgressMonitor();

	@Override
	public Object start(IApplicationContext context) throws Exception {
		Path output = Path.of(required("xml.instances.output"));
		Map<String, Object> result = new LinkedHashMap<>();
		result.put("formatVersion", 1);
		result.put("application", "org.eclipse.pde.xmlstudy.instances.validate");
		result.put("reporter", ExtensionsErrorReporter.class.getName());
		result.put("pdeVersion", Platform.getBundle("org.eclipse.pde.core").getVersion().toString());
		result.put("javaVersion", System.getProperty("java.runtime.version"));
		result.put("os", System.getProperty("os.name"));
		result.put("preferences", FLAGS);
		result.put("preferenceQualifier", BaseProject.PDE_PLUGIN_ID);
		result.put("validationScope", "PDE extension grammar with explicit structural preferences; not complete W3C XSD, Java, resource, NLS, identifier-reference, deprecation or manifest validation");
		result.put("coverageLookupMeaning", "One supplemental SchemaRegistry lookup per unique point after validation, followed by loaded/valid state inspection. These are not measured parse counts.");
		try {
			IWorkspace workspace = ResourcesPlugin.getWorkspace();
			IWorkspaceDescription settings = workspace.getDescription();
			settings.setAutoBuilding(false);
			workspace.setDescription(settings);
			List<IProject> projects = importProjects(workspace, Path.of(required("xml.instances.projectList")));
			IProject controlProject = importProject(workspace, Path.of(required("xml.instances.controlDirectory")));
			if (!CONTROL_PROJECT.equals(controlProject.getName())) {
				throw new IllegalStateException("Unexpected control project: " + controlProject.getName());
			}
			for (IProject project : projects) {
				setPreferences(project);
			}
			setPreferences(controlProject);
			IPluginModelBase[] models = PluginRegistry.getAllModels();
			List<String> missingModels = new ArrayList<>();
			for (IProject project : projects) {
				IPluginModelBase model = PluginRegistry.findModel(project);
				if (model == null || !project.getName().equals(model.getPluginBase().getId())) {
					missingModels.add(project.getName());
				}
			}
			if (!missingModels.isEmpty() || PluginRegistry.findModel(controlProject) == null) {
				throw new IllegalStateException("Workspace models unavailable: " + missingModels);
			}
			for (String point : List.of("grammar", "order", "choice", "choiceSequence", "missing", "unspecified")) {
				if (!PDECore.getDefault().getExtensionsRegistry().hasExtensionPoint(CONTROL_PROJECT + "." + point)) {
					throw new IllegalStateException("Control extension point was not registered: " + point);
				}
			}
			result.put("registeredModelCount", models.length);
			result.put("registeredModels", java.util.Arrays.stream(models).map(model -> {
				Map<String, Object> entry = new LinkedHashMap<>();
				entry.put("id", model.getPluginBase().getId());
				entry.put("version", model.getPluginBase().getVersion());
				entry.put("installLocation", model.getInstallLocation());
				entry.put("workspaceResource", model.getUnderlyingResource() == null ? null
						: model.getUnderlyingResource().getFullPath().toPortableString());
				return entry;
			}).sorted(Comparator.comparing(Json::encode)).toList());
			result.put("projects", projects.stream().map(IProject::getName).toList());
			List<Map<String, Object>> files = new ArrayList<>();
			for (IProject project : projects) {
				for (String name : List.of("plugin.xml", "fragment.xml")) {
					IFile file = project.getFile(name);
					if (file.exists()) {
						files.add(validateFile(file));
					}
				}
			}
			result.put("files", files);
			Map<String, Object> coverage = coverage(files);
			result.put("schemasByExtensionPoint", coverage);
			applyCoverage(files, coverage);
			List<Map<String, Object>> controls = new ArrayList<>();
			for (String line : Files.readAllLines(Path.of(required("xml.instances.controlCases")), StandardCharsets.UTF_8)) {
				if (line.isBlank() || line.startsWith("#")) {
					continue;
				}
				String[] fields = line.split("\t", 3);
				if (fields.length != 3 || fields[0].contains("/") || fields[0].contains("..")) {
					throw new IllegalArgumentException("Invalid control case row: " + line);
				}
				Map<String, Object> control = validateFile(controlProject.getFile("cases/" + fields[0]));
				control.put("expectation", fields[1]);
				control.put("description", fields[2]);
				controls.add(control);
			}
			Map<String, Object> controlCoverage = coverage(controls);
			applyCoverage(controls, controlCoverage);
			result.put("controlSchemasByExtensionPoint", controlCoverage);
			result.put("controls", controls);
			boolean controlsPassed = checkControls(controls);
			result.put("controlsPassed", controlsPassed);
			result.put("summary", summarize(files));
			if (Boolean.getBoolean("xml.instances.repeatedLoadProbe")) {
				result.put("repeatedLoadDiagnostic", RepeatedLoadProbe.run());
			}
			result.put("status", controlsPassed && files.stream().allMatch(file -> Boolean.TRUE.equals(file.get("completed")))
					? "completed" : "failed");
			workspace.save(true, monitor);
			write(output, result);
			System.out.println("XML_INSTANCE_RESULT " + Json.encode(Map.of("status", result.get("status"),
					"output", output.toString(), "summary", result.get("summary"), "controlsPassed", controlsPassed)));
			return "completed".equals(result.get("status")) ? EXIT_OK : Integer.valueOf(2);
		} catch (Exception failure) {
			result.put("status", "failed");
			result.put("failure", stack(failure));
			write(output, result);
			throw failure;
		}
	}

	private List<IProject> importProjects(IWorkspace workspace, Path list) throws Exception {
		List<IProject> projects = new ArrayList<>();
		Set<String> names = new LinkedHashSet<>();
		for (String line : Files.readAllLines(list, StandardCharsets.UTF_8)) {
			if (line.isBlank() || line.stripLeading().startsWith("#")) {
				continue;
			}
			IProject project = importProject(workspace, Path.of(line.trim()));
			if (CONTROL_PROJECT.equals(project.getName()) || !names.add(project.getName())) {
				throw new IllegalArgumentException("Duplicate/control project in corpus: " + project.getName());
			}
			projects.add(project);
		}
		if (projects.isEmpty()) {
			throw new IllegalArgumentException("Empty project list");
		}
		projects.sort(Comparator.comparing(IProject::getName));
		return projects;
	}

	private IProject importProject(IWorkspace workspace, Path directory) throws Exception {
		if (!directory.isAbsolute() || !Files.isRegularFile(directory.resolve(".project"))) {
			throw new IllegalArgumentException("Expected absolute project directory: " + directory);
		}
		IProjectDescription description = workspace.loadProjectDescription(
				org.eclipse.core.runtime.Path.fromOSString(directory.resolve(".project").toString()));
		description.setLocationURI(directory.toUri());
		IProject project = workspace.getRoot().getProject(description.getName());
		if (project.exists()) {
			throw new IllegalStateException("Fresh workspace required; project already exists: " + project.getName());
		}
		project.create(description, monitor);
		project.open(monitor);
		return project;
	}

	private static void setPreferences(IProject project) throws Exception {
		Preferences node = new ProjectScope(project).getNode(BaseProject.PDE_PLUGIN_ID);
		for (var entry : FLAGS.entrySet()) {
			node.putInt(entry.getKey(), entry.getValue());
		}
		node.flush();
		for (var entry : FLAGS.entrySet()) {
			if (CompilerFlags.getFlag(project, entry.getKey()) != entry.getValue()) {
				throw new IllegalStateException("Preference not effective: " + project.getName() + ": " + entry.getKey());
			}
		}
	}

	private Map<String, Object> validateFile(IFile file) throws Exception {
		Map<String, Object> result = new LinkedHashMap<>();
		result.put("project", file.getProject().getName());
		result.put("file", file.getProjectRelativePath().toPortableString());
		result.put("workspacePath", file.getFullPath().toPortableString());
		byte[] bytes;
		try (var stream = file.getContents()) {
			bytes = stream.readAllBytes();
		}
		result.put("byteLength", bytes.length);
		result.put("sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
		file.deleteMarkers(PDEMarkerFactory.MARKER_ID, true, IResource.DEPTH_ZERO);
		ObservedReporter reporter = new ObservedReporter(file);
		try {
			DefaultSAXParser.parse(file, reporter);
			reporter.validateContent(monitor);
			result.put("completed", reporter.parseCompleted);
		} catch (RuntimeException failure) {
			result.put("completed", false);
			result.put("failure", stack(failure));
		}
		Element root = reporter.getDocumentRoot();
		result.put("documentElement", root == null ? null : root.getNodeName());
		result.put("parseCompleted", reporter.parseCompleted);
		result.put("extensions", reporter.extensionRecords());
		result.put("extensionCount", reporter.extensions.size());
		List<Map<String, Object>> diagnostics = markers(file);
		result.put("diagnostics", diagnostics);
		result.put("diagnosticCount", diagnostics.size());
		return result;
	}

	private static List<Map<String, Object>> markers(IFile file) throws CoreException {
		List<Map<String, Object>> result = new ArrayList<>();
		for (IMarker marker : file.findMarkers(PDEMarkerFactory.MARKER_ID, true, IResource.DEPTH_ZERO)) {
			Map<String, Object> entry = new LinkedHashMap<>();
			entry.put("type", marker.getType());
			entry.put("attributes", new TreeMap<>(marker.getAttributes()));
			result.add(entry);
		}
		result.sort(Comparator.comparing(Json::encode));
		return result;
	}

	private static Map<String, Object> coverage(List<Map<String, Object>> files) {
		Set<String> points = new java.util.TreeSet<>();
		for (Map<String, Object> file : files) {
			for (Map<String, Object> extension : extensions(file)) {
				points.add((String) extension.get("point"));
			}
		}
		Map<String, Object> result = new LinkedHashMap<>();
		for (String point : points) {
			Map<String, Object> entry = new LinkedHashMap<>();
			entry.put("point", point);
			try {
				IPluginExtensionPoint declaration = PDECore.getDefault().getExtensionsRegistry().findExtensionPoint(point);
				entry.put("pointPresent", declaration != null);
				if (declaration == null) {
					entry.put("status", "unknown-extension-point");
				} else {
					entry.put("provider", declaration.getPluginBase().getId());
					entry.put("providerModelLocation", declaration.getPluginModel().getInstallLocation());
					entry.put("providerWorkspaceResource", declaration.getPluginModel().getUnderlyingResource() == null ? null
							: declaration.getPluginModel().getUnderlyingResource().getFullPath().toPortableString());
					entry.put("schemaDeclaration", declaration.getSchema());
					var url = SchemaRegistry.getSchemaURL(declaration);
					entry.put("schemaUrl", url == null ? null : url.toExternalForm());
					ISchema schema = PDECore.getDefault().getSchemaRegistry().getSchema(point);
					entry.put("modelPresent", schema != null);
					if (schema == null) {
						entry.put("status", declaration.getSchema() == null || declaration.getSchema().isBlank()
								? "no-schema-declaration" : "schema-unavailable");
					} else {
						boolean loaded = schema instanceof Schema concrete && concrete.isLoaded();
						entry.put("modelClass", schema.getClass().getName());
						entry.put("modelLoaded", loaded);
						entry.put("modelValid", schema.isValid());
						entry.put("modelUrl", schema.getURL() == null ? null : schema.getURL().toExternalForm());
						boolean rootPresent = loaded && schema.findElement("extension") != null;
						entry.put("extensionRootPresent", rootPresent);
						entry.put("status", !loaded ? "schema-load-failed" : !schema.isValid() ? "invalid-schema-model"
								: !rootPresent ? "schema-root-missing" : "schema-model-loaded");
					}
				}
			} catch (RuntimeException failure) {
				entry.put("status", "coverage-exception");
				entry.put("failure", stack(failure));
			}
			result.put(point, entry);
		}
		return result;
	}

	private static void applyCoverage(List<Map<String, Object>> files, Map<String, Object> coverage) {
		for (Map<String, Object> file : files) {
			for (Map<String, Object> extension : extensions(file)) {
				@SuppressWarnings("unchecked")
				Map<String, Object> point = (Map<String, Object>) coverage.get(extension.get("point"));
				extension.put("coverageStatus", point.get("status"));
			}
		}
	}

	@SuppressWarnings("unchecked")
	private static List<Map<String, Object>> extensions(Map<String, Object> file) {
		return (List<Map<String, Object>>) file.get("extensions");
	}

	private static boolean checkControls(List<Map<String, Object>> controls) {
		boolean allPassed = !controls.isEmpty();
		for (Map<String, Object> control : controls) {
			int count = (Integer) control.get("diagnosticCount");
			boolean complete = Boolean.TRUE.equals(control.get("completed"));
			boolean schemaAvailable = extensions(control).stream().allMatch(
					extension -> "schema-model-loaded".equals(extension.get("coverageStatus")));
			boolean result = switch ((String) control.get("expectation")) {
				case "accept" -> complete && schemaAvailable && count == 0;
				case "reject" -> complete && schemaAvailable && count > 0;
				case "reject-point" -> complete && count > 0 && extensions(control).stream().anyMatch(
						extension -> "unknown-extension-point".equals(extension.get("coverageStatus")));
				case "coverage-gap" -> complete && extensions(control).stream().anyMatch(
						extension -> Set.of("schema-unavailable", "schema-load-failed", "no-schema-declaration")
							.contains(extension.get("coverageStatus")));
				case "observe-invalid" -> complete && schemaAvailable;
				default -> throw new IllegalArgumentException("Unknown control expectation: " + control.get("expectation"));
			};
			control.put("harnessCheckPassed", result);
			control.put("pdeReportedDiagnostic", count > 0);
			if ("observe-invalid".equals(control.get("expectation"))) {
				control.put("knownInvalidInputAcceptedWithoutDiagnostic", complete && schemaAvailable && count == 0);
			}
			allPassed &= result;
		}
		return allPassed;
	}

	private static Map<String, Object> summarize(List<Map<String, Object>> files) {
		Map<String, Integer> byCoverage = new TreeMap<>();
		int extensionCount = 0;
		int diagnostics = 0;
		int errors = 0;
		int warnings = 0;
		int information = 0;
		for (Map<String, Object> file : files) {
			extensionCount += (Integer) file.get("extensionCount");
			diagnostics += (Integer) file.get("diagnosticCount");
			for (Map<String, Object> extension : extensions(file)) {
				byCoverage.merge((String) extension.get("coverageStatus"), 1, Integer::sum);
			}
			@SuppressWarnings("unchecked")
			List<Map<String, Object>> markers = (List<Map<String, Object>>) file.get("diagnostics");
			for (Map<String, Object> marker : markers) {
				@SuppressWarnings("unchecked")
				Map<String, Object> attributes = (Map<String, Object>) marker.get("attributes");
				Object severity = attributes.get(IMarker.SEVERITY);
				if (Integer.valueOf(IMarker.SEVERITY_ERROR).equals(severity)) {
					errors++;
				} else if (Integer.valueOf(IMarker.SEVERITY_WARNING).equals(severity)) {
					warnings++;
				} else {
					information++;
				}
			}
		}
		return Map.of("descriptorFiles", files.size(), "extensionContributions", extensionCount,
				"diagnostics", diagnostics, "errors", errors, "warnings", warnings,
				"information", information, "contributionsByCoverage", byCoverage);
	}

	private static Map<String, Integer> flags() {
		Map<String, Integer> result = new LinkedHashMap<>();
		for (String key : List.of(CompilerFlags.P_UNKNOWN_ELEMENT, CompilerFlags.P_UNKNOWN_ATTRIBUTE,
				CompilerFlags.P_NO_REQUIRED_ATT, CompilerFlags.P_UNRESOLVED_EX_POINTS)) {
			result.put(key, CompilerFlags.ERROR);
		}
		for (String key : List.of(CompilerFlags.P_UNKNOWN_CLASS, CompilerFlags.P_DISCOURAGED_CLASS,
				CompilerFlags.P_UNKNOWN_RESOURCE, CompilerFlags.P_NOT_EXTERNALIZED,
				CompilerFlags.P_UNKNOWN_IDENTIFIER, CompilerFlags.P_DEPRECATED, CompilerFlags.P_INTERNAL)) {
			result.put(key, CompilerFlags.IGNORE);
		}
		return result;
	}

	private static String required(String property) {
		String value = System.getProperty(property, "");
		if (value.isBlank()) {
			throw new IllegalArgumentException("Required JVM property: " + property);
		}
		return value;
	}

	private static String stack(Throwable failure) {
		StringWriter text = new StringWriter();
		failure.printStackTrace(new PrintWriter(text));
		return text.toString();
	}

	private static void write(Path output, Map<String, Object> value) throws Exception {
		Files.createDirectories(output.toAbsolutePath().getParent());
		Path temporary = output.resolveSibling(output.getFileName() + ".tmp");
		Files.writeString(temporary, Json.encode(value) + "\n", StandardCharsets.UTF_8);
		Files.move(temporary, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
	}

	@Override
	public void stop() {
	}

	/** Adds observation only; validation decisions are made by the installed superclass. */
	private static final class ObservedReporter extends ExtensionsErrorReporter {
		private final List<ExtensionRecord> extensions = new ArrayList<>();
		private ExtensionRecord current;
		private boolean parseCompleted;

		ObservedReporter(IFile file) {
			super(file);
		}

		@Override
		public void endDocument() throws SAXException {
			super.endDocument();
			parseCompleted = true;
		}

		@Override
		protected void validateExtension(Element element) {
			ExtensionRecord extension = new ExtensionRecord(element.getAttribute("point"), getLine(element), extensions.size() + 1);
			extensions.add(extension);
			current = extension;
			try {
				super.validateExtension(element);
				extension.completed = true;
			} finally {
				current = null;
			}
		}

		@Override
		public VirtualMarker report(String message, int line, int severity, int fixId, String category) {
			VirtualMarker marker = super.report(message, line, severity, fixId, category);
			if (current != null && marker != null) {
				current.markers.add(marker);
			}
			return marker;
		}

		List<Map<String, Object>> extensionRecords() {
			return extensions.stream().map(ExtensionRecord::record).toList();
		}
	}

	private static final class ExtensionRecord {
		private final String point;
		private final int line;
		private final int ordinal;
		private final List<VirtualMarker> markers = new ArrayList<>();
		private boolean completed;

		ExtensionRecord(String point, int line, int ordinal) {
			this.point = point;
			this.line = line;
			this.ordinal = ordinal;
		}

		Map<String, Object> record() {
			Map<String, Object> result = new LinkedHashMap<>();
			result.put("ordinal", ordinal);
			result.put("point", point);
			result.put("line", line);
			result.put("completed", completed);
			result.put("diagnostics", markers.stream().map(marker -> new TreeMap<>(marker.getAttributes())).toList());
			result.put("diagnosticCount", markers.size());
			return result;
		}
	}
}
