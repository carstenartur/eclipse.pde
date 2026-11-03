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

import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.helpers.DefaultHandler;

/** Parses the element tree consumed by {@link Schema}. */
@SuppressWarnings("restriction")
final class SchemaDocumentParser {

	private SchemaDocumentParser() {
	}

	static Element parse(InputStream stream, boolean abbreviated)
			throws ParserConfigurationException, SAXException, IOException {
		if (abbreviated) {
			XMLDefaultHandler handler = new XMLDefaultHandler(true);
			XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE().parse(stream, handler);
			return (Element) handler.getDocumentElement();
		}

		DocumentBuilder parser;
		synchronized (FullDocumentFactory.INSTANCE) {
			parser = FullDocumentFactory.INSTANCE.newDocumentBuilder();
		}
		parser.setEntityResolver((publicId, systemId) -> new InputSource(new StringReader(""))); //$NON-NLS-1$
		parser.setErrorHandler(new DefaultHandler());
		Element root = parser.parse(stream).getDocumentElement();
		// XMLDefaultHandler puts all processing instructions outside the root.
		// Schema consumes only the root, including text joined across those PIs.
		removeProcessingInstructions(root);
		root.normalize();
		return root;
	}

	private static void removeProcessingInstructions(Node parent) {
		for (Node child = parent.getFirstChild(); child != null;) {
			Node next = child.getNextSibling();
			if (child.getNodeType() == Node.PROCESSING_INSTRUCTION_NODE) {
				parent.removeChild(child);
			} else {
				removeProcessingInstructions(child);
			}
			child = next;
		}
	}

	// Do not create an additional factory for the abbreviated registry path.
	private static final class FullDocumentFactory {
		private static final DocumentBuilderFactory INSTANCE = createFactory();

		private static DocumentBuilderFactory createFactory() {
			// This API returns a fresh factory, not Platform's shared cached factory.
			DocumentBuilderFactory factory = XmlProcessorFactory.createDocumentBuilderFactoryWithErrorOnDOCTYPE();
			factory.setNamespaceAware(false);
			factory.setIgnoringComments(true);
			factory.setCoalescing(true);
			factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, ""); //$NON-NLS-1$
			factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, ""); //$NON-NLS-1$
			return factory;
		}
	}
}
