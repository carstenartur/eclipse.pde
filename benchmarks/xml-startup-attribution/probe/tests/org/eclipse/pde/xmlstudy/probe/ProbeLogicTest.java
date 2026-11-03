package org.eclipse.pde.xmlstudy.probe;

/** Checks the measurement boundary, without Eclipse mocks or real-time sleeps. */
public final class ProbeLogicTest {

	public static void main(String[] args) {
		QuietWindow gate = new QuietWindow(1_000_000_000L);
		check(!gate.elapsed(20_000_000_000L, false, true), "must not settle before a visible workbench");
		gate.begin(2_000_000_000L);
		check(!gate.elapsed(2_999_999_999L, false, true), "must wait the whole quiet window");
		check(gate.elapsed(3_000_000_000L, false, true), "must settle when the full quiet window completes");
		check(!gate.elapsed(3_000_000_000L, true, true), "a pending job must block settlement");
		check(!gate.elapsed(3_000_000_000L, false, false), "unfinished explicit validation must block settlement");
		gate.activity(3_100_000_000L);
		check(!gate.elapsed(4_000_000_000L, false, true), "new job activity must reset the window");
		check(gate.elapsed(4_100_000_000L, false, true), "must settle after the last job's full quiet window");
		gate.activity(3_500_000_000L);
		check(!gate.elapsed(4_000_000_000L, false, true), "an older concurrent event must not shorten the window");
		System.out.println("ProbeLogicTest: 8 checks passed");
	}

	private static void check(boolean condition, String message) {
		if (!condition) {
			throw new AssertionError(message);
		}
	}
}
