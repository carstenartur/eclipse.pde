package bench;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.zip.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.eclipse.core.internal.runtime.XmlProcessorFactory;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.sandbox.jdt.internal.corext.fix.helper.SchemaTransformationUtils;
import org.w3c.dom.*;

/** Corpus preparation and semantic checks, never called in a timed benchmark. */
public class Prepare {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args.length == 0 ? "." : args[0]).toAbsolutePath();
        Path original = root.resolve("corpus/original");
        Path compact = root.resolve("corpus/compact");
        Files.createDirectories(root.resolve("results"));
        List<Path> files;
        try (var walk = Files.walk(original)) {
            files = walk.filter(Files::isRegularFile).sorted().toList();
        }
        if (files.size() != 50) throw new AssertionError("Expected 50 files, got " + files.size());
        long before = 0, after = 0, oldNodes = 0, newNodes = 0;
        StringBuilder stats = new StringBuilder("path,original_bytes,compact_bytes,full_nodes_original,full_nodes_compact\n");
        for (Path file : files) {
            String source = Files.readString(file, StandardCharsets.UTF_8);
            String transformed = SchemaTransformationUtils.transform(source, StandardCharsets.UTF_8, false);
            // Check the exact transformation on this corpus, including comments, PIs,
            // attribute values, and significant text. Ignore only structural indentation.
            String a = signature(parse(source), false);
            String b = signature(parse(transformed), false);
            if (!a.equals(b)) {
                Path diagnostic = root.resolve("results/semantic-mismatch");
                Files.createDirectories(diagnostic);
                Files.writeString(diagnostic.resolve("original-signature.txt"), a);
                Files.writeString(diagnostic.resolve("compact-signature.txt"), b);
                Files.writeString(diagnostic.resolve("compact.xml"), transformed);
                int at = 0;
                while (at < Math.min(a.length(), b.length()) && a.charAt(at) == b.charAt(at)) at++;
                throw new AssertionError("Semantic mismatch: " + file + " at " + at
                    + "\noriginal: " + a.substring(Math.max(0, at - 80), Math.min(a.length(), at + 180))
                    + "\ncompact: " + b.substring(Math.max(0, at - 80), Math.min(b.length(), at + 180)));
            }
            if (!transformed.equals(SchemaTransformationUtils.transform(transformed, StandardCharsets.UTF_8, false)))
                throw new AssertionError("Not idempotent: " + file);
            Path destination = compact.resolve(original.relativize(file));
            Files.createDirectories(destination.getParent());
            Files.writeString(destination, transformed, StandardCharsets.UTF_8);
            for (boolean abbreviated : List.of(true, false)) {
                if (!signature(pde(source, abbreviated), false).equals(signature(pde(transformed, abbreviated), false)))
                    throw new AssertionError("PDE DOM mismatch: " + file + " abbreviated=" + abbreviated);
            }
            long n1 = count(pde(source, false)), n2 = count(pde(transformed, false));
            long s1 = Files.size(file), s2 = Files.size(destination);
            before += s1; after += s2; oldNodes += n1; newNodes += n2;
            stats.append(original.relativize(file)).append(',').append(s1).append(',').append(s2)
                .append(',').append(n1).append(',').append(n2).append('\n');
        }
        Files.writeString(root.resolve("results/files.csv"), stats);
        zip(original, root.resolve("corpus/original.jar"));
        zip(compact, root.resolve("corpus/compact.jar"));
        String json = "{\n  \"files\":50,\n  \"schemas\":49,\n  \"xml_bytes_original\":" + before
            + ",\n  \"xml_bytes_compact\":" + after
            + ",\n  \"xml_only_jar_original\":" + Files.size(root.resolve("corpus/original.jar"))
            + ",\n  \"xml_only_jar_compact\":" + Files.size(root.resolve("corpus/compact.jar"))
            + ",\n  \"full_dom_nodes_original\":" + oldNodes + ",\n  \"full_dom_nodes_compact\":" + newNodes
            + ",\n  \"semantic_checks_passed\":50,\n  \"idempotence_checks_passed\":50\n}\n";
        Files.writeString(root.resolve("results/corpus-summary.json"), json);
        System.out.println(json);
        System.out.println("Parser: " + XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE().getClass().getName());
    }

    static Document parse(String xml) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setCoalescing(true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        return factory.newDocumentBuilder().parse(new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)));
    }

    static Node pde(String xml, boolean abbreviated) throws Exception {
        XMLDefaultHandler handler = new XMLDefaultHandler(abbreviated);
        XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE().parse(
            new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)), handler);
        return handler.getDocument();
    }

    static long count(Node node) {
        long n = 1;
        for (Node c = node.getFirstChild(); c != null; c = c.getNextSibling()) n += count(c);
        return n;
    }

    static String signature(Node node, boolean preserve) {
        if (node instanceof Element e && e.hasAttribute("xml:space")) preserve = "preserve".equals(e.getAttribute("xml:space"));
        // EXSD documentation is content, including whitespace. Elsewhere this
        // corpus check ignores whitespace-only nodes when there is no mixed text.
        boolean documentation = node.getNodeName().equals("documentation") || node.getNodeName().endsWith(":documentation");
        if (documentation) {
            boolean hasElement = false;
            for (Node c = node.getFirstChild(); c != null; c = c.getNextSibling()) hasElement |= c.getNodeType() == Node.ELEMENT_NODE;
            preserve |= hasElement || !node.getTextContent().isBlank();
        }
        StringBuilder b = new StringBuilder();
        b.append('[').append(node.getNodeType()).append(':');
        append(b, node.getNodeName());
        if (node.getNodeValue() != null) append(b, node.getNodeValue());
        NamedNodeMap attrs = node.getAttributes();
        if (attrs != null) {
            List<String> a = new ArrayList<>();
            for (int i = 0; i < attrs.getLength(); i++) {
                Node attr = attrs.item(i); a.add(attr.getNodeName() + "=" + attr.getNodeValue());
            }
            Collections.sort(a); for (String attr : a) append(b, attr);
        }
        boolean hasText = false;
        for (Node c = node.getFirstChild(); c != null; c = c.getNextSibling()) {
            hasText |= (c.getNodeType() == Node.TEXT_NODE || c.getNodeType() == Node.CDATA_SECTION_NODE)
                && !c.getNodeValue().isBlank();
        }
        for (Node c = node.getFirstChild(); c != null; c = c.getNextSibling()) {
            if (!preserve && !hasText && c.getNodeType() == Node.TEXT_NODE && c.getNodeValue().isBlank()) continue;
            b.append(signature(c, preserve));
        }
        return b.append(']').toString();
    }

    static void append(StringBuilder b, String value) { b.append(value.length()).append(':').append(value); }

    static void zip(Path source, Path target) throws Exception {
        try (ZipOutputStream out = new ZipOutputStream(Files.newOutputStream(target)); var walk = Files.walk(source)) {
            out.setLevel(6);
            for (Path p : walk.filter(Files::isRegularFile).sorted().toList()) {
                ZipEntry entry = new ZipEntry(source.relativize(p).toString().replace('\\', '/'));
                entry.setTimeLocal(LocalDateTime.of(1980, 1, 1, 0, 0));
                out.putNextEntry(entry); Files.copy(p, out); out.closeEntry();
            }
        }
    }
}
