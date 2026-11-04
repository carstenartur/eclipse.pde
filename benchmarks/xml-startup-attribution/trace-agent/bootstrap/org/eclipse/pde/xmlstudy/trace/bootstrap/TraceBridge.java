package org.eclipse.pde.xmlstudy.trace.bootstrap;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Method;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.*;

/** Bootstrap-visible diagnostic sink. Calls never change an application's outcome. */
public final class TraceBridge {
    private static final long START = System.nanoTime();
    private static final long UPTIME_AT_START = ManagementFactory.getRuntimeMXBean().getUptime();
    private static final AtomicLong IDS = new AtomicLong();
    private static final ThreadLocal<Boolean> BUSY = ThreadLocal.withInitial(() -> false);
    private static final ThreadLocal<ArrayDeque<Long>> PARENTS = ThreadLocal.withInitial(ArrayDeque::new);
    private static final Map<Long, Span> SPANS = new ConcurrentHashMap<>();
    private static final Map<Long, TrackedInput> STREAMS = new ConcurrentHashMap<>();
    private static volatile PrintWriter output;
    private static volatile String currentPhase = "before_probe";
    private static volatile long dropped;
    private static volatile long emitted;
    private static volatile boolean broken;
    private static final long LIMIT = Long.getLong("xml.trace.maxEvents", 1_000_000L);

    private record Span(long id, long parent, String operation, String method, String source,
            String phase, long started, Map<String, Object> details) { }

    private TraceBridge() { }

    public static void initialize(String filename) throws IOException {
        Path path = Path.of(filename).toAbsolutePath();
        Files.createDirectories(path.getParent());
        output = new PrintWriter(new BufferedWriter(new OutputStreamWriter(
                Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE), StandardCharsets.UTF_8)));
        // Load every helper path before bootstrap classes are transformed.
        new TrackedInput(InputStream.nullInputStream(), new Span(-1, 0, "warmup", "", "", "", 0, Map.of()));
        json(Map.of("escape", "\n\t\"\\", "values", List.of(1, true, "ok")));
        Runtime.getRuntime().addShutdownHook(new Thread(TraceBridge::shutdown, "XML trace shutdown"));
        emit("agent_started", Map.of("formatVersion", 1, "javaVersion", System.getProperty("java.version"),
                "pid", ProcessHandle.current().pid(), "phaseOrigin", "premain", "maxEvents", LIMIT,
                "measurement", "diagnostic; instrumentation affects timing"));
    }

    public static void instrumentation(String className, List<String> methods) {
        emit("instrumented", Map.of("class", className, "methods", methods));
    }

    public static void instrumentationError(String className, Throwable failure) {
        emit("instrumentation_error", Map.of("class", className, "error", failure.toString()));
    }

    public static void phase(String phase) {
        try {
            String previous = currentPhase;
            currentPhase = phase;
            System.setProperty("xml.trace.phase", phase);
            emit("phase", Map.of("previousPhase", previous));
        } catch (Throwable failure) { traceError(failure); }
    }

    public static void job(String event, Object[] args) {
        if (Boolean.TRUE.equals(BUSY.get())) return;
        BUSY.set(true);
        try {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("event", event);
            for (Object arg : args) {
                if (arg == null) continue;
                Object job = call(arg, "getJob");
                if (job == null && arg.getClass().getName().contains("Job")) job = arg;
                if (job != null) {
                    data.put("jobClass", job.getClass().getName());
                    data.put("jobIdentity", Integer.toHexString(System.identityHashCode(job)));
                    data.put("jobName", text(call(job, "getName")));
                    Object status = call(arg, "getResult");
                    if (status != null) data.put("result", text(status));
                }
            }
            data.put("caller", callers());
            emit("job", data);
        } catch (Throwable failure) { traceError(failure); }
        finally { BUSY.set(false); }
    }

    public static long enter(String operation, String method, Object receiver, Object[] args) {
        if (Boolean.TRUE.equals(BUSY.get()) || output == null || broken) return 0;
        BUSY.set(true);
        try {
            Map<String, Object> details = new LinkedHashMap<>();
            String source = source(receiver, args, details);
            if (operation.equals("registry_start") && args.length > 1 && args[1] instanceof Boolean) details.put("loadedFromCache", args[1]);
            if (operation.endsWith("_builder") && args.length > 0) {
                details.put("buildKind", args[0]);
                Object project=call(receiver,"getProject");
                if (project!=null) details.put("project", text(call(project,"getName")));
            }
            boolean io = operation.equals("resource_open") || operation.equals("zip_entry_open") || operation.equals("resource_lookup") || operation.equals("file_open");
            if (io && (source.endsWith(".class") || (!looksXml(source) && !inParser()))) return 0;
            if (io) details.put("resourceAttribution", looksXml(source) ? "xml_suffix" : "inside_parser_or_loader");
            if (operation.equals("file_open")) details.put("bytesMeasured", false);
            long id = IDS.incrementAndGet();
            long parent = PARENTS.get().isEmpty() ? 0 : PARENTS.get().peek();
            Span span = new Span(id, parent, operation, method, source, phaseName(), System.nanoTime(), details);
            SPANS.put(id, span);
            PARENTS.get().push(id);
            Map<String, Object> data = spanData(span);
            data.put("caller", callers());
            emit("begin", data);
            return id;
        } catch (Throwable failure) { traceError(failure); return 0; }
        finally { BUSY.set(false); }
    }

    public static InputStream opened(long id, InputStream result) {
        if (id == 0) return result;
        try {
            Span span = SPANS.get(id);
            if (span == null) return result;
            if (result instanceof TrackedInput tracked) {
                finish(id, "returned", Map.of("streamAliasOf", tracked.span.id()));
                return result;
            }
            if (result == null) {
                finish(id, "missing", Map.of());
                return null;
            }
            TrackedInput tracked = new TrackedInput(result, span);
            STREAMS.put(id, tracked);
            finish(id, "returned", Map.of("streamIdentity", Integer.toHexString(System.identityHashCode(result))));
            return tracked;
        } catch (Throwable failure) { traceError(failure); return result; }
    }

    public static void returned(long id, Object result) {
        if (id == 0) return;
        try {
            Span span = SPANS.get(id);
            if (span == null) return;
            Map<String, Object> extra = new LinkedHashMap<>();
            if (result instanceof Boolean || result instanceof Number || result instanceof String) extra.put("result", result);
            String outcome = span.operation.equals("resource_lookup") && result == null ? "missing" : "returned";
            finish(id, outcome, extra);
        } catch (Throwable failure) { traceError(failure); }
    }

    public static void failed(long id, Throwable failure) {
        if (id == 0) return;
        try { finish(id, "threw", Map.of("exception", failure.getClass().getName(), "error", text(failure.getMessage()))); }
        catch (Throwable nested) { traceError(nested); }
    }

    private static void finish(long id, String outcome, Map<String, Object> extra) {
        Span span = SPANS.remove(id);
        if (span == null) return;
        ArrayDeque<Long> parents = PARENTS.get();
        if (!parents.isEmpty() && parents.peek() == id) parents.pop();
        else parents.remove(id);
        Map<String, Object> data = spanData(span);
        data.putAll(extra);
        data.put("outcome", outcome);
        data.put("durationNs", System.nanoTime() - span.started());
        data.put("endPhase", phaseName());
        emit("end", data);
    }

    private static Map<String, Object> spanData(Span span) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", span.id()); data.put("parent", span.parent());
        data.put("operation", span.operation()); data.put("method", span.method());
        data.put("source", span.source()); data.put("phase", span.phase());
        data.putAll(span.details());
        return data;
    }

    private static String source(Object receiver, Object[] args, Map<String, Object> details) {
        if (receiver instanceof URLConnection connection) return connection.getURL().toString();
        if (receiver instanceof URL url) return url.toString();
        if (receiver instanceof ZipFile zip && args.length > 0) {
            Object entry = args[0];
            if (entry instanceof ZipEntry z) {
                details.put("entrySize", z.getSize()); details.put("entryCompressedSize", z.getCompressedSize());
                details.put("entryCompressionMethod", z.getMethod());
                return zip.getName() + "!/" + z.getName();
            }
            return zip.getName() + "!/" + text(entry);
        }
        for (Object arg : args) {
            if (arg instanceof Path || arg instanceof File || arg instanceof URL || arg instanceof URI) return arg.toString();
            if (arg instanceof String value && (looksXml(value) || value.startsWith("file:") || value.startsWith("jar:"))) return value;
            if (arg instanceof TrackedInput input) return input.span.source();
            if (arg != null && arg.getClass().getName().equals("org.xml.sax.InputSource")) {
                Object system = call(arg, "getSystemId");
                if (system != null) return system.toString();
                Object stream = call(arg, "getByteStream");
                if (stream instanceof TrackedInput input) return input.span.source();
                details.put("inputKind", stream == null ? "character_or_system_input" : "anonymous_byte_stream");
            }
        }
        if (receiver != null) {
            for (String accessor : new String[]{"getURL", "getURI", "getName"}) {
                Object value = call(receiver, accessor);
                if (value != null && !value.toString().isEmpty()) return value.toString();
            }
        }
        return "<unresolved>";
    }

    private static Object call(Object receiver, String method) {
        try {
            Method m = receiver.getClass().getMethod(method);
            if (!m.canAccess(receiver) && !m.trySetAccessible()) return null;
            return m.invoke(receiver);
        } catch (ReflectiveOperationException | RuntimeException ignored) { return null; }
    }

    private static boolean looksXml(String value) {
        String lower = value.toLowerCase(Locale.ROOT);
        int end = lower.indexOf('?'); if (end >= 0) lower = lower.substring(0, end);
        end = lower.indexOf('#'); if (end >= 0) lower = lower.substring(0, end);
        return lower.endsWith(".xml") || lower.endsWith(".xmi") || lower.endsWith(".exsd")
                || lower.endsWith(".mxsd") || lower.endsWith(".xsd") || lower.endsWith(".dtd");
    }

    private static boolean inParser() {
        for (long id : PARENTS.get()) {
            Span s = SPANS.get(id);
            if (s != null && (s.operation().contains("parse") || s.operation().contains("load"))) return true;
        }
        return false;
    }

    private static List<String> callers() {
        List<String> frames = new ArrayList<>();
        for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
            String name = frame.getClassName();
            if (name.equals(Thread.class.getName()) || name.startsWith(TraceBridge.class.getPackageName())) continue;
            frames.add(frame.toString());
            if (frames.size() == 18) break;
        }
        return frames;
    }

    private static String phaseName() { return System.getProperty("xml.trace.phase", currentPhase); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }

    private static synchronized void emit(String kind, Map<String, ?> values) {
        if (output == null || broken) return;
        if (emitted >= LIMIT && !kind.equals("agent_summary")) { dropped++; return; }
        try {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("kind", kind);
            data.put("elapsedNs", System.nanoTime() - START);
            data.put("jvmUptimeMs", UPTIME_AT_START + (System.nanoTime() - START) / 1_000_000);
            data.put("phase", phaseName());
            data.put("thread", Thread.currentThread().getName());
            data.put("threadId", Thread.currentThread().getId());
            data.putAll(values);
            output.println(json(data)); output.flush(); emitted++;
            if (output.checkError()) throw new IOException("XML trace output failed");
        } catch (Throwable failure) { broken = true; System.err.println("XML_TRACE_OUTPUT_ERROR " + failure); }
    }

    private static void traceError(Throwable failure) {
        emit("trace_error", Map.of("error", failure.toString()));
    }

    private static void shutdown() {
        BUSY.set(true);
        for (TrackedInput stream : List.copyOf(STREAMS.values())) stream.report("shutdown_unclosed");
        for (Span span : List.copyOf(SPANS.values())) {
            Map<String, Object> data = spanData(span); data.put("outcome", "incomplete_at_shutdown");
            emit("incomplete", data);
        }
        emit("agent_summary", Map.of("eventsBeforeSummary", emitted, "droppedEvents", dropped,
                "inFlightSpans", SPANS.size(), "outputFailed", broken));
        if (output != null) output.close();
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) {
            StringJoiner join = new StringJoiner(",", "{", "}");
            map.forEach((k,v) -> join.add(json(k.toString()) + ":" + json(v))); return join.toString();
        }
        if (value instanceof Iterable<?> list) {
            StringJoiner join = new StringJoiner(",", "[", "]");
            for (Object item : list) join.add(json(item)); return join.toString();
        }
        String s = value.toString(); StringBuilder out = new StringBuilder("\"");
        for (int i=0; i<s.length(); i++) {
            char c=s.charAt(i);
            if (c=='"' || c=='\\') out.append('\\').append(c);
            else if (c < 32) out.append(String.format("\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }

    private static final class TrackedInput extends FilterInputStream {
        private final Span span;
        private long bytes, skipped;
        private boolean eof, reported;
        private final Map<String, Long> phaseBytes = new LinkedHashMap<>();
        private TrackedInput(InputStream stream, Span span) { super(stream); this.span=span; }
        private synchronized void count(long count) {
            if (count < 0) eof=true;
            else if (count > 0) { bytes += count; phaseBytes.merge(phaseName(), count, Long::sum); }
        }
        @Override public int read() throws IOException { int v=in.read(); count(v < 0 ? -1 : 1); return v; }
        @Override public int read(byte[] data, int offset, int length) throws IOException {
            int v=in.read(data,offset,length); count(v); return v;
        }
        @Override public int read(byte[] data) throws IOException { return read(data,0,data.length); }
        @Override public long skip(long count) throws IOException { long v=in.skip(count); synchronized(this){skipped+=v;} return v; }
        @Override public void close() throws IOException { try { in.close(); } finally { report("close"); } }
        private synchronized void report(String reason) {
            if (reported) return;
            reported=true;
            Map<String,Object> data=spanData(span);
            data.put("bytesRead",bytes); data.put("bytesSkipped",skipped); data.put("reachedEof",eof);
            data.put("termination",reason); data.put("bytesByPhase",new LinkedHashMap<>(phaseBytes));
            data.put("byteMeaning","uncompressed bytes delivered by this stream layer; repeated reads count again");
            emit("stream",data); STREAMS.remove(span.id());
        }
    }
}
