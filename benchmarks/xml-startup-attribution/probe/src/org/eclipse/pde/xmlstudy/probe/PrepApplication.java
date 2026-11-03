package org.eclipse.pde.xmlstudy.probe;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.eclipse.core.resources.IProject;
import org.eclipse.core.resources.IProjectDescription;
import org.eclipse.core.resources.IWorkspace;
import org.eclipse.core.resources.IWorkspaceDescription;
import org.eclipse.core.resources.ResourcesPlugin;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;

/** Import an explicit project-directory list into a disposable fixture workspace. */
public final class PrepApplication implements IApplication {

	@Override
	public Object start(IApplicationContext context) throws Exception {
		if (Boolean.parseBoolean(System.getProperty("xml.study.enabled", "true"))) {
			throw new IllegalArgumentException("Workspace preparation requires -Dxml.study.enabled=false");
		}
		String listPath = System.getProperty("xml.study.projectList", "");
		if (listPath.isBlank()) {
			throw new IllegalArgumentException("Set xml.study.projectList to a UTF-8 file of absolute project-directory paths");
		}
		IWorkspace workspace = ResourcesPlugin.getWorkspace();
		IWorkspaceDescription settings = workspace.getDescription();
		settings.setAutoBuilding(false);
		workspace.setDescription(settings);
		NullProgressMonitor monitor = new NullProgressMonitor();
		List<String> imported = new ArrayList<>();
		for (String line : Files.readAllLines(Path.of(listPath), StandardCharsets.UTF_8)) {
			if (line.isBlank() || line.stripLeading().startsWith("#")) {
				continue;
			}
			Path directory = Path.of(line.trim());
			if (!directory.isAbsolute() || !Files.isRegularFile(directory.resolve(".project"))) {
				throw new IllegalArgumentException("Expected an absolute project directory containing .project: " + directory);
			}
			IProjectDescription description = workspace.loadProjectDescription(
					org.eclipse.core.runtime.Path.fromOSString(directory.resolve(".project").toString()));
			description.setLocationURI(directory.toUri());
			IProject project = workspace.getRoot().getProject(description.getName());
			if (!project.exists()) {
				project.create(description, monitor);
			} else if (!directory.toUri().equals(project.getLocationURI())) {
				throw new IllegalArgumentException("Project already exists at another location: " + project.getName());
			}
			if (!project.isOpen()) {
				project.open(monitor);
			}
			imported.add(project.getName());
		}
		if (imported.isEmpty()) {
			throw new IllegalArgumentException("The project list is empty");
		}
		workspace.save(true, monitor);
		System.out.println("XML_STUDY_PREP " + Json.encode(Map.of("status", "ok", "projects", imported, "autoBuild", false)));
		return EXIT_OK;
	}

	@Override
	public void stop() {
	}
}
