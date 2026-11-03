package org.eclipse.pde.xmlstudy.probe;

import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Map;

/** Observe a deliberately opened real file and confirm it disappears on close. */
public final class FdDiagnosticsTest {

	public static void main(String[] args) throws Exception {
		if (!Boolean.TRUE.equals(FdDiagnostics.snapshot().get("supported"))) {
			System.out.println("FdDiagnosticsTest: skipped; /proc/self/fd unavailable");
			return;
		}
		Path path = Files.createTempFile("xml-study-fd-test-", ".jar");
		try {
			Map<String, Object> opened;
			try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
				if (!channel.isOpen()) {
					throw new AssertionError("Test file channel did not open");
				}
				opened = FdDiagnostics.snapshot();
				if (!containsTarget(opened, path.toString(), "jar")) {
					throw new AssertionError("An open .jar file descriptor was omitted or misclassified");
				}
				if (containsTarget(opened, Path.of("/proc/self/fd").toRealPath().toString(), null)) {
					throw new AssertionError("The scanner included its own directory descriptors");
				}
			}
			if (containsTarget(FdDiagnostics.snapshot(), path.toString(), null)) {
				throw new AssertionError("The descriptor remained after its channel closed");
			}
			System.out.println("FdDiagnosticsTest: 3 real-descriptor checks passed");
		} finally {
			Files.deleteIfExists(path);
		}
	}

	private static boolean containsTarget(Map<String, Object> snapshot, String target, String kind) {
		for (Object value : (List<?>) snapshot.get("descriptors")) {
			Map<?, ?> descriptor = (Map<?, ?>) value;
			if (target.equals(descriptor.get("target")) && (kind == null || kind.equals(descriptor.get("kind")))) {
				return true;
			}
		}
		return false;
	}
}
