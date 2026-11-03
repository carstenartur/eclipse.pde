import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import javax.xml.parsers.DocumentBuilderFactory;

import org.eclipse.core.commands.AbstractHandler;
import org.eclipse.core.commands.ExecutionEvent;
import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.IConfigurationElement;
import org.eclipse.core.runtime.IExecutableExtension;
import org.eclipse.core.runtime.IExtensionRegistry;
import org.eclipse.core.runtime.RegistryFactory;
import org.eclipse.core.runtime.spi.RegistryContributor;
import org.eclipse.core.runtime.spi.RegistryStrategy;
import org.eclipse.e4.ui.css.core.dom.IElementProvider;
import org.eclipse.e4.ui.css.core.engine.CSSEngine;
import org.eclipse.e4.ui.css.core.impl.engine.RegistryCSSElementProvider;
import org.w3c.dom.Element;

/** Real SDK registry parsing/executable initialization and CSS provider selection. */
public final class ExtraConsumerProbe {
    public static final class CapturingHandler extends AbstractHandler implements IExecutableExtension {
        Object data;
        String property;
        public CapturingHandler() { }
        @Override
        public Object execute(ExecutionEvent event) { return null; }
        @Override
        public void setInitializationData(IConfigurationElement config, String propertyName, Object data) {
            this.property = propertyName;
            this.data = data;
        }
    }

    public static final class WidgetA { }
    public static final class WidgetB { }
    public static final class WidgetC { }

    public static class ReturningProvider implements IElementProvider {
        private final String name;
        ReturningProvider(String name) { this.name = name; }
        @Override
        public Element getElement(Object object, CSSEngine engine) {
            try {
                return DocumentBuilderFactory.newInstance().newDocumentBuilder().newDocument().createElement(name);
            } catch (Exception failure) {
                throw new AssertionError(failure);
            }
        }
    }
    public static final class ProviderA extends ReturningProvider { public ProviderA() { super("a"); } }
    public static final class ProviderB extends ReturningProvider { public ProviderB() { super("b"); } }
    public static final class ProviderC extends ReturningProvider { public ProviderC() { super("c"); } }

    private static void require(boolean value, String message) {
        if (!value) { throw new AssertionError(message); }
    }

    public static void main(String[] args) throws Exception {
        Object token = new Object();
        // Standard SDK strategy: actual reflection/class loading, no replacement registry/consumer classes.
        IExtensionRegistry registry = RegistryFactory.createRegistry(new RegistryStrategy(null, null), token, token);
        StringBuilder xml = new StringBuilder("<plugin><extension-point id=\"commands\" name=\"Commands\"/>"
                + "<extension-point id=\"elementProvider\" name=\"Providers\"/>"
                + "<extension point=\"org.eclipse.e4.ui.css.core.commands\">");
        for (int count = 0; count < 3; count++) {
            xml.append("<command id=\"").append(count).append("\"><defaultHandler class=\"")
                    .append(CapturingHandler.class.getName()).append("\">");
            for (int index = 0; index < count; index++) {
                xml.append("<parameter name=\"p").append(index).append("\" value=\"v").append(index).append("\"/>");
            }
            xml.append("</defaultHandler></command>");
        }
        xml.append("<command id=\"bad\"><defaultHandler class=\"no.such.Handler\"/></command></extension>")
                .append("<extension point=\"org.eclipse.e4.ui.css.core.elementProvider\">");
        Class<?>[] providers = { ProviderA.class, ProviderB.class, ProviderC.class };
        Class<?>[] widgets = { WidgetA.class, WidgetB.class, WidgetC.class };
        for (int i = 0; i < providers.length; i++) {
            xml.append("<provider class=\"").append(providers[i].getName()).append("\"><widget class=\"")
                    .append(widgets[i].getName()).append("\"/></provider>");
        }
        xml.append("</extension></plugin>");
        try {
            require(registry.addContribution(new ByteArrayInputStream(xml.toString().getBytes(StandardCharsets.UTF_8)),
                    new RegistryContributor("probe", "org.eclipse.e4.ui.css.core", null, null), false,
                    "extra-consumer-contract.xml", null, token), "Contribution rejected");
            IConfigurationElement[] commands = registry.getConfigurationElementsFor("org.eclipse.e4.ui.css.core.commands");
            require(commands.length == 4, "Expected three valid and one invalid handler case");
            for (IConfigurationElement command : commands) {
                String id = command.getAttribute("id");
                if (id.equals("bad")) {
                    try {
                        command.createExecutableExtension("defaultHandler");
                        throw new AssertionError("Absent handler class was accepted");
                    } catch (CoreException expected) {
                        System.out.println("PASS defaultHandler absentClass=CoreException");
                    }
                    continue;
                }
                int count = Integer.parseInt(id);
                CapturingHandler handler = (CapturingHandler) command.createExecutableExtension("defaultHandler");
                require("defaultHandler".equals(handler.property), "Initialization property lost");
                if (count == 0) {
                    require(handler.data == null, "Zero parameters must yield null initialization data");
                } else {
                    require(handler.data instanceof Map<?, ?>, "Parameters must yield an initialization map");
                    Map<?, ?> values = (Map<?, ?>) handler.data;
                    require(values.size() == count, "Wrong number of initialization parameters");
                    for (int i = 0; i < count; i++) {
                        require(("v" + i).equals(values.get("p" + i)), "Initialization parameter lost");
                    }
                }
                System.out.println("PASS defaultHandler parameters=" + count + " initialization=preserved");
            }
            require(registry.getConfigurationElementsFor("org.eclipse.e4.ui.css.core.elementProvider").length == 3,
                    "Expected three providers in the same contribution");
            RegistryCSSElementProvider consumer = new RegistryCSSElementProvider(registry);
            Object[] objects = { new WidgetA(), new WidgetB(), new WidgetC() };
            for (int i = 0; i < objects.length; i++) {
                Element element = consumer.getElement(objects[i], null);
                require(element != null && element.getTagName().equals(String.valueOf((char) ('a' + i))),
                        "Consumer did not select provider " + i);
                System.out.println("PASS elementProvider index=" + i + " selected=TRUE");
            }
            require(consumer.getElement(new Object(), null) == null, "Unmatched object must not select a provider");
            System.out.println("PASS elementProvider unmatched=NULL");
            for (Class<?> type : new Class<?>[] { registry.getClass(), RegistryCSSElementProvider.class }) {
                System.out.println("SOURCE " + type.getName() + " " + type.getProtectionDomain().getCodeSource().getLocation());
            }
        } finally {
            registry.stop(token);
        }
    }
}
