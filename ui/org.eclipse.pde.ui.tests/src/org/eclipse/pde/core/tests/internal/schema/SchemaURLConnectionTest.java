/*******************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation.
 *
 * This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License 2.0
 * which accompanies this distribution, and is available at
 * https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *******************************************************************************/
package org.eclipse.pde.core.tests.internal.schema;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.JarURLConnection;
import java.net.URI;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;

import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.util.SchemaUtil;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.xml.sax.Attributes;
import org.xml.sax.helpers.DefaultHandler;

public class SchemaURLConnectionTest {

	private static final String SCHEMA = "<schema><element name=\"extension\"/></schema>";
	private Path archive;
	private TrackingConnection connection;

	@BeforeEach
	public void createArchive() throws IOException {
		archive = Files.createTempFile("pde-schema-", ".jar");
		writeEntry("schema.exsd", SCHEMA);
	}

	@AfterEach
	public void deleteArchive() throws IOException {
		Files.deleteIfExists(archive);
	}

	@Test
	public void missingSchemaEntryDoesNotReconnectDuringCleanup() throws Exception {
		for (boolean abbreviated : new boolean[] { false, true }) {
			Schema schema = new Schema(null, trackedURL("missing.exsd"), abbreviated);
			schema.load();

			assertFalse(schema.isLoaded());
			assertEquals(1, connection.streamRequests);
			assertEquals(0, connection.jarRequests, "Cleanup must not reconnect after a missing entry");
		}
	}

	@Test
	public void missingAnnotationEntryDoesNotReconnectDuringCleanup() throws Exception {
		SchemaUtil.parseURL(trackedURL("missing.exsd"), new DefaultHandler());

		assertEquals(1, connection.streamRequests);
		assertEquals(0, connection.jarRequests, "Cleanup must not reconnect after a missing entry");
	}

	@Test
	public void successfulSchemaLoadClosesStreamAndJar() throws Exception {
		for (boolean abbreviated : new boolean[] { false, true }) {
			Schema schema = new Schema(null, trackedURL("schema.exsd"), abbreviated);
			schema.load();

			assertTrue(schema.isLoaded());
			assertNotNull(schema.findElement("extension"));
			assertResourcesClosed();
		}
	}

	@Test
	public void malformedSchemaClosesStreamAndJar() throws Exception {
		writeEntry("schema.exsd", "<schema><element");
		for (boolean abbreviated : new boolean[] { false, true }) {
			Schema schema = new Schema(null, trackedURL("schema.exsd"), abbreviated);
			schema.load();

			assertFalse(schema.isLoaded());
			assertResourcesClosed();
		}
	}

	@Test
	public void successfulAnnotationParseClosesStreamAndJar() throws Exception {
		StringBuilder elements = new StringBuilder();
		SchemaUtil.parseURL(trackedURL("schema.exsd"), new DefaultHandler() {
			@Override
			public void startElement(String uri, String localName, String qName, Attributes attributes) {
				elements.append(qName).append(' ');
			}
		});

		assertEquals("schema element ", elements.toString());
		assertResourcesClosed();
	}

	@Test
	public void malformedAnnotationParseClosesStreamAndJar() throws Exception {
		writeEntry("schema.exsd", "<schema><element");
		SchemaUtil.parseURL(trackedURL("schema.exsd"), new DefaultHandler());

		assertResourcesClosed();
	}

	@Test
	public void missingSchemaCanLoadAfterResourceIsCreated() throws Exception {
		Schema schema = new Schema(null, trackedURL("later.exsd"), false);
		schema.load();
		assertFalse(schema.isLoaded());

		writeEntry("later.exsd", SCHEMA);
		schema.load();

		assertTrue(schema.isLoaded());
		assertNotNull(schema.findElement("extension"));
		assertResourcesClosed();
	}

	private void assertResourcesClosed() {
		assertFalse(connection.getUseCaches());
		assertTrue(connection.streamClosed, "The entry stream must be closed");
		assertNotNull(connection.openedJar);
		assertThrows(IllegalStateException.class, () -> connection.openedJar.getJarEntry("schema.exsd"),
				"The JAR must be closed too");
	}

	private void writeEntry(String name, String contents) throws IOException {
		try (JarOutputStream output = new JarOutputStream(Files.newOutputStream(archive))) {
			output.putNextEntry(new JarEntry(name));
			output.write(contents.getBytes(StandardCharsets.UTF_8));
			output.closeEntry();
		}
	}

	@SuppressWarnings("deprecation") // A per-URL handler observes a real JDK JAR connection.
	private URL trackedURL(String entry) throws Exception {
		URL actual = URI.create("jar:" + archive.toUri() + "!/" + entry).toURL();
		return new URL(null, actual.toExternalForm(), new URLStreamHandler() {
			@Override
			protected URLConnection openConnection(URL url) throws IOException {
				connection = new TrackingConnection(actual);
				return connection;
			}
		});
	}

	private static class TrackingConnection extends JarURLConnection {
		private final JarURLConnection delegate;
		private int streamRequests;
		private int jarRequests;
		private boolean streamClosed;
		private JarFile openedJar;

		TrackingConnection(URL url) throws IOException {
			super(url);
			delegate = (JarURLConnection) url.openConnection();
		}

		@Override
		public void setUseCaches(boolean useCaches) {
			super.setUseCaches(useCaches);
			delegate.setUseCaches(useCaches);
		}

		@Override
		public void connect() throws IOException {
			delegate.connect();
		}

		@Override
		public InputStream getInputStream() throws IOException {
			streamRequests++;
			InputStream input = delegate.getInputStream();
			openedJar = delegate.getJarFile();
			return new FilterInputStream(input) {
				@Override
				public void close() throws IOException {
					try {
						super.close();
					} finally {
						streamClosed = true;
					}
				}
			};
		}

		@Override
		public JarFile getJarFile() throws IOException {
			jarRequests++;
			return delegate.getJarFile();
		}
	}
}
