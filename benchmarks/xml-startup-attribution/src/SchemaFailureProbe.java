/*
 * Copyright (c) 2026 Carsten Hammer and others.
 * SPDX-License-Identifier: EPL-2.0
 */
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.URI;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;

import org.eclipse.pde.internal.core.schema.Schema;
import org.eclipse.pde.internal.core.schema.SchemaDescriptor;

/** Counts real PDE loads; synthetic inputs are not production defect evidence. */
public final class SchemaFailureProbe {
    private static final int QUERIES = 24;

    private static final class CountedInput {
        int opens;
        final byte[] bytes;
        final URL url;

        CountedInput(String xml) throws Exception {
            bytes = xml.getBytes(StandardCharsets.UTF_8);
            url = URL.of(URI.create("memory:/fixture.exsd"), new URLStreamHandler() {
                @Override
                protected URLConnection openConnection(URL target) {
                    return new URLConnection(target) {
                        @Override public void connect() { }
                        @Override public InputStream getInputStream() {
                            opens++;
                            return new ByteArrayInputStream(bytes);
                        }
                    };
                }
            });
        }
    }

    public static void main(String[] args) throws Exception {
        for (boolean abbreviated : new boolean[] { false, true }) {
            run("corrected", "<schema><element name='root'/></schema>", abbreviated, true);
            run("malformed_xml", "<schema><element name='root'></schema>", abbreviated, false);
            run("missing_element_name", "<schema><element/></schema>", abbreviated, false);
        }
    }

    private static void run(String name, String xml, boolean abbreviated, boolean expectedLoaded)
            throws Exception {
        CountedInput input = new CountedInput(xml);
        SchemaDescriptor descriptor = new SchemaDescriptor("example.point", input.url);
        Schema schema = (Schema) descriptor.getSchema(abbreviated);
        for (int i = 0; i < QUERIES; i++) {
            if (descriptor.getSchema(abbreviated) != schema) {
                throw new AssertionError("Descriptor did not retain the schema");
            }
            switch (i % 3) {
                case 0 -> schema.findElement("root");
                case 1 -> schema.getElements();
                default -> schema.getResolvedElements();
            }
        }
        int expectedOpens = expectedLoaded ? 1 : QUERIES + 1;
        if (input.opens != expectedOpens || schema.isLoaded() != expectedLoaded) {
            throw new AssertionError(name + ": opens=" + input.opens + ", loaded=" + schema.isLoaded());
        }
        System.out.printf(java.util.Locale.ROOT,
                "{\"fixture\":\"%s\",\"synthetic\":true,\"abbreviated\":%s,"
                + "\"queries\":%d,\"streamOpens\":%d,\"schemaLoaded\":%s}%n",
                name, abbreviated, QUERIES, input.opens, schema.isLoaded());
    }
}
