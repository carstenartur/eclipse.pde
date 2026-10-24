/*******************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Eclipse Public License 2.0 which accompanies this distribution,
 * and is available at https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *******************************************************************************/
package org.eclipse.pde.internal.core.schema;

import java.io.IOException;
import java.io.InputStream;

import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;

import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.XMLReader;
import org.xml.sax.ext.DefaultHandler2;

import com.ctc.wstx.sax.WstxSAXParserFactory;
import com.ctc.wstx.stax.WstxInputFactory;

/** Experimental, locally selected provider for schema loading only. */
final class SchemaXmlReader {

	private static final WstxSAXParserFactory FACTORY = createFactory();

	private static final DefaultHandler2 REJECT_DOCTYPE = new DefaultHandler2() {
		@Override
		public void startDTD(String name, String publicId, String systemId) throws SAXException {
			throw new SAXException("DOCTYPE is not allowed in extension point schemas"); //$NON-NLS-1$
		}
	};

	private SchemaXmlReader() {
	}

	private static WstxSAXParserFactory createFactory() {
		WstxInputFactory input = new WstxInputFactory();
		input.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, false);
		input.setProperty(XMLInputFactory.SUPPORT_DTD, false);
		input.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
		input.setXMLResolver((publicId, systemId, base, namespace) -> {
			throw new XMLStreamException("External entity resolution is not allowed"); //$NON-NLS-1$
		});
		return new WstxSAXParserFactory(input);
	}

	static void parse(InputStream stream, XMLDefaultHandler handler) throws SAXException, IOException {
		XMLReader reader;
		synchronized (FACTORY) {
			reader = FACTORY.newSAXParser().getXMLReader();
		}
		reader.setProperty("http://xml.org/sax/properties/lexical-handler", REJECT_DOCTYPE); //$NON-NLS-1$
		reader.setContentHandler(handler);
		reader.setDTDHandler(handler);
		reader.setErrorHandler(handler);
		reader.setEntityResolver((publicId, systemId) -> {
			throw new SAXException("External entity resolution is not allowed"); //$NON-NLS-1$
		});
		reader.parse(new InputSource(stream));
	}
}
