import java.io.StringReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javax.xml.parsers.DocumentBuilderFactory;

import org.eclipse.core.expressions.CompositeExpression;
import org.eclipse.core.expressions.EvaluationContext;
import org.eclipse.core.expressions.EvaluationResult;
import org.eclipse.core.expressions.Expression;
import org.eclipse.core.expressions.ExpressionConverter;
import org.eclipse.core.expressions.IVariableResolver;
import org.eclipse.ui.internal.wizards.datatransfer.expressions.HasFolderExpression;
import org.xml.sax.InputSource;

/** Exercises the real SDK consumers, without replacing Eclipse classes. */
public final class ConsumerContractProbe {
    private ConsumerContractProbe() {
    }

    public static void main(String[] args) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        Map<String, String> attributes = new LinkedHashMap<>();
        attributes.put("enablement", "");
        attributes.put("and", "");
        attributes.put("or", "");
        attributes.put("with", " variable=\"v\"");
        attributes.put("resolve", " variable=\"v\"");
        attributes.put("adapt", " type=\"java.lang.String\"");
        attributes.put("iterate", " operator=\"and\"");
        for (Map.Entry<String, String> item : attributes.entrySet()) {
            String tag = item.getKey();
            String xml = "<" + tag + item.getValue() + "><equals value=\"x\"/>"
                    + "<and><equals value=\"x\"/></and><equals value=\"x\"/></" + tag + ">";
            var element = factory.newDocumentBuilder().parse(new InputSource(new StringReader(xml)))
                    .getDocumentElement();
            Expression expression = ExpressionConverter.getDefault().perform(element);
            if (!(expression instanceof CompositeExpression composite) || composite.getChildren().length != 3) {
                throw new AssertionError("Consumer did not retain the three supplied children: " + tag);
            }
            Object contextValue = tag.equals("iterate") ? List.of("x", "x") : "x";
            EvaluationContext context = new EvaluationContext(null, contextValue,
                    new IVariableResolver[] { (name, values) -> name.equals("v") ? "x" : null });
            context.addVariable("v", "x");
            if (expression.evaluate(context) != EvaluationResult.TRUE) {
                throw new AssertionError("Consumer evaluation differs: " + tag);
            }
            System.out.println("PASS expression " + tag + " children=3 result=TRUE");
        }
        Path root = Files.createTempDirectory("xml-schema-consumer-");
        Path child = root.resolve(".metadata");
        HasFolderExpression folder = new HasFolderExpression(".metadata");
        EvaluationContext context = new EvaluationContext(null, root.toFile());
        try {
            Files.createDirectory(child);
            if (folder.evaluate(context) != EvaluationResult.TRUE) {
                throw new AssertionError("Existing directory must satisfy hasFolder");
            }
            System.out.println("PASS hasFolder directory=TRUE");
            Files.delete(child);
            Files.createFile(child);
            if (folder.evaluate(context) != EvaluationResult.FALSE) {
                throw new AssertionError("A regular file must not satisfy hasFolder");
            }
            System.out.println("PASS hasFolder file=FALSE");
            Files.delete(child);
            if (folder.evaluate(context) != EvaluationResult.FALSE) {
                throw new AssertionError("A missing path must not satisfy hasFolder");
            }
            System.out.println("PASS hasFolder absent=FALSE");
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
        System.out.println("SOURCE expressions " + ExpressionConverter.class.getProtectionDomain().getCodeSource().getLocation());
        System.out.println("SOURCE hasFolder " + HasFolderExpression.class.getProtectionDomain().getCodeSource().getLocation());
    }
}

