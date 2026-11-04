package org.eclipse.pde.xmlstudy.probe;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.osgi.service.runnable.StartupMonitor;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Shell;
import org.eclipse.ui.IWorkbench;
import org.eclipse.ui.IWorkbenchWindow;
import org.eclipse.ui.PlatformUI;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;
import org.osgi.framework.ServiceRegistration;

/** A passive startup observer, with an explicitly separate optional workload. */
public final class Activator implements BundleActivator, StartupMonitor {

	static final String BUNDLE_ID = "org.eclipse.pde.xmlstudy.probe";
	private static final long QUIET_MS = 1_000;
	private static final long TIMEOUT_MS = Long.getLong("xml.study.timeoutMs", 60_000L);
	private final QuietWindow quiet = new QuietWindow(TimeUnit.MILLISECONDS.toNanos(QUIET_MS));
	private final AtomicBoolean applicationRunning = new AtomicBoolean();
	private final AtomicBoolean ready = new AtomicBoolean();
	private final AtomicBoolean terminal = new AtomicBoolean();
	private final AtomicBoolean uiDispatchPending = new AtomicBoolean();
	private final List<Map<String, Object>> phases = new ArrayList<>();
	private final Object outputLock = new Object();
	private JobObservation jobs;
	private ScheduledExecutorService observer;
	private ServiceRegistration<StartupMonitor> registration;
	private volatile IWorkbench workbench;
	private volatile int visibleWindows;
	private volatile boolean workloadComplete;
	private volatile Map<String, Object> validation = Map.of();
	private volatile Map<String, Object> diagnostic = Map.of();
	private boolean diagnostics;
	private String scenario;
	private String runId;
	private long probeStartedNanos;
	private String output;
	private boolean fdDiagnostics;

	@Override
	public void start(BundleContext context) {
		if (!Boolean.parseBoolean(System.getProperty("xml.study.enabled", "true"))) {
			return;
		}
		probeStartedNanos = System.nanoTime();
		scenario = System.getProperty("xml.study.scenario", "startup");
		runId = System.getProperty("xml.study.runId", "");
		output = System.getProperty("xml.study.output", "");
		fdDiagnostics = Boolean.getBoolean("xml.study.fdDiagnostics");
		diagnostics = Boolean.getBoolean("xml.study.diagnostics");
		workloadComplete = !List.of("validation", "autobuild", "editors").contains(scenario);
		jobs = new JobObservation(quiet);
		Job.getJobManager().addJobChangeListener(jobs);
		registration = context.registerService(StartupMonitor.class, this, null);
		observer = Executors.newSingleThreadScheduledExecutor(runnable -> {
			Thread thread = new Thread(runnable, "XML study observer");
			thread.setDaemon(true);
			return thread;
		});
		emit("probe_started", Map.of("quietWindowMs", QUIET_MS, "observationTimeoutMs", TIMEOUT_MS));
		if (!List.of("startup", "validation", "autobuild", "editors").contains(scenario)) {
			finish("probe_error", "error", Map.of("error", "Unknown xml.study.scenario: " + scenario));
			return;
		}
		if ("autobuild".equals(scenario)) {
			DiagnosticScenarios.scheduleAutomaticBuild(this);
		}
		long remainingNanos = TimeUnit.MILLISECONDS.toNanos(TIMEOUT_MS) - (System.nanoTime() - probeStartedNanos);
		observer.schedule(this::timeout, Math.max(0, remainingNanos), TimeUnit.NANOSECONDS);
		observer.scheduleWithFixedDelay(this::poll, 0, 100, TimeUnit.MILLISECONDS);
	}

	@Override
	public void update() {
		// Startup updates are intentionally not logged or used as readiness.
	}

	@Override
	public void applicationRunning() {
		if (applicationRunning.compareAndSet(false, true) && !terminal.get()) {
			emit("application_running", Map.of());
			// Queue the first UI check immediately; do not quantize readiness to the poll period.
			poll();
		}
	}

	private void poll() {
		if (terminal.get() || !applicationRunning.get()) {
			return;
		}
		try {
			if (!PlatformUI.isWorkbenchRunning()) {
				return;
			}
			IWorkbench current = PlatformUI.getWorkbench();
			workbench = current;
			Display display = current.getDisplay();
			if (display.isDisposed() || !uiDispatchPending.compareAndSet(false, true)) {
				return;
			}
			display.asyncExec(() -> {
				try {
					observeOnUiThread(current);
				} catch (Exception failure) {
					fail(failure);
				} finally {
					uiDispatchPending.set(false);
				}
			});
		} catch (Exception failure) {
			fail(failure);
		}
	}

	private void observeOnUiThread(IWorkbench current) {
		if (terminal.get() || current.isClosing()) {
			return;
		}
		int visible = 0;
		for (IWorkbenchWindow window : current.getWorkbenchWindows()) {
			Shell shell = window.getShell();
			if (shell != null && !shell.isDisposed() && shell.isVisible()) {
				visible++;
			}
		}
		visibleWindows = visible;
		if (visible == 0 || current.isStarting()) {
			return;
		}
		if (ready.compareAndSet(false, true)) {
			quiet.begin(System.nanoTime());
			emit("workbench_ready", diagnostics ? Map.of("measurement", "startup observation",
					"workspace", DiagnosticScenarios.snapshot(current)) : Map.of("measurement", "startup observation"));
			if ("validation".equals(scenario)) {
				ValidationScenario.schedule(this);
			} else if ("editors".equals(scenario)) {
				try { DiagnosticScenarios.seedEditors(this, current); }
				catch (Exception failure) { fail(failure); return; }
			}
		}
		JobObservation.Snapshot snapshot = jobs.snapshot();
		if (quiet.elapsed(System.nanoTime(), snapshot.blocking(), workloadComplete)) {
			finish(diagnostics ? "background_settled" : "validation_settled", "ok", Map.of("measurement", measurement(),
					"quietWindowMs", QUIET_MS, "quietWindowIncludedInTiming", true,
					"validation", validation, "diagnostic", diagnostic,
					"workspace", diagnostics ? DiagnosticScenarios.snapshot(current) : Map.of()));
		}
	}

	void validationStarted() {
		emit("validation_started", Map.of("measurement", "post-start validation"));
	}

	void validationFinished(Map<String, Object> result) {
		validation = result;
		emit("validation_finished", Map.of("measurement", "post-start validation", "validation", result));
		quiet.activity(System.nanoTime());
		workloadComplete = true;
	}

	void diagnosticPhase(String phase, Map<String, Object> details) {
		emit(phase, details);
	}

	void diagnosticFinished(Map<String, Object> details) {
		diagnostic = details;
		quiet.activity(System.nanoTime());
		workloadComplete = true;
	}

	void fail(Exception failure) {
		finish("probe_error", "error", Map.of("error", failure.getClass().getName() + ": " + failure.getMessage()));
	}

	private void timeout() {
		finish("timeout", "timeout", Map.of("observationTimeoutMs", TIMEOUT_MS,
				"applicationRunningObserved", applicationRunning.get(), "workbenchReadyObserved", ready.get()));
	}

	private String measurement() {
		return switch (scenario) {
		case "validation" -> "post-start validation";
		case "autobuild" -> "startup with a controlled automatic-build trigger";
		case "editors" -> "editor seed after workbench readiness";
		default -> "startup observation";
		};
	}

	private Map<String, Object> event(String phase, Map<String, Object> extra) {
		Map<String, Object> event = new LinkedHashMap<>();
		event.put("phase", phase);
		event.put("scenario", scenario);
		event.put("runId", runId);
		event.put("processId", ProcessHandle.current().pid());
		event.put("jvmUptimeMs", ManagementFactory.getRuntimeMXBean().getUptime());
		event.put("processCpuNs", processCpuNs());
		event.put("cpuCounter", CpuClock.source());
		event.put("probeElapsedMs", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - probeStartedNanos));
		event.put("visibleWindows", visibleWindows);
		event.put("jobs", jobs.snapshot().data());
		if (fdDiagnostics) {
			event.put("fileDescriptors", FdDiagnostics.snapshot());
		}
		event.putAll(extra);
		return event;
	}

	static long processCpuNs() {
		return CpuClock.sample();
	}

	private void emit(String phase, Map<String, Object> extra) {
		synchronized (outputLock) {
			if (terminal.get()) {
				return;
			}
			Map<String, Object> item = event(phase, extra);
			phases.add(item);
			System.out.println("XML_STUDY_PHASE " + Json.encode(item));
			System.out.flush();
		}
	}

	private void finish(String phase, String status, Map<String, Object> extra) {
		if (!terminal.compareAndSet(false, true)) {
			return;
		}
		synchronized (outputLock) {
			Map<String, Object> terminalExtra = new LinkedHashMap<>(extra);
			terminalExtra.put("status", status);
			Map<String, Object> item = event(phase, terminalExtra);
			phases.add(item);
			System.out.println("XML_STUDY_PHASE " + Json.encode(item));
			System.out.flush();
			Map<String, Object> result = new LinkedHashMap<>();
			result.put("formatVersion", 1);
			result.put("status", status);
			result.put("scenario", scenario);
			result.put("runId", runId);
			result.put("measurement", measurement());
			result.put("javaVersion", System.getProperty("java.version"));
			result.put("processId", ProcessHandle.current().pid());
			result.put("cpuCounter", CpuClock.source());
			result.put("fdDiagnostics", fdDiagnostics);
			result.put("quietWindowMs", QUIET_MS);
			result.put("observationTimeoutMs", TIMEOUT_MS);
			result.put("schemaLoadCounters", "not instrumented; job counts are not parse counts");
			result.put("phases", List.copyOf(phases));
			writeResult(result);
		}
		requestClose();
	}

	private void writeResult(Map<String, Object> result) {
		if (output.isBlank()) {
			return;
		}
		try {
			Path destination = Path.of(output).toAbsolutePath();
			Files.createDirectories(destination.getParent());
			Path temporary = Files.createTempFile(destination.getParent(), destination.getFileName().toString(), ".tmp");
			try {
				Files.writeString(temporary, Json.encode(result) + "\n", StandardCharsets.UTF_8);
				Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
			} finally {
				Files.deleteIfExists(temporary);
			}
		} catch (IOException failure) {
			System.err.println("XML_STUDY_OUTPUT_ERROR " + Json.encode(Map.of("error", failure.toString())));
		}
	}

	private void requestClose() {
		IWorkbench current = workbench;
		if (current == null) {
			return;
		}
		Display display = current.getDisplay();
		if (!display.isDisposed()) {
			display.asyncExec(() -> {
				if (!display.isDisposed() && !current.isClosing() && !current.close()) {
					System.err.println("XML_STUDY_CLOSE_REJECTED");
				}
			});
		}
	}

	@Override
	public void stop(BundleContext context) {
		if (observer != null) {
			observer.shutdownNow();
		}
		if (jobs != null) {
			Job.getJobManager().removeJobChangeListener(jobs);
		}
		if (registration != null) {
			registration.unregister();
		}
	}
}
