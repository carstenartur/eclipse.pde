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
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

import org.eclipse.pde.internal.core.ischema.ISchemaAttribute;
import org.eclipse.pde.internal.core.ischema.ISchemaComplexType;
import org.eclipse.pde.internal.core.ischema.ISchemaCompositor;
import org.eclipse.pde.internal.core.ischema.ISchemaRepeatable;
import org.eclipse.pde.internal.core.schema.Schema;
import org.junit.jupiter.api.Test;

public class SchemaWriterTest {

	private static final String INPUT = """
			<schema targetNamespace="test.plugin">
			  <annotation><appinfo><meta.schema plugin="test.plugin" id="point" name="Point"/></appinfo>
			    <documentation>Overview  text</documentation></annotation>
			  <element name="extension"><complexType><sequence>
			    <element ref="child" minOccurs="0" maxOccurs="unbounded"/>
			  </sequence><attribute name="point" type="string" use="required"/></complexType></element>
			  <element name="child"><annotation><documentation>&lt;pre&gt;first  second
			    third&lt;/pre&gt;</documentation></annotation><complexType>
			    <attribute name="pattern" type="string" use="default" value="a  b"/>
			  </complexType></element>
			</schema>
			""";

	@Test
	public void usesTabsForStructuralIndentation() {
		String output = write(load(INPUT, 3.4));

		assertTrue(output.contains("\t<element name=\"extension\">"));
		assertTrue(output.contains("\t\t<complexType>"));
		assertTrue(output.contains("\t\t\t<sequence>"));
		assertFalse(output.lines().anyMatch(line -> line.matches(" +<.*")),
				"The writer must not restore spaces used only for XML indentation");
	}

	@Test
	public void roundTripPreservesSchemaAndDocumentationForBothTargetVersions() {
		for (double targetVersion : new double[] { 3.3, 3.4 }) {
			String output = write(load(INPUT, targetVersion));
			Schema reloaded = load(output, targetVersion);

			assertEquals("test.plugin.point", reloaded.getQualifiedPointId());
			assertEquals("Overview  text", reloaded.getDescription());
			assertEquals("<pre>first  second\n    third</pre>", reloaded.findElement("child").getDescription());
			ISchemaAttribute attribute = reloaded.findElement("child").getAttribute("pattern");
			assertEquals(ISchemaAttribute.DEFAULT, attribute.getUse());
			assertEquals("a  b", attribute.getValue());
			var compositor = ((ISchemaComplexType) reloaded.findElement("extension").getType()).getCompositor();
			assertEquals(ISchemaCompositor.SEQUENCE, compositor.getKind());
			var child = (ISchemaRepeatable) compositor.getChildren()[0];
			assertEquals(0, child.getMinOccurs());
			assertEquals(Integer.MAX_VALUE, child.getMaxOccurs());
			assertTrue(output.contains(targetVersion >= 3.4 ? "<appinfo>" : "<appInfo>"));
			assertEquals(output, write(reloaded));
		}
	}

	private static Schema load(String contents, double targetVersion) {
		Schema schema = new Schema(null, null, false) {
			@Override
			public double getSchemaVersion() {
				return targetVersion;
			}
		};
		schema.load(new ByteArrayInputStream(contents.getBytes(StandardCharsets.UTF_8)));
		assertTrue(schema.isLoaded());
		return schema;
	}

	private static String write(Schema schema) {
		StringWriter output = new StringWriter();
		try (PrintWriter writer = new PrintWriter(output)) {
			schema.write("", writer);
		}
		return output.toString();
	}
}
