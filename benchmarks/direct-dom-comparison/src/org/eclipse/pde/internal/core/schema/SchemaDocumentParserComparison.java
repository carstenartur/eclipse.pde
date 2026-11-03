/*
 * Copyright (c) 2026 Carsten Hammer and others.
 *
 * This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License 2.0
 * which accompanies this distribution, and is available at
 * https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *******************************************************************************/
package org.eclipse.pde.internal.core.schema;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.w3c.dom.Element;
import org.w3c.dom.NamedNodeMap;
import org.w3c.dom.Node;
import org.xml.sax.SAXException;

/** Standalone compatibility checks using the production Platform factory. */
@SuppressWarnings("restriction")
public class SchemaDocumentParserComparison {

	private static int checks;

	public static void main(String[] args) throws Exception {
		List<String> fixtures = List.of(
				"<root>before<child attr='a &amp; b'>inside<![CDATA[ <raw>]]>&amp;</child>between<empty/>after</root>",
				"<root xml:space='preserve'> \t<child/> \n</root>",
				"<?pde version='3.8'?><!--copyright--><root>before<!--comment-->after</root><!--tail-->",
				"<?before data?><root>before<?nested data?>after<child>a<?inner?>b</child>end</root><?tail?>",
				"<schema xmlns='http://www.w3.org/2001/XMLSchema' xmlns:p='urn:p' p:a='v'><p:child/></schema>",
				"<p:root p:a='v'>unbound qualified names</p:root>",
				"<root a='&#x1F600; &quot; &apos;'>a&#x1F600;é\r\n<![CDATA[<raw>]]>&lt;&gt;&amp;</root>",
				"<root>" + "ab\uD83D\uDE00 &amp;&lt;&gt;\n".repeat(10_000) + "</root>",
				"<root/>");
		for (String xml : fixtures) {
			for (boolean abbreviated : new boolean[] { false, true }) {
				compare(xml.getBytes(StandardCharsets.UTF_8), abbreviated);
			}
		}

		Element root = candidate(bytes("<root>before<!--comment--><![CDATA[<raw>]]><?pi?>after</root>"), false);
		check(root.getChildNodes().getLength() == 1, "comments, CDATA and PIs must leave one text node");
		check("before<raw>after".equals(root.getFirstChild().getNodeValue()), "literal mixed text");
		check(root.getFirstChild().getNodeType() == Node.TEXT_NODE, "CDATA must be ordinary text");
		check(root.getNamespaceURI() == null && root.getLocalName() == null, "namespace-unaware DOM");
		Element abbreviated = candidate(bytes("<root a='v'>before<child b='x'>inside</child>after</root>"), true);
		check(abbreviated.getChildNodes().getLength() == 1, "abbreviated root has only child element");
		check(abbreviated.getFirstChild().getChildNodes().getLength() == 0, "abbreviated child has no text");
		check("v".equals(abbreviated.getAttribute("a")), "abbreviated attribute retained");
		Element platformDefault = XmlProcessorFactory.createDocumentBuilderWithErrorOnDOCTYPE()
				.parse(new ByteArrayInputStream(bytes("<root><!--kept--><![CDATA[kept]]></root>"))).getDocumentElement();
		check(platformDefault.getFirstChild().getNodeType() == Node.COMMENT_NODE, "Platform factory comments unchanged");
		check(platformDefault.getLastChild().getNodeType() == Node.CDATA_SECTION_NODE, "Platform factory CDATA unchanged");
		try (var executor = Executors.newFixedThreadPool(4)) {
			Callable<String> parse = () -> candidate(bytes("<root>before<![CDATA[<raw>]]><?pi?>after</root>"), false)
					.getTextContent();
			for (var result : executor.invokeAll(java.util.Collections.nCopies(40, parse))) {
				check("before<raw>after".equals(result.get()), "independent concurrent document builders");
			}
		}

		for (String xml : List.of("<root>", "<root>&undefined;</root>",
				"<!DOCTYPE root><root/>",
				"<!DOCTYPE root [<!ENTITY x 'internal'>]><root>&x;</root>",
				"<!DOCTYPE root SYSTEM 'file:/definitely-not-present/pde-test.dtd'><root/>",
				"<!DOCTYPE root [<!ENTITY x SYSTEM 'http://127.0.0.1:1/never-fetch'>]><root>&x;</root>")) {
			for (boolean mode : new boolean[] { false, true }) {
				reject(xml, mode, false);
				reject(xml, mode, true);
			}
		}

		int schemas = 0;
		if (args.length != 0) {
			try (var paths = Files.walk(Path.of(args[0]))) {
				for (Path path : paths.filter(p -> p.toString().endsWith(".exsd")).sorted().toList()) {
					byte[] xml = Files.readAllBytes(path);
					for (boolean mode : new boolean[] { false, true }) {
						compare(xml, mode);
					}
					schemas++;
				}
			}
		}
		System.out.println("PASS " + checks + " checks; " + fixtures.size()
				+ " synthetic fixtures in both modes; " + schemas + " EXSD files in both modes");
	}

	private static byte[] bytes(String xml) {
		return xml.getBytes(StandardCharsets.UTF_8);
	}

	private static void compare(byte[] xml, boolean abbreviated) throws Exception {
		assertTree(legacy(xml, abbreviated), candidate(xml, abbreviated), "/");
		checks++;
	}

	private static Element legacy(byte[] xml, boolean abbreviated) throws Exception {
		XMLDefaultHandler handler = new XMLDefaultHandler(abbreviated);
		XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE().parse(new ByteArrayInputStream(xml), handler);
		return (Element) handler.getDocumentElement();
	}

	private static Element candidate(byte[] xml, boolean abbreviated) throws Exception {
		return SchemaDocumentParser.parse(new ByteArrayInputStream(xml), abbreviated);
	}

	private static void reject(String xml, boolean abbreviated, boolean direct) throws Exception {
		try {
			if (direct) {
				candidate(bytes(xml), abbreviated);
			} else {
				legacy(bytes(xml), abbreviated);
			}
			throw new AssertionError("accepted malformed/DOCTYPE XML; direct=" + direct + ", abbreviated=" + abbreviated);
		} catch (SAXException expected) {
			checks++;
		}
	}

	private static void assertTree(Node expected, Node actual, String location) {
		check(expected.getNodeType() == actual.getNodeType(), location + " node type");
		check(Objects.equals(expected.getNodeName(), actual.getNodeName()), location + " node name");
		check(Objects.equals(expected.getNodeValue(), actual.getNodeValue()), location + " node value");
		check(Objects.equals(expected.getNamespaceURI(), actual.getNamespaceURI()), location + " namespace URI");
		check(Objects.equals(expected.getLocalName(), actual.getLocalName()), location + " local name");
		check(Objects.equals(expected.getPrefix(), actual.getPrefix()), location + " prefix");
		NamedNodeMap expectedAttributes = expected.getAttributes();
		NamedNodeMap actualAttributes = actual.getAttributes();
		if (expectedAttributes != null) {
			check(actualAttributes != null && expectedAttributes.getLength() == actualAttributes.getLength(),
					location + " attribute count");
			for (int i = 0; i < expectedAttributes.getLength(); i++) {
				Node attribute = expectedAttributes.item(i);
				Node actualAttribute = actualAttributes.getNamedItem(attribute.getNodeName());
				check(actualAttribute != null, location + " missing attribute " + attribute.getNodeName());
				assertTree(attribute, actualAttribute, location + "@" + attribute.getNodeName());
			}
		}
		check(expected.getChildNodes().getLength() == actual.getChildNodes().getLength(), location + " child count");
		Node child = expected.getFirstChild();
		Node actualChild = actual.getFirstChild();
		for (int i = 0; child != null; i++, child = child.getNextSibling(), actualChild = actualChild.getNextSibling()) {
			assertTree(child, actualChild, location + child.getNodeName() + "[" + i + "]/");
		}
	}

	private static void check(boolean condition, String description) {
		if (!condition) {
			throw new AssertionError(description);
		}
		checks++;
	}
}
