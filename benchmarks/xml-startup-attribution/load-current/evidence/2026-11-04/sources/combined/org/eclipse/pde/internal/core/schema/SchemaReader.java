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
package org.eclipse.pde.internal.core.schema;

import java.io.InputStream;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicReference;

import javax.xml.parsers.SAXParser;

import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.w3c.dom.Node;

/** Builds schema DOMs while retaining at most one idle, reset parser. */
public final class SchemaReader {

	// reset() need not clear provider caches such as interned XML names. Retire
	// parsers periodically while amortizing their construction across many reads.
	private static final int MAX_PARSER_USES = 100;

	private static final class CachedParser {
		final SAXParser parser;
		int uses;

		CachedParser(SAXParser parser) {
			this.parser = parser;
		}
	}

	private final Callable<SAXParser> parserFactory;
	private final AtomicReference<CachedParser> idleParser = new AtomicReference<>();

	/**
	 * @param parserFactory creates a new, securely configured parser; must allow
	 *                      concurrent calls
	 */
	public SchemaReader(Callable<SAXParser> parserFactory) {
		this.parserFactory = parserFactory;
	}

	public Node read(InputStream stream, boolean abbreviated) throws Exception {
		// Remove the parser while it is in use, including during concurrent or
		// reentrant reads. Keep at most one idle parser, without retaining threads.
		CachedParser cached = idleParser.getAndSet(null);
		if (cached == null) {
			cached = new CachedParser(parserFactory.call());
		}
		SAXParser parser = cached.parser;
		XMLDefaultHandler handler = new XMLDefaultHandler(abbreviated);
		parser.parse(stream, handler);
		Node root = handler.getDocumentElement();
		// Only a successful parse may return a parser to the cache. Reset also
		// releases handlers and the document they reference before publication.
		try {
			parser.reset();
			if (++cached.uses < MAX_PARSER_USES) {
				idleParser.compareAndSet(null, cached);
			}
		} catch (UnsupportedOperationException e) {
			// Providers without reset support remain usable, without caching.
		}
		return root;
	}
}
