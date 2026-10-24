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
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.eclipse.pde.internal.core.schema.Schema;
import org.junit.jupiter.api.Test;

@SuppressWarnings("restriction")
public class SchemaDocumentationTest {

	@Test
	public void readsEmptyOverviewDocumentation() throws Exception {
		Schema schema = read("<schema><annotation><documentation/></annotation><element name='extension'/></schema>");

		assertTrue(schema.isLoaded());
		assertEquals("", schema.getDescription());
		assertEquals("extension", schema.getElementAt(0).getName());
	}

	@Test
	public void readsEmptyNamedDocumentationSection() throws Exception {
		Schema schema = read("<schema><annotation><appinfo><meta.section type='apiinfo'/></appinfo>"
				+ "<documentation></documentation></annotation><element name='extension'/></schema>");

		assertTrue(schema.isLoaded());
		assertEquals("", Arrays.stream(schema.getDocumentSections())
				.filter(section -> section.getSectionId().equals("apiinfo")).findFirst().orElseThrow().getDescription());
		assertEquals("extension", schema.getElementAt(0).getName());
	}

	@Test
	public void readsEmptyElementDocumentation() throws Exception {
		Schema schema = read("<schema><element name='extension'><annotation><documentation/>"
				+ "</annotation></element></schema>");

		assertTrue(schema.isLoaded());
		assertEquals("", schema.getElementAt(0).getDescription());
	}

	@Test
	public void keepsExistingDocumentationNormalization() throws Exception {
		Schema schema = read("<schema><annotation><documentation> \tOverview &amp; detail \n</documentation>"
				+ "</annotation><element name='extension'><annotation>"
				+ "<documentation> \tElement detail </documentation></annotation></element></schema>");

		assertEquals("Overview & detail", schema.getDescription());
		assertEquals("Element detail", schema.getElementAt(0).getDescription());
	}

	private static Schema read(String xml) throws Exception {
		XMLDefaultHandler handler = new XMLDefaultHandler();
		XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE()
				.parse(new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)), handler);
		Schema schema = new Schema("test", "point", "Test", false);
		// Exercise model traversal directly so an exception cannot be swallowed by load().
		schema.traverseDocumentTree(handler.getDocumentElement());
		return schema;
	}
}
