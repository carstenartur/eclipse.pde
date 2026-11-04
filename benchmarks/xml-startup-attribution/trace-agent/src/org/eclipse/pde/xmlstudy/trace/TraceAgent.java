package org.eclipse.pde.xmlstudy.trace;

import java.io.*;
import java.lang.instrument.*;
import java.nio.file.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.util.jar.JarFile;
import org.eclipse.pde.xmlstudy.trace.bootstrap.TraceBridge;
import org.objectweb.asm.*;
import org.objectweb.asm.commons.*;

/** Premain-only diagnostic agent. Never include it in primary timing cells. */
public final class TraceAgent {
    public static void premain(String options, Instrumentation instrumentation) throws Exception {
        String destination = options == null || options.isBlank() ? System.getProperty("xml.trace.output") : options;
        if (destination == null || destination.isBlank()) throw new IllegalArgumentException("Use -javaagent:xml-trace-agent.jar=/absolute/new/trace.jsonl");
        Path self=Path.of(TraceAgent.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        Path bootstrap=self.resolveSibling("xml-trace-bootstrap.jar");
        instrumentation.appendToBootstrapClassLoaderSearch(new JarFile(bootstrap.toFile()));
        // All Eclipse bundle class loaders must resolve the exact same bootstrap sink.
        String delegation=System.getProperty("org.osgi.framework.bootdelegation", "");
        String bridgePackage="org.eclipse.pde.xmlstudy.trace.bootstrap";
        if (!delegation.contains(bridgePackage)) System.setProperty("org.osgi.framework.bootdelegation",
                delegation.isBlank() ? bridgePackage : delegation+","+bridgePackage);
        TraceBridge.initialize(destination);
        Module bridge=TraceBridge.class.getModule();
        for (Module module : ModuleLayer.boot().modules()) {
            if (module.getName().equals("java.base") || module.getName().equals("java.xml")) {
                instrumentation.redefineModule(module,Set.of(bridge),Map.of(),Map.of(),Set.of(),Map.of());
            }
        }
        Transformer transformer=new Transformer();
        instrumentation.addTransformer(transformer,true);
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (candidate(type.getName().replace('.','/')) && instrumentation.isModifiableClass(type)) {
                try { instrumentation.retransformClasses(type); }
                catch (Throwable failure) { TraceBridge.instrumentationError(type.getName(),failure); }
            }
        }
    }

    static boolean candidate(String name) {
        return name.equals("java/io/FileInputStream") || name.equals("java/net/URL") || name.equals("java/nio/file/Files") || name.equals("java/util/zip/ZipFile")
                || name.equals("sun/net/www/protocol/jar/JarURLConnection")
                || name.equals("sun/net/www/protocol/file/FileURLConnection")
                || name.startsWith("org/eclipse/osgi/storage/bundlefile/") || name.startsWith("org/eclipse/osgi/storage/url/")
                || name.equals("org/eclipse/osgi/framework/internal/protocol/bundleentry/Handler")
                || name.equals("org/eclipse/osgi/framework/internal/protocol/BundleURLConnection")
                || name.equals("com/sun/org/apache/xerces/internal/parsers/AbstractSAXParser")
                || name.equals("com/sun/org/apache/xerces/internal/parsers/DOMParser")
                || name.equals("org/apache/xerces/parsers/AbstractSAXParser") || name.equals("org/apache/xerces/parsers/DOMParser")
                || name.equals("com/sun/xml/internal/stream/XMLInputFactoryImpl")
                || name.equals("org/eclipse/core/internal/registry/ExtensionsParser")
                || name.equals("org/eclipse/core/internal/registry/ExtensionRegistry")
                || name.equals("org/eclipse/core/internal/registry/osgi/RegistryStrategyOSGI")
                || name.equals("org/eclipse/pde/internal/core/builders/ManifestConsistencyChecker")
                || name.equals("org/eclipse/pde/internal/core/builders/ExtensionPointSchemaBuilder")
                || name.equals("org/eclipse/jdt/internal/core/builder/JavaBuilder")
                || name.equals("org/eclipse/pde/internal/core/XMLDefaultHandler")
                || name.equals("org/eclipse/pde/internal/core/schema/Schema")
                || name.equals("org/eclipse/pde/internal/core/plugin/AbstractExtensionsModel")
                || name.equals("org/eclipse/emf/ecore/xmi/impl/XMLLoadImpl")
                || name.equals("org/eclipse/emf/ecore/xmi/impl/XMLResourceImpl")
                || name.equals("org/eclipse/e4/ui/internal/workbench/ResourceHandler")
                || name.equals("org/eclipse/core/internal/jobs/JobListeners")
                || name.equals("org/eclipse/pde/xmlstudy/probe/Activator");
    }

    private static String operation(String owner,String name,String descriptor) {
        Type returns=Type.getReturnType(descriptor);
        if (owner.equals("java/io/FileInputStream") && name.equals("<init>")) return "file_open";
        if (name.equals("getInputStream") && returns.equals(Type.getType(InputStream.class))) {
            return owner.equals("java/util/zip/ZipFile") ? "zip_entry_open" : "resource_open";
        }
        if (owner.equals("java/net/URL") && name.equals("openStream")) return "resource_open";
        if (owner.equals("java/nio/file/Files") && name.equals("newInputStream")) return "resource_open";
        if ((owner.equals("java/util/zip/ZipFile") || owner.startsWith("org/eclipse/osgi/storage/bundlefile/")) && name.equals("getEntry")) return "resource_lookup";
        if (owner.endsWith("/AbstractSAXParser") && name.equals("parse")) return "sax_parse";
        if (owner.endsWith("/DOMParser") && name.equals("parse")) return "dom_parse";
        if (owner.endsWith("/XMLInputFactoryImpl") && name.startsWith("createXMLStreamReader")) return "stax_parse";
        if (owner.endsWith("/ExtensionsParser") && name.equals("parseManifest")) return "registry_parse";
        if (owner.endsWith("/ExtensionRegistry") && name.equals("addContribution")) return "registry_contribution";
        if (owner.endsWith("/RegistryStrategyOSGI") && name.equals("onStart")) return "registry_start";
        if (owner.startsWith("org/eclipse/pde/internal/core/builders/") && name.equals("build")) return "pde_builder";
        if (owner.equals("org/eclipse/jdt/internal/core/builder/JavaBuilder") && name.equals("build")) return "java_builder";
        if (owner.endsWith("/XMLDefaultHandler") && name.equals("startDocument")) return "pde_handler";
        if (owner.equals("org/eclipse/pde/internal/core/schema/Schema") && name.equals("load")) return "schema_load";
        if (owner.endsWith("/AbstractExtensionsModel") && name.equals("load")) return "pde_model_load";
        if (owner.startsWith("org/eclipse/emf/") && (name.equals("load") || name.equals("doLoad"))) return "emf_load";
        if (owner.endsWith("/ResourceHandler") && (name.equals("loadMostRecentModel") || name.equals("loadResource"))) return "e4_model_load";
        return null;
    }

    private static final class Transformer implements ClassFileTransformer {
        @Override public byte[] transform(Module module,ClassLoader loader,String className,Class<?> redefining,
                ProtectionDomain domain,byte[] bytes) {
            if (className==null || !candidate(className)) return null;
            try {
                ClassReader reader=new ClassReader(bytes);
                ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS) {
                    @Override protected String getCommonSuperClass(String left,String right) {
                        try {
                            Class<?> a=Class.forName(left.replace('/','.'),false,loader);
                            Class<?> b=Class.forName(right.replace('/','.'),false,loader);
                            if (a.isAssignableFrom(b)) return left;
                            if (b.isAssignableFrom(a)) return right;
                            if (a.isInterface() || b.isInterface()) return "java/lang/Object";
                            do { a=a.getSuperclass(); } while (!a.isAssignableFrom(b));
                            return a.getName().replace('.','/');
                        } catch (Throwable failure) {
                            throw new IllegalStateException("Cannot compute verification frame for "+left+" and "+right,failure);
                        }
                    }
                };
                List<String> methods=new ArrayList<>();
                reader.accept(new ClassVisitor(Opcodes.ASM9,writer) {
                    @Override public MethodVisitor visitMethod(int access,String name,String descriptor,String signature,String[] exceptions) {
                        MethodVisitor delegate=super.visitMethod(access,name,descriptor,signature,exceptions);
                        if ((access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE))!=0) return delegate;
                        Type[] args=Type.getArgumentTypes(descriptor);
                        boolean phase=className.equals("org/eclipse/pde/xmlstudy/probe/Activator")
                                && (name.equals("emit") || name.equals("finish")) && args.length>0 && args[0].equals(Type.getType(String.class));
                        boolean job=className.equals("org/eclipse/core/internal/jobs/JobListeners")
                                && Set.of("scheduled","running","done","sleeping","awake","aboutToRun",
                                        "queueScheduled","queueRunning","queueDone","queueSleeping","queueAwake","queueAboutToRun").contains(name);
                        String operation=operation(className,name,descriptor);
                        if (!phase && !job && operation==null) return delegate;
                        methods.add(name+descriptor);
                        if (phase || job) return new AdviceAdapter(Opcodes.ASM9,delegate,access,name,descriptor) {
                            @Override protected void onMethodEnter() {
                                if (phase) { loadArg(0); invokeStatic(Type.getType(TraceBridge.class),new Method("phase","(Ljava/lang/String;)V")); }
                                else { push(name); loadArgArray(); invokeStatic(Type.getType(TraceBridge.class),new Method("job","(Ljava/lang/String;[Ljava/lang/Object;)V")); }
                            }
                        };
                        return new SpanAdvice(delegate,access,name,descriptor,operation,className);
                    }
                },ClassReader.EXPAND_FRAMES);
                if (methods.isEmpty()) return null;
                byte[] transformed=writer.toByteArray();
                TraceBridge.instrumentation(className,methods);
                return transformed;
            } catch (Throwable failure) { TraceBridge.instrumentationError(className,failure); return null; }
        }
    }

    private static final class SpanAdvice extends AdviceAdapter {
        private static final Type BRIDGE=Type.getType(TraceBridge.class);
        private final String operation,owner,name,descriptor;
        private final boolean isStatic;
        private final Label begin=new Label(),end=new Label(),handler=new Label();
        private int token;
        SpanAdvice(MethodVisitor delegate,int access,String name,String descriptor,String operation,String owner) {
            super(Opcodes.ASM9,delegate,access,name,descriptor);
            this.operation=operation; this.owner=owner; this.name=name; this.descriptor=descriptor;
            this.isStatic=(access & Opcodes.ACC_STATIC)!=0;
        }
        @Override protected void onMethodEnter() {
            push(operation); push(owner.replace('/','.')+"."+name+descriptor);
            if (isStatic) visitInsn(ACONST_NULL); else loadThis();
            loadArgArray();
            invokeStatic(BRIDGE,new Method("enter","(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)J"));
            token=newLocal(Type.LONG_TYPE); storeLocal(token); mark(begin);
        }
        @Override protected void onMethodExit(int opcode) {
            if (opcode==ATHROW) return;
            Type returns=Type.getReturnType(descriptor);
            int result=-1;
            if (returns!=Type.VOID_TYPE) { result=newLocal(returns); storeLocal(result); }
            loadLocal(token);
            if (operation.equals("resource_open") || operation.equals("zip_entry_open")) {
                loadLocal(result); invokeStatic(BRIDGE,new Method("opened","(JLjava/io/InputStream;)Ljava/io/InputStream;"));
            } else {
                if (result<0) visitInsn(ACONST_NULL); else { loadLocal(result); box(returns); }
                invokeStatic(BRIDGE,new Method("returned","(JLjava/lang/Object;)V"));
                if (result>=0) loadLocal(result);
            }
        }
        @Override public void visitMaxs(int maxStack,int maxLocals) {
            mark(end); visitTryCatchBlock(begin,end,handler,"java/lang/Throwable"); mark(handler);
            int failure=newLocal(Type.getType(Throwable.class)); storeLocal(failure);
            loadLocal(token); loadLocal(failure); invokeStatic(BRIDGE,new Method("failed","(JLjava/lang/Throwable;)V"));
            loadLocal(failure); throwException();
            super.visitMaxs(maxStack,maxLocals);
        }
    }
}
