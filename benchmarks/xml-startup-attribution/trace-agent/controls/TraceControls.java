import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.zip.*;
import javax.xml.parsers.*;
import org.xml.sax.*;
import org.xml.sax.helpers.DefaultHandler;

/** Executable real-parser controls. Runs identically with and without the agent. */
public final class TraceControls {
    private static final byte[] XML = "<?xml version=\"1.0\"?><plugin><extension point=\"control\"/></plugin>".getBytes(StandardCharsets.UTF_8);
    private static void phase(String name) throws Exception {
        System.setProperty("xml.trace.phase", name);
        try {
            Class.forName("org.eclipse.pde.xmlstudy.trace.bootstrap.TraceBridge", true, null)
                .getMethod("phase", String.class).invoke(null, name);
        } catch (ClassNotFoundException ignored) { }
    }
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]);
        Files.createDirectories(root);
        Path jar = root.resolve("controls.jar");
        try (ZipOutputStream out = new ZipOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new ZipEntry("plugin.xml")); out.write(XML); out.closeEntry();
            out.putNextEntry(new ZipEntry("model.xmi")); out.write(XML); out.closeEntry();
        }
        URL plugin = URI.create("jar:" + jar.toUri() + "!/plugin.xml").toURL();
        phase("control_sax_jar");
        try (InputStream in = plugin.openConnection().getInputStream()) {
            InputSource input = new InputSource(in); input.setSystemId(plugin.toString());
            SAXParserFactory.newInstance().newSAXParser().parse(input, new DefaultHandler());
        }
        phase("control_dom_jar");
        DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(plugin.toString());
        phase("control_direct_zip");
        try (ZipFile zip = new ZipFile(jar.toFile()); InputStream in = zip.getInputStream(zip.getEntry("plugin.xml"))) {
            if (in.readAllBytes().length != XML.length) throw new AssertionError("ZIP bytes differ");
        }
        phase("control_missing_jar");
        try {
            URI.create("jar:" + jar.toUri() + "!/missing.exsd").toURL().openConnection().getInputStream();
            throw new AssertionError("Missing JAR entry unexpectedly opened");
        } catch (FileNotFoundException expected) { }
        phase("control_missing_file");
        try {
            Files.newInputStream(root.resolve("missing.xml"));
            throw new AssertionError("Missing file unexpectedly opened");
        } catch (NoSuchFileException expected) { }
        phase("control_missing_file_constructor");
        try {
            new FileInputStream(root.resolve("missing-constructor.xml").toFile());
            throw new AssertionError("Missing constructor file unexpectedly opened");
        } catch (FileNotFoundException expected) { }
        phase("control_malformed");
        try {
            SAXParserFactory.newInstance().newSAXParser().parse(new InputSource(new StringReader("<broken>")), new DefaultHandler());
            throw new AssertionError("Malformed XML unexpectedly parsed");
        } catch (SAXParseException expected) { }
        phase("control_worker");
        java.util.concurrent.atomic.AtomicReference<Throwable> failure = new java.util.concurrent.atomic.AtomicReference<>();
        Thread worker = new Thread(() -> {
            try { DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(new ByteArrayInputStream(XML)); }
            catch (Throwable e) { failure.set(e); }
        }, "XML positive-control worker");
        worker.start(); worker.join();
        if (failure.get() != null) throw new AssertionError(failure.get());
        phase("controls_complete");
        System.out.println("CONTROL_OK xmlBytes=" + XML.length + " cases=8");
    }
}
