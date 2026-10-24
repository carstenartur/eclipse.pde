/*******************************************************************************
 * Copyright (c) 2026 Carsten Hammer and others.
 *
 * This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License 2.0
 * which accompanies this distribution, and is available at
 * https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *******************************************************************************/
package org.eclipse.pde.core.tests.internal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import javax.xml.parsers.SAXParser;

import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.schema.SchemaReader;
import org.junit.jupiter.api.Test;
import org.w3c.dom.Node;
import org.xml.sax.SAXException;
import org.xml.sax.SAXNotRecognizedException;
import org.xml.sax.SAXNotSupportedException;
import org.xml.sax.XMLReader;

@SuppressWarnings("restriction")
public class SchemaReaderTest {

	@Test
	public void reusesParserWithoutSharingDocumentsOrMode() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = reader(created);
		Node first = reader.read(xml("<first>before<child/> after</first>"), false);
		Node second = reader.read(xml("<second a='value'>ignored<child/>ignored</second>"), true);
		Node third = reader.read(xml("<third>text</third>"), false);

		assertEquals(1, created.get());
		assertEquals("before after", first.getTextContent());
		assertEquals("second", second.getNodeName());
		assertEquals("value", second.getAttributes().getNamedItem("a").getNodeValue());
		assertEquals(1, second.getChildNodes().getLength());
		assertEquals("", second.getTextContent());
		assertEquals("text", third.getTextContent());
		assertNotSame(first.getOwnerDocument(), second.getOwnerDocument());
	}

	@Test
	public void releasesDocumentHandlersBeforeCachingParser() throws Exception {
		SAXParser parser = XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE();
		SchemaReader reader = new SchemaReader(() -> parser);
		reader.read(xml("<root/>"), false);

		assertNull(parser.getXMLReader().getContentHandler());
		assertNull(parser.getXMLReader().getDTDHandler());
		assertNull(parser.getXMLReader().getEntityResolver());
		assertNull(parser.getXMLReader().getErrorHandler());
	}

	@Test
	public void retiresParserStateAcrossRepeatedSchemaReads() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = reader(created);
		for (int i = 0; i < 256; i++) {
			String name = "element" + i;
			assertEquals(name, reader.read(xml("<" + name + "/>"), false).getNodeName());
		}
		// reset() need not clear provider state such as interned XML names. Retire
		// parsers periodically, while still amortizing their construction cost.
		assertTrue(created.get() > 1);
		assertTrue(created.get() < 256);
	}

	@Test
	public void rejectsDoctypeAfterReuseAndDiscardsFailedParser() throws Exception {
		for (String rejected : new String[] { "<root>", "<!DOCTYPE root><root/>",
				"<!DOCTYPE root [<!ENTITY e 'expanded'>]><root>&e;</root>",
				"<!DOCTYPE root SYSTEM 'file:///does-not-exist.dtd'><root/>" }) {
			AtomicInteger created = new AtomicInteger();
			SchemaReader reader = reader(created);
			reader.read(xml("<before/>"), false);
			reader.read(xml("<reuse/>"), true);

			assertThrows(SAXException.class, () -> reader.read(xml(rejected), false));
			assertEquals("after", reader.read(xml("<after/>"), false).getNodeName());
			assertEquals(2, created.get());
		}
	}

	@Test
	public void discardsParserAfterInputFailure() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = reader(created);
		reader.read(xml("<before/>"), false);
		InputStream failing = new InputStream() {
			@Override
			public int read() throws IOException {
				throw new IOException("Input failed");
			}
		};

		assertThrows(IOException.class, () -> reader.read(failing, false));
		assertEquals("after", reader.read(xml("<after/>"), false).getNodeName());
		assertEquals(2, created.get());
	}

	@Test
	public void concurrentReadsUseSeparateParsersAndKeepOnlyOneIdle() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = reader(created);
		for (int round = 0; round < 2; round++) {
			CountDownLatch reading = new CountDownLatch(2);
			Runnable overlap = () -> {
				reading.countDown();
				try {
					if (!reading.await(10, TimeUnit.SECONDS)) {
						throw new AssertionError("Reads did not overlap");
					}
				} catch (InterruptedException e) {
					Thread.currentThread().interrupt();
					throw new AssertionError(e);
				}
			};
			try (var executor = Executors.newFixedThreadPool(2)) {
				var first = executor.submit(() -> reader.read(onFirstRead("<first>A</first>", overlap), false));
				var second = executor.submit(() -> reader.read(onFirstRead("<second>B</second>", overlap), false));
				assertEquals("A", first.get(15, TimeUnit.SECONDS).getTextContent());
				assertEquals("B", second.get(15, TimeUnit.SECONDS).getTextContent());
			}
			assertEquals(2 + round, created.get());
		}
		reader.read(xml("<next/>"), false);
		assertEquals(3, created.get());
	}

	@Test
	@SuppressWarnings("deprecation")
	public void doesNotCacheParsersThatCannotBeReset() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = new SchemaReader(() -> {
			created.incrementAndGet();
			SAXParser delegate = XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE();
			return new SAXParser() {
				@Override
				public org.xml.sax.Parser getParser() throws SAXException {
					return delegate.getParser();
				}

				@Override
				public XMLReader getXMLReader() throws SAXException {
					return delegate.getXMLReader();
				}

				@Override
				public boolean isNamespaceAware() {
					return delegate.isNamespaceAware();
				}

				@Override
				public boolean isValidating() {
					return delegate.isValidating();
				}

				@Override
				public void setProperty(String name, Object value)
						throws SAXNotRecognizedException, SAXNotSupportedException {
					delegate.setProperty(name, value);
				}

				@Override
				public Object getProperty(String name) throws SAXNotRecognizedException, SAXNotSupportedException {
					return delegate.getProperty(name);
				}
			}; // SAXParser's default reset() throws UnsupportedOperationException.
		});

		assertEquals("first", reader.read(xml("<first/>"), false).getNodeName());
		assertEquals("second", reader.read(xml("<second/>"), false).getNodeName());
		assertEquals(2, created.get());
	}

	@Test
	public void nestedReadDoesNotReuseActiveParser() throws Exception {
		AtomicInteger created = new AtomicInteger();
		SchemaReader reader = reader(created);
		AtomicReference<Node> nested = new AtomicReference<>();
		Node outer = reader.read(onFirstRead("<outer>A</outer>", () -> {
			try {
				nested.set(reader.read(xml("<inner>B</inner>"), false));
			} catch (Exception e) {
				throw new AssertionError(e);
			}
		}), false);

		assertEquals("A", outer.getTextContent());
		assertEquals("B", nested.get().getTextContent());
		assertEquals(2, created.get());
		reader.read(xml("<next/>"), false);
		assertEquals(2, created.get());
	}

	private static SchemaReader reader(AtomicInteger created) {
		return new SchemaReader(() -> {
			created.incrementAndGet();
			return XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE();
		});
	}

	private static InputStream xml(String content) {
		return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
	}

	private static InputStream onFirstRead(String content, Runnable action) {
		return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8)) {
			private boolean first = true;

			private void beforeRead() {
				if (first) {
					first = false;
					action.run();
				}
			}

			@Override
			public int read() {
				beforeRead();
				return super.read();
			}

			@Override
			public int read(byte[] bytes, int offset, int length) {
				beforeRead();
				return super.read(bytes, offset, length);
			}
		};
	}
}
