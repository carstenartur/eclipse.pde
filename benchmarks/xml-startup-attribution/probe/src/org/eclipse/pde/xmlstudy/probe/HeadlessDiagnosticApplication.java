package org.eclipse.pde.xmlstudy.probe;

import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import org.eclipse.core.resources.*;
import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.equinox.app.*;
import org.eclipse.pde.internal.core.plugin.WorkspaceExtensionsModel;
import org.eclipse.pde.internal.core.schema.Schema;

/** Attribution workload inside real Equinox. Its boundaries are never GUI readiness. */
public final class HeadlessDiagnosticApplication implements IApplication {
    public static void phase(String name) throws Exception {
        Class<?> bridge=Class.forName("org.eclipse.pde.xmlstudy.trace.bootstrap.TraceBridge",true,null);
        Method phase=bridge.getMethod("phase",String.class); phase.invoke(null,name);
    }
    @Override public Object start(IApplicationContext context) throws Exception {
        phase("headless_application_entered");
        Path projectDirectory=Path.of(System.getProperty("xml.trace.fixture"));
        IWorkspace workspace=ResourcesPlugin.getWorkspace();
        IWorkspaceDescription settings=workspace.getDescription();
        settings.setAutoBuilding(false); workspace.setDescription(settings);
        NullProgressMonitor monitor=new NullProgressMonitor();
        for (String name : java.util.List.of(DiagnosticScenarios.PROVIDER, DiagnosticScenarios.CONSUMER)) {
            Path location=projectDirectory.getParent().resolve(name);
            IProjectDescription description=workspace.loadProjectDescription(org.eclipse.core.runtime.Path.fromOSString(location.resolve(".project").toString()));
            description.setLocationURI(location.toUri());
            IProject imported=workspace.getRoot().getProject(description.getName());
            if (!imported.exists()) imported.create(description,monitor);
            if (!imported.isOpen()) imported.open(monitor);
        }
        IProject project=workspace.getRoot().getProject(DiagnosticScenarios.PROVIDER);
        phase("explicit_pde_model_load_started");
        WorkspaceExtensionsModel model=new WorkspaceExtensionsModel(project.getFile("plugin.xml"));
        try (java.io.InputStream stream=project.getFile("plugin.xml").getContents()) { model.load(stream,false); }
        String schemaVersion=((org.eclipse.pde.internal.core.plugin.AbstractExtensions)model.getExtensions()).getSchemaVersion();
        if (!model.isLoaded() || !"3.4".equals(schemaVersion)) throw new AssertionError("Abbreviated PDE model did not retain the fixture schema version");
        phase("explicit_pde_schema_load_started");
        Schema schema=new Schema(null,projectDirectory.resolve("schema/control.exsd").toUri().toURL(),false);
        schema.load();
        if (!schema.isLoaded() || schema.getElementCount()!=2) throw new AssertionError("Fixture schema failed to load");
        phase("explicit_pde_loads_finished");
        Map<String,Object> automaticBuild=Map.of();
        if (Boolean.getBoolean("xml.trace.autoBuild")) {
            automaticBuild=DiagnosticScenarios.automaticBuild((name,details) -> {
                try { phase(name); } catch (Exception failure) { throw new IllegalStateException(failure); }
                System.out.println("XML_HEADLESS_BUILD_PHASE "+Json.encode(Map.of("phase",name,"details",details)));
            });
        }
        long deadline=System.nanoTime()+30_000_000_000L,quietSince=0;
        boolean settled=false;
        while (System.nanoTime()<deadline) {
            boolean blocking=false;
            for (Job job:Job.getJobManager().find(null)) {
                if (job.getState()==Job.RUNNING || job.getState()==Job.WAITING) { blocking=true; break; }
            }
            long now=System.nanoTime();
            if (blocking) quietSince=0;
            else if (quietSince==0) quietSince=now;
            else if (now-quietSince>=1_000_000_000L) { settled=true; break; }
            Thread.sleep(100);
        }
        phase("headless_workspace_save_started");
        workspace.save(true,monitor);
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("status",settled?"ok":"timeout"); result.put("measurement","headless diagnostic; no workbench created");
        result.put("autoBuild",workspace.getDescription().isAutoBuilding()); result.put("automaticBuild",automaticBuild);
        result.put("fixtureProjects",java.util.List.of(DiagnosticScenarios.PROVIDER,DiagnosticScenarios.CONSUMER)); result.put("fixturePluginSchemaVersion",schemaVersion); result.put("pdeModelMode","abbreviated header load");
        result.put("fixtureSchemaElements",schema.getElementCount()); result.put("settled",settled);
        result.put("quietWindowMs",1000); result.put("javaVersion",System.getProperty("java.version"));
        Path output=Path.of(System.getProperty("xml.study.output"));
        Files.createDirectories(output.toAbsolutePath().getParent()); Files.writeString(output,Json.encode(result)+"\n");
        phase(settled?"headless_background_settled":"headless_background_timeout");
        System.out.println("XML_HEADLESS_RESULT "+Json.encode(result));
        return settled?EXIT_OK:Integer.valueOf(2);
    }
    @Override public void stop() { }
}
