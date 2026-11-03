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
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.w3c.dom.NamedNodeMap;
import org.w3c.dom.Node;

/** Small comparison, not a startup measurement or a replacement for JMH. */
@SuppressWarnings("restriction")
public class SchemaDocumentParserBenchmark {

	private static volatile long consumed;

	public static void main(String[] args) throws Exception {
		List<byte[]> corpus;
		try (var paths = Files.walk(Path.of(args[0]))) {
			corpus = paths.filter(p -> p.toString().endsWith(".exsd")).sorted().map(path -> {
				try {
					return Files.readAllBytes(path);
				} catch (java.io.IOException e) {
					throw new java.io.UncheckedIOException(e);
				}
			}).toList();
		}
		if (corpus.isEmpty()) {
			throw new IllegalArgumentException("No EXSD files in corpus");
		}
		int iterations = args.length > 1 ? Integer.parseInt(args[1]) : 100;
		var bean = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
		if (!bean.isCurrentThreadCpuTimeSupported() || !bean.isThreadAllocatedMemorySupported()) {
			throw new IllegalStateException("CPU time and thread allocation counters required");
		}
		bean.setThreadCpuTimeEnabled(true);
		bean.setThreadAllocatedMemoryEnabled(true);
		long threadId = Thread.currentThread().threadId();
		for (int i = 0; i < 500; i++) {
			load(corpus, false);
			load(corpus, true);
		}
		System.out.println("# " + corpus.size() + " EXSD files; UTF-8/source bytes preloaded; full roots fully walked");
		System.out.println("round\tparser\tcpu_ms_per_corpus\tallocated_MiB_per_corpus\tchecksum");
		for (int round = 0; round < 8; round++) {
			for (int order = 0; order < 2; order++) {
				boolean direct = (round + order) % 2 == 0;
				long cpuStart = bean.getCurrentThreadCpuTime();
				long allocatedStart = bean.getThreadAllocatedBytes(threadId);
				for (int i = 0; i < iterations; i++) {
					load(corpus, direct);
				}
				long allocated = bean.getThreadAllocatedBytes(threadId) - allocatedStart;
				long cpu = bean.getCurrentThreadCpuTime() - cpuStart;
				System.out.printf(java.util.Locale.ROOT, "%d\t%s\t%.6f\t%.6f\t%d%n", round + 1,
						direct ? "direct-dom" : "patched-sax", cpu / 1_000_000.0 / iterations,
						allocated / 1048576.0 / iterations, consumed);
			}
		}
	}

	private static void load(List<byte[]> corpus, boolean direct) throws Exception {
		long checksum = 0;
		for (byte[] xml : corpus) {
			Node root;
			if (direct) {
				root = SchemaDocumentParser.parse(new ByteArrayInputStream(xml), false);
			} else {
				XMLDefaultHandler handler = new XMLDefaultHandler();
				XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE().parse(new ByteArrayInputStream(xml), handler);
				root = handler.getDocumentElement();
			}
			checksum = checksum * 31 + walk(root);
		}
		consumed = checksum;
	}

	private static long walk(Node node) {
		long hash = node.getNodeType();
		hash = hash * 31 + node.getNodeName().hashCode();
		if (node.getNodeValue() != null) {
			hash = hash * 31 + node.getNodeValue().hashCode();
		}
		NamedNodeMap attributes = node.getAttributes();
		if (attributes != null) {
			long attributeHash = 0;
			for (int i = 0; i < attributes.getLength(); i++) {
				attributeHash += walk(attributes.item(i));
			}
			hash = hash * 31 + attributeHash;
		}
		for (Node child = node.getFirstChild(); child != null; child = child.getNextSibling()) {
			hash = hash * 31 + walk(child);
		}
		return hash;
	}
}
