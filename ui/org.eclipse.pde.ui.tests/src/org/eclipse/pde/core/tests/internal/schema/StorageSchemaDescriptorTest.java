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

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.eclipse.core.resources.IStorage;
import org.eclipse.core.runtime.IPath;
import org.eclipse.core.runtime.PlatformObject;
import org.eclipse.pde.internal.core.ischema.ISchema;
import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.StorageSchemaDescriptor;
import org.junit.jupiter.api.Test;

public class StorageSchemaDescriptorTest {

	private static final String VALID_SCHEMA = """
			<schema>
			   <element name="extension">
			      <complexType>
			         <attribute name="point" type="string" use="required"/>
			      </complexType>
			   </element>
			</schema>
			""";

	@Test
	public void loadsSchemaFromOneClosedStorageStream() {
		CountingStorage storage = new CountingStorage(VALID_SCHEMA);
		StorageSchemaDescriptor descriptor = new StorageSchemaDescriptor(storage);

		Schema schema = (Schema) descriptor.getSchema(false);

		assertTrue(schema.isLoaded());
		assertNotNull(schema.findElement("extension"));
		assertSingleClosedStream(storage);
	}

	@Test
	public void closesSingleStorageStreamAfterParseFailure() {
		CountingStorage storage = new CountingStorage("<schema><element");
		StorageSchemaDescriptor descriptor = new StorageSchemaDescriptor(storage);

		Schema schema = (Schema) descriptor.getSchema(false);

		assertFalse(schema.isLoaded());
		assertSingleClosedStream(storage);
	}

	@Test
	public void cachedSchemaDoesNotReopenStorage() {
		CountingStorage storage = new CountingStorage(VALID_SCHEMA);
		StorageSchemaDescriptor descriptor = new StorageSchemaDescriptor(storage);
		ISchema first = descriptor.getSchema(false);
		int opensAfterLoading = storage.streams.size();

		assertSame(first, descriptor.getSchema(false));
		assertEquals(opensAfterLoading, storage.streams.size(), "A cached schema must not reopen its storage");
	}

	private static void assertSingleClosedStream(CountingStorage storage) {
		assertAll(
				() -> assertEquals(1, storage.streams.size(), "Loading a schema must open storage once"),
				() -> assertTrue(storage.streams.stream().allMatch(stream -> stream.closed),
						"Every opened storage stream must be closed after loading"));
	}

	private static class CountingStorage extends PlatformObject implements IStorage {
		private final byte[] contents;
		private final List<CloseTrackingInputStream> streams = new ArrayList<>();

		CountingStorage(String contents) {
			this.contents = contents.getBytes(StandardCharsets.UTF_8);
		}

		@Override
		public InputStream getContents() {
			CloseTrackingInputStream stream = new CloseTrackingInputStream(contents);
			streams.add(stream);
			return stream;
		}

		@Override
		public IPath getFullPath() {
			return IPath.fromPortableString("storage.exsd");
		}

		@Override
		public String getName() {
			return "storage.exsd";
		}

		@Override
		public boolean isReadOnly() {
			return true;
		}
	}

	private static class CloseTrackingInputStream extends ByteArrayInputStream {
		private boolean closed;

		CloseTrackingInputStream(byte[] contents) {
			super(contents);
		}

		@Override
		public void close() throws IOException {
			closed = true;
			super.close();
		}
	}
}
