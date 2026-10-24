package bench;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.TimeUnit;

import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.SchemaDescriptor;
import org.eclipse.pde.internal.core.schema.SchemaProvider;
import org.eclipse.pde.internal.core.ischema.ISchema;
import org.eclipse.pde.internal.core.ischema.ISchemaDescriptor;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

/** Measurement-only client of the real Schema.load and SchemaDescriptor paths. */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 8, time = 2)
@Measurement(iterations = 6, time = 1)
@Fork(value = 3, jvmArgsAppend = {"-Xms512m", "-Xmx512m", "-XX:+UseSerialGC", "-XX:ActiveProcessorCount=1"})
@Threads(1)
@State(Scope.Thread)
public class SchemaLoadBenchmark {
    @Param({"original"}) public String variant;
    private List<URL> urls;
    private IncludeProvider includes;
    private com.sun.management.ThreadMXBean threads;
    private long threadId;

    static Path evaluation() { return Path.of(System.getProperty("evaluation")).toAbsolutePath(); }
    static Path corpus() { return Path.of(System.getProperty("corpus")).toAbsolutePath(); }

    /** Resolve the workbench corpus's real include files without an IDE target platform. */
    static final class IncludeProvider implements SchemaProvider {
        int loads;
        @Override public ISchema createSchema(ISchemaDescriptor descriptor, String location) {
            try {
                URL url;
                if (location.startsWith("schema://org.eclipse.core.expressions/")) {
                    url = evaluation().resolve("corpus-includes/" + location.substring("schema://org.eclipse.core.expressions/".length())).toUri().toURL();
                } else {
                    url = new URL(descriptor.getSchemaURL(), location);
                }
                loads++;
                Schema result = (Schema) new SchemaDescriptor(null, url, this).getSchema(false);
                if (!result.isLoaded()) throw new AssertionError("Include not loaded: " + url);
                return result;
            } catch (IOException e) { throw new UncheckedIOException(e); }
        }
    }

    static List<URL> urls(String variant) throws IOException {
        List<URL> urls = new ArrayList<>();
        Path directory = corpus().resolve(variant);
        try (var files = Files.walk(directory)) {
            for (Path file : files.filter(p -> p.toString().endsWith(".exsd")).sorted().toList()) {
                String name = directory.relativize(file).toString().replace('\\', '/');
                urls.add(URI.create("jar:" + corpus().resolve(variant + ".jar").toUri() + "!/" + name).toURL());
            }
        }
        if (urls.size() != 49) throw new AssertionError("Expected 49 schemas, got " + urls.size());
        return urls;
    }

    @Setup(Level.Trial) public void setup() throws Exception {
        urls = urls(variant);
        includes = new IncludeProvider();
        threads = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        threads.setThreadCpuTimeEnabled(true);
        threads.setThreadAllocatedMemoryEnabled(true);
        threadId = Thread.currentThread().threadId();
        // Trial setup checks are outside the measured operation.
        for (URL url : urls) requireLoaded(load(url, includes));
    }

    static Schema load(URL url, IncludeProvider includes) {
        return (Schema) new SchemaDescriptor(null, url, includes).getSchema(false);
    }

    static void requireLoaded(Schema schema) {
        if (!schema.isLoaded() || schema.getElementCount() == 0) {
            throw new AssertionError("Model not loaded: " + schema.getURL());
        }
    }

    @State(Scope.Thread)
    @AuxCounters(AuxCounters.Type.EVENTS)
    public static class Counters {
        long cpu, bytes, count;
        @Setup(Level.Iteration) public void reset() { cpu = bytes = count = 0; }
        public double cpuMs() { return count == 0 ? 0 : cpu / 1_000_000.0 / count; }
        public double allocatedBytes() { return count == 0 ? 0 : (double) bytes / count; }
    }

    @Benchmark public void loadSchemas(Blackhole bh, Counters counters) {
        long cpu = threads.getCurrentThreadCpuTime(), bytes = threads.getThreadAllocatedBytes(threadId);
        for (URL url : urls) bh.consume(load(url, includes));
        counters.cpu += threads.getCurrentThreadCpuTime() - cpu;
        counters.bytes += threads.getThreadAllocatedBytes(threadId) - bytes;
        counters.count++;
    }

    static Schema fixture(String xml) {
        Schema schema = new Schema("test", "point", "Test", false);
        schema.load(new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)));
        return schema;
    }

    static void validate(String... variants) throws Exception {
        String body = "<schema><annotation><appinfo><meta.schema plugin='test' id='point' name='Test'/></appinfo>"
                + "<documentation> leading<![CDATA[ <raw>]]>&amp;middle<!--comment-->tail </documentation></annotation>"
                + "<element name='extension'><complexType><attribute name='id' type='string' use='required'/></complexType></element></schema>";
        Schema fixture = fixture(body);
        if (!fixture.isLoaded() || !fixture.isValid() || !"leading <raw>&middletail".equals(fixture.getDescription())
                || fixture.getElementCount() != 1 || fixture.findElement("extension").getAttributes().length != 1)
            throw new AssertionError("Literal schema model fixture changed");
        String[] prohibited = {"<!DOCTYPE schema>", "<!DOCTYPE schema [<!ENTITY e 'value'>]>",
                "<!DOCTYPE schema SYSTEM 'file:///intentionally-missing.dtd'>",
                "<!DOCTYPE schema SYSTEM 'http://127.0.0.1:9/intentionally-missing.dtd'>",
                "<!DOCTYPE schema [<!ENTITY % e SYSTEM 'file:///intentionally-missing.dtd'>%e;]>"};
        for (String prefix : prohibited) {
            if (fixture(prefix + body).isLoaded()) throw new AssertionError("DOCTYPE accepted: " + prefix);
            if (!fixture(body).isLoaded()) throw new AssertionError("Valid load failed after rejected DOCTYPE");
        }
        if (fixture("<schema><element></schema>").isLoaded()) throw new AssertionError("Malformed XML accepted");
        for (String variant : List.of(variants)) {
            IncludeProvider includes = new IncludeProvider();
            int elementCount = 0;
            for (URL url : urls(variant)) {
                Schema schema = load(url, includes);
                requireLoaded(schema);
                elementCount += schema.getElementCount();
                // Serialization needs a target version, but the read path does not.
                // Fix it only after loading, outside every measured section.
                var field = Schema.class.getDeclaredField("fTargetVersion");
                field.setAccessible(true);
                field.setDouble(schema, 3.4);
                StringWriter text = new StringWriter();
                schema.write("", new PrintWriter(text));
                byte[] hash = MessageDigest.getInstance("SHA-256").digest(text.toString().getBytes(StandardCharsets.UTF_8));
                System.out.println("MODEL " + variant + " " + url.toString().substring(url.toString().lastIndexOf('/') + 1) + " " + HexFormat.of().formatHex(hash));
            }
            System.out.println("CHECKED " + variant + " schemas=49 elements=" + elementCount + " additionalIncludeLoads=" + includes.loads);
        }
        System.out.println("VALIDATED literal model, five DOCTYPE rejection/recovery pairs, malformed XML");
    }

    static void first(String variant, String file) throws Exception {
        // Prepare only URLs and metrics. No Schema or XML parser is used before timing.
        List<URL> entries = urls(variant);
        if (!file.equals("all")) entries = entries.stream().filter(u -> u.toString().endsWith("/" + file)).toList();
        if (entries.isEmpty()) throw new AssertionError(file);
        IncludeProvider includes = new IncludeProvider();
        var metrics = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        metrics.setThreadCpuTimeEnabled(true);
        metrics.setThreadAllocatedMemoryEnabled(true);
        var classes = ManagementFactory.getClassLoadingMXBean();
        long thread = Thread.currentThread().threadId();
        long beforeClasses = classes.getTotalLoadedClassCount();
        long cpu = metrics.getCurrentThreadCpuTime(), bytes = metrics.getThreadAllocatedBytes(thread), wall = System.nanoTime();
        List<Schema> models = new ArrayList<>();
        for (URL url : entries) models.add(load(url, includes));
        wall = System.nanoTime() - wall;
        bytes = metrics.getThreadAllocatedBytes(thread) - bytes;
        cpu = metrics.getCurrentThreadCpuTime() - cpu;
        long loadedClasses = classes.getTotalLoadedClassCount() - beforeClasses;
        int elements = 0;
        for (Schema schema : models) { requireLoaded(schema); elements += schema.getElementCount(); }
        System.out.printf(Locale.ROOT, "FIRST,%s,%s,%.6f,%.6f,%d,%d,%d,%d,%d%n", variant, file,
                wall / 1e6, cpu / 1e6, bytes, loadedClasses, models.size(), includes.loads, elements);
    }

    public static void main(String[] args) throws Exception {
        if (args[0].equals("validate")) validate(args.length > 1 ? Arrays.copyOfRange(args, 1, args.length) : new String[]{"original"});
        else if (args[0].equals("first")) first(args[1], args[2]);
        else throw new IllegalArgumentException(Arrays.toString(args));
    }
}
