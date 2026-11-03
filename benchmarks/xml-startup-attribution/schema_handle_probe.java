/*
 * Copyright (c) 2026 Contributors to the Eclipse Foundation.
 * SPDX-License-Identifier: EPL-2.0
 */
import com.sun.management.UnixOperatingSystemMXBean;
import java.io.InputStream;
import java.lang.management.ManagementFactory;
import java.net.URI;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.SchemaDescriptor;

/** Real file/JAR lifecycle probe; inputs are synthetic, not production defects. */
final class SchemaHandleProbe {
    private static final UnixOperatingSystemMXBean OS =
            (UnixOperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
    private static final String PROC_DIRECTORY = "/proc/" + ProcessHandle.current().pid() + "/fd";

    private record Snapshot(long mxbean, int procRaw, int probeDirectoryHandles,
            Map<String, Integer> fixtureTargets, Map<String, Integer> allTargets) {
        int fixtureCount() {
            return fixtureTargets.values().stream().mapToInt(Integer::intValue).sum();
        }

        Map<String, Object> asMap() {
            return Map.of("mxbean_open_fds", mxbean, "proc_raw_fds", procRaw,
                    "probe_directory_fds", probeDirectoryHandles,
                    "proc_fds_excluding_probe_directory", procRaw - probeDirectoryHandles,
                    "fixture_handle_count", fixtureCount(), "fixture_targets", fixtureTargets);
        }
    }

    private static Snapshot snapshot(Path fixtureDirectory) throws Exception {
        long total = OS.getOpenFileDescriptorCount();
        Map<String, Integer> fixtures = new TreeMap<>();
        Map<String, Integer> targets = new TreeMap<>();
        int raw = 0;
        int ownDirectory = 0;
        String prefix = fixtureDirectory.toString() + "/";
        try (var descriptors = Files.newDirectoryStream(Path.of("/proc/self/fd"))) {
            for (Path descriptor : descriptors) {
                String target;
                try {
                    target = Files.readSymbolicLink(descriptor).toString();
                } catch (java.nio.file.NoSuchFileException racedDescriptor) {
                    continue;
                }
                raw++;
                if (target.equals(PROC_DIRECTORY)) {
                    ownDirectory++;
                    continue;
                }
                targets.merge(target, 1, Integer::sum);
                if (target.startsWith(prefix)) {
                    fixtures.merge(target, 1, Integer::sum);
                }
            }
        }
        return new Snapshot(total, raw, ownDirectory, fixtures, targets);
    }

    private static Map<String, Integer> targetDelta(Snapshot baseline, Snapshot current) {
        Map<String, Integer> difference = new TreeMap<>(current.allTargets);
        baseline.allTargets.forEach((key, value) -> difference.merge(key, -value, Integer::sum));
        difference.entrySet().removeIf(entry -> entry.getValue() == 0);
        return difference;
    }

    private static void verifyState(Schema schema, boolean expectedLoaded) {
        if (schema.isLoaded() != expectedLoaded) {
            throw new AssertionError("Unexpected loaded state: " + schema.isLoaded());
        }
    }

    private static Map<String, Object> phase(URL url, Path fixtureDirectory, String mode,
            boolean abbreviated, boolean expectedLoaded, int warmup, int rounds, int operations)
            throws Exception {
        boolean fresh = mode.equals("new_descriptor_per_operation");
        Snapshot beforeWarmup = snapshot(fixtureDirectory);
        SchemaDescriptor cachedDescriptor = new SchemaDescriptor("fixture.point", url);
        Schema cachedSchema = (Schema) cachedDescriptor.getSchema(abbreviated);
        verifyState(cachedSchema, expectedLoaded);
        Snapshot afterInitialLoad = snapshot(fixtureDirectory);
        int maxFixture = afterInitialLoad.fixtureCount();
        int samples = 1;
        List<Map<String, Object>> measuredRounds = new ArrayList<>();
        Snapshot afterWarmup = null;
        for (int round = -1; round < rounds; round++) {
            int count = round == -1 ? warmup : operations;
            int roundMaxFixture = 0;
            for (int operation = 0; operation < count; operation++) {
                if (fresh) {
                    SchemaDescriptor descriptor = new SchemaDescriptor("fixture.point", url);
                    Schema schema = (Schema) descriptor.getSchema(abbreviated);
                    verifyState(schema, expectedLoaded);
                    if (descriptor.getSchema(abbreviated) != schema) {
                        throw new AssertionError("Fresh descriptor failed to retain its schema");
                    }
                } else {
                    if (cachedDescriptor.getSchema(abbreviated) != cachedSchema) {
                        throw new AssertionError("Cached descriptor replaced its schema");
                    }
                    switch (operation % 3) {
                        case 0 -> cachedSchema.findElement("root");
                        case 1 -> cachedSchema.getElements();
                        default -> cachedSchema.getResolvedElements();
                    }
                    verifyState(cachedSchema, expectedLoaded);
                }
                Snapshot sample = snapshot(fixtureDirectory);
                roundMaxFixture = Math.max(roundMaxFixture, sample.fixtureCount());
                samples++;
            }
            maxFixture = Math.max(maxFixture, roundMaxFixture);
            Snapshot end = snapshot(fixtureDirectory);
            if (round == -1) {
                afterWarmup = end;
            } else {
                Map<String, Object> observation = new LinkedHashMap<>();
                observation.put("round", round + 1);
                observation.put("operations", count);
                observation.put("max_fixture_handles_after_operation", roundMaxFixture);
                observation.put("end", end.asMap());
                observation.put("mxbean_delta_since_warmup", end.mxbean - afterWarmup.mxbean);
                observation.put("fd_target_delta_since_warmup", targetDelta(afterWarmup, end));
                measuredRounds.add(observation);
            }
        }
        // Retain the original descriptor throughout the measurement; no disposal
        // or forced GC is used to make the resource counts fall.
        if (cachedDescriptor.getSchema(abbreviated) != cachedSchema) {
            throw new AssertionError("Descriptor changed during measurement");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("before_warmup", beforeWarmup.asMap());
        result.put("after_initial_load", afterInitialLoad.asMap());
        result.put("after_warmup", afterWarmup.asMap());
        result.put("warmup_operations", warmup);
        result.put("rounds", measuredRounds);
        result.put("total_operations", warmup + rounds * operations);
        result.put("post_operation_samples", samples);
        result.put("max_fixture_handles_after_operation", maxFixture);
        result.put("schema_loaded", cachedSchema.isLoaded());
        result.put("fixture_handles_retained", maxFixture > 0);
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path backingFile = Path.of(args[0]).toRealPath();
        Path fixtureDirectory = backingFile.getParent();
        String protocol = args[1];
        String fixture = args[2];
        boolean expectedLoaded = Boolean.parseBoolean(args[3]);
        boolean abbreviated = Boolean.parseBoolean(args[4]);
        int warmup = Integer.parseInt(args[5]);
        int rounds = Integer.parseInt(args[6]);
        int operations = Integer.parseInt(args[7]);
        URL url = protocol.equals("file") ? backingFile.toUri().toURL()
                : URI.create("jar:" + backingFile.toUri().toASCIIString() + "!/schema/fixture.exsd").toURL();

        // Positive control: prove the /proc filter sees an actual open backing
        // file, then close it before observing any PDE loads.
        Snapshot positiveControl;
        try (InputStream control = Files.newInputStream(backingFile)) {
            control.read();
            positiveControl = snapshot(fixtureDirectory);
            control.read();
        }
        Snapshot afterControlClose = snapshot(fixtureDirectory);
        if (positiveControl.fixtureCount() < 1 || afterControlClose.fixtureCount() != 0) {
            throw new AssertionError("Open-handle positive control did not behave as expected");
        }

        List<Map<String, Object>> phases = new ArrayList<>();
        for (String mode : List.of("cached_descriptor_queries", "new_descriptor_per_operation")) {
            phases.add(phase(url, fixtureDirectory, mode, abbreviated, expectedLoaded,
                    warmup, rounds, operations));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("protocol", protocol);
        result.put("fixture", fixture);
        result.put("synthetic_input", true);
        result.put("abbreviated", abbreviated);
        result.put("expected_schema_loaded", expectedLoaded);
        result.put("positive_control_open", positiveControl.asMap());
        result.put("positive_control_closed", afterControlClose.asMap());
        result.put("forced_gc", false);
        result.put("fresh_jvm_for_case", true);
        result.put("phases", phases);
        boolean retained = phases.stream().anyMatch(value -> Boolean.TRUE.equals(value.get("fixture_handles_retained")));
        result.put("fixture_handles_retained", retained);
        System.out.println(json(result));
        if (retained) {
            System.exit(1);
        }
    }

    private static String json(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String text) {
            return "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"")
                    .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
        }
        if (value instanceof Map<?, ?> map) {
            List<String> fields = new ArrayList<>();
            map.forEach((key, item) -> fields.add(json(key.toString()) + ":" + json(item)));
            return "{" + String.join(",", fields) + "}";
        }
        if (value instanceof Iterable<?> items) {
            List<String> values = new ArrayList<>();
            items.forEach(item -> values.add(json(item)));
            return "[" + String.join(",", values) + "]";
        }
        return value.toString();
    }
}
