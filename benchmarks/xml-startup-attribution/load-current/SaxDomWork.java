// SPDX-License-Identifier: EPL-2.0
import java.io.*;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.*;
import java.util.jar.*;
import org.eclipse.pde.internal.core.XMLDefaultHandler;
import org.w3c.dom.*;
import org.xml.sax.SAXException;

/** Intrusive work counters only: not a CPU or wall-time benchmark. */
public class SaxDomWork {
    static long characters, units, rawText, normalizedText, schemas, bytes;
    static class Handler extends XMLDefaultHandler {
        @Override public void characters(char[] c, int start, int length) throws SAXException {
            characters++; units += length; super.characters(c,start,length);
        }
    }
    static long texts(Node node) {
        long n=node.getNodeType()==Node.TEXT_NODE?1:0;
        for(Node c=node.getFirstChild();c!=null;c=c.getNextSibling()) n+=texts(c);
        return n;
    }
    static void canonical(Node node, StringBuilder value) {
        value.append(node.getNodeType()).append(':').append(node.getNodeName()).append(':');
        String text=node.getNodeValue(); if(text!=null)value.append(text.length()).append(':').append(text);
        NamedNodeMap attrs=node.getAttributes();
        if(attrs!=null) { TreeMap<String,String> sorted=new TreeMap<>(); for(int i=0;i<attrs.getLength();i++)sorted.put(attrs.item(i).getNodeName(),attrs.item(i).getNodeValue()); sorted.forEach((k,v)->value.append(k.length()).append(':').append(k).append(v.length()).append(':').append(v)); }
        value.append('{'); for(Node c=node.getFirstChild();c!=null;c=c.getNextSibling())canonical(c,value); value.append('}');
    }
    public static void main(String[] args) throws Exception {
        Field document=XMLDefaultHandler.class.getDeclaredField("fDocument"); document.setAccessible(true);
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(JarFile jar=new JarFile(Path.of(args[0]).toFile())) {
            for(JarEntry entry:jar.stream().filter(e->e.getName().endsWith(".exsd")).sorted(Comparator.comparing(JarEntry::getName)).toList()) {
                Handler handler=new Handler();
                var parser=org.eclipse.core.internal.runtime.XmlProcessorFactory.createSAXParserWithErrorOnDOCTYPE();
                try(InputStream input=jar.getInputStream(entry)){parser.parse(input,handler);}
                rawText+=texts((Document)document.get(handler));
                Document dom=handler.getDocument(); normalizedText+=texts(dom); schemas++; bytes+=entry.getSize();
                StringBuilder value=new StringBuilder(entry.getName()).append('\n');canonical(dom,value);digest.update(value.toString().getBytes(StandardCharsets.UTF_8));
            }
        }
        if(schemas!=49)throw new AssertionError("Expected 49 schemas: "+schemas);
        System.out.printf(Locale.ROOT,"{\"schemas\":%d,\"bytes\":%d,\"characterCallbacks\":%d,\"characterUnits\":%d,\"textNodesBeforeNormalization\":%d,\"normalizedTextNodes\":%d,\"domHash\":\"%s\"}%n",schemas,bytes,characters,units,rawText,normalizedText,HexFormat.of().formatHex(digest.digest()));
    }
}
