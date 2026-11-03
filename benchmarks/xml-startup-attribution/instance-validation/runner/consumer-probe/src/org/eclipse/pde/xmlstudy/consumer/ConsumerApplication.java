package org.eclipse.pde.xmlstudy.consumer;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.eclipse.core.expressions.ExpressionConverter;
import org.eclipse.core.runtime.Platform;
import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;
import org.eclipse.ui.internal.wizards.datatransfer.expressions.HasFolderExpression;

/** Runs the unchanged contract probe after Eclipse's platform is initialized. */
public final class ConsumerApplication implements IApplication {

	@Override
	public Object start(IApplicationContext context) throws Exception {
		Path source = Path.of(System.getProperty("xml.consumer.source"));
		Path output = Path.of(System.getProperty("xml.consumer.output"));
		String sourceHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(source)));
		Map<String, Object> result = new LinkedHashMap<>();
		result.put("sourceSha256", sourceHash);
		result.put("platformRunning", Platform.isRunning());
		result.put("application", "org.eclipse.pde.xmlstudy.consumer.check");
		result.put("javaVersion", System.getProperty("java.runtime.version"));
		Class<?> probe = Class.forName("ConsumerContractProbe");
		result.put("codeSources", Map.of("probe", probe.getProtectionDomain().getCodeSource().getLocation().toExternalForm(),
				"expressions", ExpressionConverter.class.getProtectionDomain().getCodeSource().getLocation().toExternalForm(),
				"hasFolder", HasFolderExpression.class.getProtectionDomain().getCodeSource().getLocation().toExternalForm()));
		result.put("bundleVersions", Map.of("expressions", Platform.getBundle("org.eclipse.core.expressions").getVersion().toString(),
				"uiIde", Platform.getBundle("org.eclipse.ui.ide").getVersion().toString()));
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		PrintStream original = System.out;
		Throwable failure = null;
		try (PrintStream capture = new PrintStream(bytes, true, StandardCharsets.UTF_8)) {
			System.setOut(capture);
			if (!Platform.isRunning() || !sourceHash.equals(System.getProperty("xml.consumer.sourceSha256"))) {
				throw new IllegalStateException("Platform not initialized or source changed since compilation");
			}
			probe.getMethod("main", String[].class).invoke(null, (Object) new String[0]);
		} catch (InvocationTargetException exception) {
			failure = exception.getCause();
		} catch (Exception exception) {
			failure = exception;
		} finally {
			System.setOut(original);
		}
		String stdout = bytes.toString(StandardCharsets.UTF_8);
		List<String> checks = stdout.lines().filter(line -> line.startsWith("PASS ")).toList();
		List<String> expected = List.of("PASS expression enablement children=3 result=TRUE",
				"PASS expression and children=3 result=TRUE", "PASS expression or children=3 result=TRUE",
				"PASS expression with children=3 result=TRUE", "PASS expression resolve children=3 result=TRUE",
				"PASS expression adapt children=3 result=TRUE", "PASS expression iterate children=3 result=TRUE",
				"PASS hasFolder directory=TRUE", "PASS hasFolder file=FALSE", "PASS hasFolder absent=FALSE");
		boolean passed = failure == null && checks.equals(expected);
		result.put("passed", passed);
		result.put("passedChecks", checks.size());
		result.put("checks", checks);
		result.put("stdout", stdout);
		if (failure != null) {
			StringWriter text = new StringWriter();
			failure.printStackTrace(new PrintWriter(text));
			result.put("failure", text.toString());
		}
		Files.createDirectories(output.toAbsolutePath().getParent());
		Path temporary = output.resolveSibling(output.getFileName() + ".tmp");
		Files.writeString(temporary, Json.encode(result) + "\n", StandardCharsets.UTF_8);
		Files.move(temporary, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
		System.out.println("XML_CONSUMER_RESULT " + Json.encode(Map.of("passed", passed, "passedChecks", checks.size(), "output", output.toString())));
		return passed ? EXIT_OK : Integer.valueOf(2);
	}

	@Override
	public void stop() {
	}
}
