package org.eclipse.pde.xmlstudy.probe;

/** A monotonic quiet-period gate; independent of Eclipse or wall-clock time. */
final class QuietWindow {

	private final long quietNanos;
	private boolean started;
	private long lastActivity;

	QuietWindow(long quietNanos) {
		this.quietNanos = quietNanos;
	}

	synchronized void begin(long now) {
		started = true;
		lastActivity = now;
	}

	synchronized void activity(long now) {
		lastActivity = Math.max(lastActivity, now);
	}

	synchronized boolean elapsed(long now, boolean blockingJobs, boolean workloadComplete) {
		return started && !blockingJobs && workloadComplete && now - lastActivity >= quietNanos;
	}
}
