package org.eclipse.pde.xmlstudy.probe;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Method;
import java.time.Duration;

/** Prefer the public HotSpot management interface; /proc CPU data may be absent. */
final class CpuClock {

	private static final Object OS_BEAN = ManagementFactory.getOperatingSystemMXBean();
	private static final Method CPU_TIME = cpuMethod();
	private static volatile String source = "unavailable";

	private CpuClock() {
	}

	private static Method cpuMethod() {
		try {
			Class<?> api = Class.forName("com.sun.management.OperatingSystemMXBean", false, ClassLoader.getPlatformClassLoader());
			return api.isInstance(OS_BEAN) ? api.getMethod("getProcessCpuTime") : null;
		} catch (ReflectiveOperationException | SecurityException unavailable) {
			return null;
		}
	}

	static long sample() {
		if (CPU_TIME != null) {
			try {
				long value = (Long) CPU_TIME.invoke(OS_BEAN);
				if (value >= 0) {
					source = "com.sun.management.OperatingSystemMXBean.getProcessCpuTime";
					return value;
				}
			} catch (ReflectiveOperationException | SecurityException unavailable) {
				// Fall back without reaching into the encapsulated implementation class.
			}
		}
		long value = ProcessHandle.current().info().totalCpuDuration().map(Duration::toNanos).orElse(-1L);
		source = value >= 0 ? "ProcessHandle.Info.totalCpuDuration" : "unavailable";
		return value;
	}

	static String source() {
		return source;
	}
}
