package org.eclipse.pde.xmlstudy.probe;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.eclipse.core.runtime.IStatus;
import org.eclipse.core.runtime.jobs.IJobChangeEvent;
import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.core.runtime.jobs.JobChangeAdapter;

/** Observes Jobs without touching PDE model/registry services. */
final class JobObservation extends JobChangeAdapter {

	record Snapshot(boolean blocking, Map<String, Object> data) {
	}

	private final QuietWindow quiet;
	private final Object lock = new Object();
	private final Map<String, long[]> totals = new LinkedHashMap<>();
	private long scheduled;
	private long completed;
	private long failed;
	private long cancelled;
	private long unlistedJobKinds;

	JobObservation(QuietWindow quiet) {
		this.quiet = quiet;
	}

	@Override
	public void scheduled(IJobChangeEvent event) {
		note(event, 0);
	}

	@Override
	public void running(IJobChangeEvent event) {
		note(event, 1);
	}

	@Override
	public void done(IJobChangeEvent event) {
		note(event, 2);
	}

	@Override
	public void awake(IJobChangeEvent event) {
		quiet.activity(System.nanoTime());
	}

	@Override
	public void sleeping(IJobChangeEvent event) {
		quiet.activity(System.nanoTime());
	}

	private void note(IJobChangeEvent event, int kind) {
		quiet.activity(System.nanoTime());
		Job job = event.getJob();
		String key = job.getClass().getName() + " | " + job.getName();
		synchronized (lock) {
			if (kind == 0) {
				scheduled++;
			} else if (kind == 2) {
				completed++;
				IStatus result = event.getResult();
				if (result != null && result.matches(IStatus.ERROR)) {
					failed++;
				}
				if (result != null && result.matches(IStatus.CANCEL)) {
					cancelled++;
				}
			}
			long[] counts = totals.get(key);
			if (counts == null && totals.size() < 128) {
				counts = new long[3];
				totals.put(key, counts);
			}
			if (counts == null) {
				unlistedJobKinds++;
			} else {
				counts[kind]++;
			}
		}
	}

	Snapshot snapshot() {
		List<Map<String, Object>> pending = new ArrayList<>();
		int runningCount = 0;
		int waitingCount = 0;
		int sleepingCount = 0;
		int blockingCount = 0;
		for (Job job : Job.getJobManager().find(null)) {
			int state = job.getState();
			if (state == Job.NONE) {
				continue;
			}
			runningCount += state == Job.RUNNING ? 1 : 0;
			waitingCount += state == Job.WAITING ? 1 : 0;
			sleepingCount += state == Job.SLEEPING ? 1 : 0;
			boolean blocks = state == Job.RUNNING || state == Job.WAITING
					|| (state == Job.SLEEPING && delayedBuildOrPdeJob(job));
			blockingCount += blocks ? 1 : 0;
			if (pending.size() < 64) {
				pending.add(Map.of("name", job.getName(), "class", job.getClass().getName(),
						"state", stateName(state), "blocking", blocks));
			}
		}
		Map<String, Object> data = new LinkedHashMap<>();
		data.put("running", runningCount);
		data.put("waiting", waitingCount);
		data.put("sleeping", sleepingCount);
		data.put("blocking", blockingCount);
		data.put("pending", pending);
		data.put("pendingListTruncated", runningCount + waitingCount + sleepingCount > pending.size());
		synchronized (lock) {
			data.put("scheduledSinceProbe", scheduled);
			data.put("completedSinceProbe", completed);
			data.put("failedSinceProbe", failed);
			data.put("cancelledSinceProbe", cancelled);
			List<Map<String, Object>> summaries = new ArrayList<>();
			for (var entry : totals.entrySet()) {
				long[] count = entry.getValue();
				summaries.add(Map.of("job", entry.getKey(), "scheduled", count[0], "started", count[1], "completed", count[2]));
			}
			data.put("observed", summaries);
			data.put("unlistedJobEvents", unlistedJobKinds);
		}
		return new Snapshot(blockingCount > 0, data);
	}

	private static boolean delayedBuildOrPdeJob(Job job) {
		String name = job.getClass().getName();
		return job.getPriority() == Job.BUILD || name.startsWith("org.eclipse.pde.")
				|| name.startsWith("org.eclipse.core.internal.events.AutoBuildJob");
	}

	private static String stateName(int state) {
		return switch (state) {
			case Job.RUNNING -> "RUNNING";
			case Job.WAITING -> "WAITING";
			case Job.SLEEPING -> "SLEEPING";
			default -> "NONE";
		};
	}
}
