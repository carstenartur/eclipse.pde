package org.eclipse.pde.xmlstudy.instances;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.JarURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.jar.JarFile;

import org.eclipse.pde.internal.core.PDECore;
import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.SchemaDescriptor;
import org.eclipse.pde.internal.core.schema.SchemaRegistry;

/** Counts actual input-stream attempts while preserving the real URL connection's behavior. */
final class RepeatedLoadProbe {

	private RepeatedLoadProbe() {
	}

	static Map<String, Object> run() throws Exception {
		List<Map<String, Object>> cases = new ArrayList<>();
		for (String point : List.of("org.eclipse.equinox.p2.repository.tools.verifier",
				"org.eclipse.ui.externaltools.configurationDuplicationMaps", "org.eclipse.core.runtime.applications")) {
			var declaration = PDECore.getDefault().getExtensionsRegistry().findExtensionPoint(point);
			if (declaration == null) {
				throw new IllegalStateException("Production diagnostic point unavailable: " + point);
			}
			URL original = SchemaRegistry.getSchemaURL(declaration);
			if (original == null) {
				throw new IllegalStateException("Production diagnostic URL unavailable: " + point);
			}
			for (boolean abbreviated : List.of(false, true)) {
				Counter counter = new Counter();
				// The legacy constructor permits a per-URL file handler; URL.of forbids it.
				// This diagnostic preserves the original protocol and delegates real I/O unchanged.
				@SuppressWarnings("deprecation")
				URL observed = new URL(null, original.toExternalForm(), new URLStreamHandler() {
					@Override
					protected URLConnection openConnection(URL ignored) throws IOException {
						counter.connectionAttempts++;
						URLConnection delegate = original.openConnection();
						return delegate instanceof JarURLConnection jar ? new ObservedJarConnection(original, jar, counter)
								: new ObservedConnection(original, delegate, counter);
					}
				});
				Path target = handleTarget(original);
				int handlesBefore = handles(target);
				SchemaDescriptor descriptor = new SchemaDescriptor(point, observed);
				Schema schema = (Schema) descriptor.getSchema(abbreviated);
				boolean loadedInitially = schema.isLoaded();
				int afterInitial = counter.streamAttempts;
				for (int i = 0; i < 24; i++) {
					switch (i % 3) {
						case 0 -> schema.findElement("extension");
						case 1 -> schema.getElements();
						default -> schema.getResolvedElements();
					}
				}
				Map<String, Object> result = new LinkedHashMap<>();
				result.put("point", point);
				result.put("sourceUrl", original.toExternalForm());
				result.put("abbreviated", abbreviated);
				result.put("subsequentQueries", 24);
				result.put("sameModelRetained", schema == descriptor.getSchema(abbreviated));
				result.put("loadedAfterInitial", loadedInitially);
				result.put("loadedAfterQueries", schema.isLoaded());
				result.put("validAfterQueries", schema.isValid());
				result.put("streamAttemptsAfterInitial", afterInitial);
				result.put("streamAttemptsAfterQueries", counter.streamAttempts);
				result.put("successfulInputStreams", counter.successfulStreams);
				result.put("closedSuccessfulStreams", counter.closedStreams);
				result.put("connectionAttempts", counter.connectionAttempts);
				result.put("streamExceptions", counter.exceptions);
				result.put("jarUseCachesValues", counter.jarUseCaches);
				result.put("fileHandleTarget", target == null ? null : target.toString());
				result.put("targetHandlesBefore", handlesBefore);
				result.put("targetHandlesAfter", handles(target));
				result.put("handlePositiveControl", handlePositiveControl(target));
				cases.add(result);
			}
		}
		return Map.of("method", "Actual SDK SchemaDescriptor/Schema and real registry URLs; transparent counting URLConnection preserves JarURLConnection identity, cache settings and getJarFile close path. Same model reused for 24 subsequent queries; no forced GC.",
				"scope", "Separate diagnostic after instance validation; counts getInputStream attempts, not startup time or all registry activity.",
				"cases", cases);
	}

	private static Path handleTarget(URL original) throws Exception {
		if ("file".equals(original.getProtocol())) {
			return Path.of(original.toURI()).toRealPath();
		}
		if ("jar".equals(original.getProtocol())) {
			URLConnection connection = original.openConnection();
			URL archive = ((JarURLConnection) connection).getJarFileURL();
			if ("file".equals(archive.getProtocol())) {
				return Path.of(archive.toURI()).toRealPath();
			}
		}
		return null;
	}

	private static int handles(Path target) throws IOException {
		Path directory = Path.of("/proc/self/fd");
		if (target == null || !Files.isDirectory(directory)) {
			return -1;
		}
		int count = 0;
		try (var entries = Files.list(directory)) {
			for (Path entry : entries.toList()) {
				try {
					Path actual = Files.readSymbolicLink(entry);
					if (actual.isAbsolute() && actual.toRealPath().equals(target)) {
						count++;
					}
				} catch (IOException ignored) {
					// Descriptor may have closed, or name may be a socket/pipe rather than a path.
				}
			}
		}
		return count;
	}

	private static Map<String, Object> handlePositiveControl(Path target) throws IOException {
		int before = handles(target);
		if (before < 0) {
			return Map.of("supported", false);
		}
		int whileOpen;
		try (InputStream held = Files.newInputStream(target)) {
			whileOpen = handles(target);
			held.read();
		}
		int afterClose = handles(target);
		if (whileOpen != before + 1 || afterClose != before) {
			throw new IllegalStateException("Target FD positive control failed: " + target + ": "
					+ before + " -> " + whileOpen + " -> " + afterClose);
		}
		return Map.of("supported", true, "before", before, "whileOpen", whileOpen, "afterClose", afterClose,
				"passed", true);
	}

	private static final class Counter {
		int connectionAttempts;
		int streamAttempts;
		int successfulStreams;
		int closedStreams;
		final List<Map<String, String>> exceptions = new ArrayList<>();
		final List<Boolean> jarUseCaches = new ArrayList<>();

		InputStream open(URLConnection connection) throws IOException {
			streamAttempts++;
			if (connection instanceof JarURLConnection) {
				jarUseCaches.add(connection.getUseCaches());
			}
			try {
				InputStream stream = connection.getInputStream();
				successfulStreams++;
				return new FilterInputStream(stream) {
					private boolean closed;
					@Override
					public void close() throws IOException {
						if (!closed) {
							closed = true;
							closedStreams++;
						}
						super.close();
					}
				};
			} catch (IOException failure) {
				exceptions.add(Map.of("type", failure.getClass().getName(), "message", String.valueOf(failure.getMessage())));
				throw failure;
			}
		}
	}

	private static final class ObservedConnection extends URLConnection {
		private final URLConnection delegate;
		private final Counter counter;
		ObservedConnection(URL url, URLConnection delegate, Counter counter) {
			super(url);
			this.delegate = delegate;
			this.counter = counter;
		}
		@Override
		public void connect() throws IOException {
			delegate.connect();
			connected = true;
		}
		@Override
		public InputStream getInputStream() throws IOException {
			return counter.open(delegate);
		}
		@Override
		public void setUseCaches(boolean value) {
			super.setUseCaches(value);
			delegate.setUseCaches(value);
		}
	}

	private static final class ObservedJarConnection extends JarURLConnection {
		private final JarURLConnection delegate;
		private final Counter counter;
		ObservedJarConnection(URL url, JarURLConnection delegate, Counter counter) throws IOException {
			super(url);
			this.delegate = delegate;
			this.counter = counter;
		}
		@Override
		public void connect() throws IOException {
			delegate.connect();
			connected = true;
		}
		@Override
		public InputStream getInputStream() throws IOException {
			return counter.open(delegate);
		}
		@Override
		public JarFile getJarFile() throws IOException {
			return delegate.getJarFile();
		}
		@Override
		public void setUseCaches(boolean value) {
			super.setUseCaches(value);
			delegate.setUseCaches(value);
		}
	}
}
