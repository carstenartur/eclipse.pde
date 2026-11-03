package org.eclipse.pde.xmlstudy.instances;

import java.util.Map;

/** Small output-only encoder; no extra bundle is activated to write results. */
final class Json {

	private Json() {
	}

	static String encode(Object value) {
		StringBuilder out = new StringBuilder();
		append(out, value);
		return out.toString();
	}

	private static void append(StringBuilder out, Object value) {
		if (value == null) {
			out.append("null");
		} else if (value instanceof Number || value instanceof Boolean) {
			out.append(value);
		} else if (value instanceof Map<?, ?> map) {
			out.append('{');
			boolean first = true;
			for (var entry : map.entrySet()) {
				if (!first) {
					out.append(',');
				}
				quote(out, entry.getKey().toString());
				out.append(':');
				append(out, entry.getValue());
				first = false;
			}
			out.append('}');
		} else if (value instanceof Iterable<?> values) {
			out.append('[');
			boolean first = true;
			for (Object item : values) {
				if (!first) {
					out.append(',');
				}
				append(out, item);
				first = false;
			}
			out.append(']');
		} else {
			quote(out, value.toString());
		}
	}

	private static void quote(StringBuilder out, String value) {
		out.append('"');
		for (int i = 0; i < value.length(); i++) {
			char c = value.charAt(i);
			switch (c) {
				case '"' -> out.append("\\\"");
				case '\\' -> out.append("\\\\");
				case '\n' -> out.append("\\n");
				case '\r' -> out.append("\\r");
				case '\t' -> out.append("\\t");
				default -> {
					if (c < 0x20) {
						out.append(String.format("\\u%04x", (int) c));
					} else {
						out.append(c);
					}
				}
			}
		}
		out.append('"');
	}
}
