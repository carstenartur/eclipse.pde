import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Map;
import org.eclipse.core.runtime.IExtensionRegistry;
import org.eclipse.core.runtime.RegistryFactory;
import org.eclipse.core.runtime.ContributorFactorySimple;
import org.eclipse.core.runtime.ICoreRunnable;
import org.eclipse.core.runtime.spi.RegistryStrategy;
import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EcorePackage;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceImpl;
import org.eclipse.pde.internal.core.schema.Schema;

/** Real Eclipse APIs from a pinned installation, running outside the workbench. */
public final class EclipseTraceControls {
    private static void phase(String name) throws Exception {
        Class.forName("org.eclipse.pde.xmlstudy.trace.bootstrap.TraceBridge",true,null)
            .getMethod("phase",String.class).invoke(null,name);
    }
    public static void main(String[] args) throws Exception {
        Path root=Path.of(args[0]); Files.createDirectories(root);
        phase("control_registry");
        Object master=new Object();
        IExtensionRegistry registry=RegistryFactory.createRegistry(new RegistryStrategy(null,null),master,null);
        String plugin="<plugin><extension-point id=\"point\" name=\"Control\"/><extension point=\"xml.trace.point\"><item/></extension></plugin>";
        boolean added=registry.addContribution(new ByteArrayInputStream(plugin.getBytes(StandardCharsets.UTF_8)),
                ContributorFactorySimple.createContributor("xml.trace"),false,"plugin.xml",null,master);
        if (!added || registry.getExtensionPoint("xml.trace.point")==null) throw new AssertionError("Registry control failed");
        registry.stop(master);
        phase("control_emf");
        EcorePackage.eINSTANCE.eClass();
        XMIResourceImpl resource=new XMIResourceImpl(URI.createURI("memory:/control.xmi"));
        String xmi="<ecore:EClass xmi:version=\"2.0\" xmlns:xmi=\"http://www.omg.org/XMI\" xmlns:ecore=\"http://www.eclipse.org/emf/2002/Ecore\" name=\"Control\"/>";
        resource.load(new ByteArrayInputStream(xmi.getBytes(StandardCharsets.UTF_8)),Map.of());
        if (resource.getContents().size()!=1) throw new AssertionError("EMF control failed");
        phase("control_pde_schema");
        Path schemaFile=root.resolve("control.exsd");
        Files.writeString(schemaFile,"<?xml version=\"1.0\"?><schema targetNamespace=\"xml.trace\" xmlns=\"http://www.w3.org/2001/XMLSchema\"><annotation><appinfo><meta.schema plugin=\"xml.trace\" id=\"point\" name=\"Control\"/></appinfo></annotation><element name=\"extension\"><complexType/></element></schema>");
        Schema schema=new Schema(null,schemaFile.toUri().toURL(),false); schema.load();
        if (!schema.isLoaded() || schema.getElementCount()!=1) throw new AssertionError("PDE schema control failed");
        phase("control_pde_schema_missing_jar");
        Path emptyJar=root.resolve("schema-control.jar");
        try (java.util.jar.JarOutputStream out=new java.util.jar.JarOutputStream(Files.newOutputStream(emptyJar))) {
            out.putNextEntry(new java.util.zip.ZipEntry("present.xml")); out.write("<root/>".getBytes(StandardCharsets.UTF_8)); out.closeEntry();
        }
        Schema missing=new Schema(null,java.net.URI.create("jar:"+emptyJar.toUri()+"!/missing.exsd").toURL(),false);
        missing.load();
        if (missing.isLoaded()) throw new AssertionError("Missing JAR schema was incorrectly loaded");
        phase("control_early_job");
        Job job=Job.create("XML pre-probe positive-control job",(ICoreRunnable) monitor -> { });
        job.schedule(); job.join();
        if (!job.getResult().isOK()) throw new AssertionError("Job control failed");
        phase("eclipse_controls_complete");
        System.out.println("ECLIPSE_CONTROL_OK registry=true emfObjects="+resource.getContents().size()+" schemaElements="+schema.getElementCount()+" earlyJob=true missingJarSchemaLoaded=false");
    }
}
