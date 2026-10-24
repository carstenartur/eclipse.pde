package bench;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.BaselineXMLDefaultHandler;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;
import org.w3c.dom.Node;

/** Original versus proposed PDE handler, with identical parsing and JAR access. */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 4, time = 2)
@Measurement(iterations = 6, time = 1)
@Fork(value = 3, jvmArgsAppend = {"-Xms512m", "-Xmx512m", "-XX:+UseSerialGC", "-XX:ActiveProcessorCount=1"})
@Threads(1)
@State(Scope.Thread)
public class HandlerComparison {
    @Param({"abbreviated", "full"}) public String mode;
    private record Entry(byte[] bytes, URL url) {}
    private final List<List<Entry>> corpora = new ArrayList<>();
    private com.sun.management.ThreadMXBean threads;
    private long threadId;
    private int round;

    @Setup(Level.Trial) public void setup() throws Exception {
        Path root = Path.of(System.getProperty("corpus", "corpus")).toAbsolutePath();
        for (String variant : List.of("original", "compact")) {
            Path directory = root.resolve(variant);
            List<Entry> entries = new ArrayList<>();
            try (var files = Files.walk(directory)) {
                for (Path p : files.filter(f -> f.toString().endsWith(".exsd")).sorted().toList()) {
                    String name = directory.relativize(p).toString().replace('\\', '/');
                    URL url = URI.create("jar:" + root.resolve(variant + ".jar").toUri() + "!/" + name).toURL();
                    byte[] bytes = Files.readAllBytes(p);
                    if (!parse(new ByteArrayInputStream(bytes), false).isEqualNode(parse(new ByteArrayInputStream(bytes), true)))
                        throw new AssertionError("DOM differs: " + p);
                    entries.add(new Entry(bytes, url));
                }
            }
            if (entries.size() != 49) throw new AssertionError("Expected 49 schemas");
            corpora.add(entries);
        }
        System.out.println("Verified 98 exact DOM comparisons; mode=" + mode);
        threads = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        threads.setThreadCpuTimeEnabled(true);
        threads.setThreadAllocatedMemoryEnabled(true);
        threadId = Thread.currentThread().threadId();
    }

    private Node parse(InputStream stream, boolean patched) throws Exception {
        var parser = XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE();
        if (patched) {
            var handler = new XMLDefaultHandler(mode.equals("abbreviated"));
            parser.parse(stream, handler); return handler.getDocumentElement();
        }
        var handler = new BaselineXMLDefaultHandler(mode.equals("abbreviated"));
        parser.parse(stream, handler); return handler.getDocumentElement();
    }

    @State(Scope.Thread)
    @AuxCounters(AuxCounters.Type.EVENTS)
    public static class Counters {
        final long[] cpu = new long[4], bytes = new long[4], count = new long[4];
        @Setup(Level.Iteration) public void reset() { Arrays.fill(cpu, 0); Arrays.fill(bytes, 0); Arrays.fill(count, 0); }
        double c(int i) { return count[i] == 0 ? 0 : cpu[i] / 1_000_000.0 / count[i]; }
        double a(int i) { return count[i] == 0 ? 0 : (double) bytes[i] / count[i]; }
        public double baselineOriginalCpu() { return c(0); }
        public double baselineCompactCpu() { return c(1); }
        public double patchedOriginalCpu() { return c(2); }
        public double patchedCompactCpu() { return c(3); }
        public double baselineOriginalBytes() { return a(0); }
        public double baselineCompactBytes() { return a(1); }
        public double patchedOriginalBytes() { return a(2); }
        public double patchedCompactBytes() { return a(3); }
    }

    @Benchmark public void compare(Blackhole bh, Counters counters) throws Exception {
        int start = round % 4, direction = (round / 4) % 2 == 0 ? 1 : -1;
        round++;
        for (int position = 0; position < 4; position++) {
            int index = Math.floorMod(start + direction * position, 4);
            long cpu = threads.getCurrentThreadCpuTime(), bytes = threads.getThreadAllocatedBytes(threadId);
            for (Entry e : corpora.get(index % 2)) {
                JarURLConnection connection = (JarURLConnection) e.url().openConnection();
                connection.setUseCaches(false);
                try (InputStream stream = connection.getInputStream()) { bh.consume(parse(stream, index >= 2)); }
                finally { connection.getJarFile().close(); }
            }
            counters.bytes[index] += threads.getThreadAllocatedBytes(threadId) - bytes;
            counters.cpu[index] += threads.getCurrentThreadCpuTime() - cpu;
            counters.count[index]++;
        }
    }
}
