package org.eclipse.pde.xmlstudy.probe;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/** Optional Linux descriptor diagnostics. Does not open or read target files. */
final class FdDiagnostics {

	private FdDiagnostics() {
	}

	static Map<String, Object> snapshot() {
		long startNanos = System.nanoTime();
		long startUptime = ManagementFactory.getRuntimeMXBean().getUptime();
		long pid = ProcessHandle.current().pid();
		Path directory = Path.of("/proc/self/fd");
		if (!Files.isDirectory(directory)) {
			return Map.of("supported", false, "reason", "/proc/self/fd is unavailable", "processId", pid);
		}
		List<Map<String, Object>> descriptors = new ArrayList<>();
		Map<String, List<Integer>> jars = new TreeMap<>();
		Map<String, List<Integer>> regularFiles = new TreeMap<>();
		Map<String, Integer> kinds = new TreeMap<>();
		int ownDirectoryDescriptors = 0;
		int racedOrInaccessible = 0;
		// The DirectoryStream is closed before returning and before stdout/file output.
		try (DirectoryStream<Path> entries = Files.newDirectoryStream(directory)) {
			// A mounted /proc can expose a different PID namespace from ProcessHandle.
			String ownDirectoryTarget = directory.toRealPath().toString();
			for (Path entry : entries) {
				int fd;
				try {
					fd = Integer.parseInt(entry.getFileName().toString());
				} catch (NumberFormatException ignored) {
					continue;
				}
				try {
					String target = Files.readSymbolicLink(entry).toString();
					if (target.equals(ownDirectoryTarget) || target.equals("/proc/self/fd")) {
						ownDirectoryDescriptors++;
						continue;
					}
					String kind = kind(entry, target);
					descriptors.add(Map.of("fd", fd, "target", target, "kind", kind));
					kinds.merge(kind, 1, Integer::sum);
					if ("jar".equals(kind)) {
						jars.computeIfAbsent(target, key -> new ArrayList<>()).add(fd);
					} else if ("regular_file".equals(kind)) {
						regularFiles.computeIfAbsent(target, key -> new ArrayList<>()).add(fd);
					}
				} catch (IOException | SecurityException ignored) {
					// Other JVM threads may open/close descriptors during this non-atomic scan.
					racedOrInaccessible++;
				}
			}
		} catch (IOException | SecurityException failure) {
			return Map.of("supported", false, "reason", failure.toString(), "processId", pid);
		}
		descriptors.sort(Comparator.comparingInt(item -> (Integer) item.get("fd")));
		Map<String, Object> result = new LinkedHashMap<>();
		result.put("supported", true);
		result.put("processId", pid);
		result.put("captureStartJvmUptimeMs", startUptime);
		result.put("captureEndJvmUptimeMs", ManagementFactory.getRuntimeMXBean().getUptime());
		result.put("scanDurationNs", System.nanoTime() - startNanos);
		result.put("descriptorsObserved", descriptors.size());
		result.put("excludedProcDirectoryDescriptors", ownDirectoryDescriptors);
		result.put("racedOrInaccessibleEntries", racedOrInaccessible);
		result.put("countsByKind", kinds);
		result.put("uniqueJarTargets", jars.size());
		result.put("uniqueRegularFileTargets", regularFiles.size());
		result.put("jarTargets", grouped(jars));
		result.put("regularFileTargets", grouped(regularFiles));
		result.put("descriptors", descriptors);
		result.put("interpretation", "non-atomic open descriptor snapshot; retained JAR handles alone do not establish a leak");
		return result;
	}

	private static List<Map<String, Object>> grouped(Map<String, List<Integer>> targets) {
		List<Map<String, Object>> groups = new ArrayList<>();
		for (var entry : targets.entrySet()) {
			entry.getValue().sort(Integer::compareTo);
			groups.add(Map.of("target", entry.getKey(), "fds", entry.getValue(), "descriptorCount", entry.getValue().size()));
		}
		return groups;
	}

	private static String kind(Path entry, String target) {
		if (target.startsWith("socket:")) {
			return "socket";
		}
		if (target.startsWith("pipe:")) {
			return "pipe";
		}
		if (target.startsWith("anon_inode:")) {
			return "anonymous_inode";
		}
		if (Files.isRegularFile(entry)) {
			String name = target.endsWith(" (deleted)") ? target.substring(0, target.length() - " (deleted)".length()) : target;
			return name.toLowerCase(Locale.ROOT).endsWith(".jar") ? "jar" : "regular_file";
		}
		return Files.isDirectory(entry) ? "directory" : "device_or_other";
	}
}
