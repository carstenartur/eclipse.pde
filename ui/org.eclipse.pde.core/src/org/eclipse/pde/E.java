package org.eclipse.pde;
public class E {
	public void bla(String[] shorts) {
		StringBuilder value = new StringBuilder();
		for (int i = 0; i < shorts.length; i++) {
			if (i > 0) {
				value.append(',');
			}
			value.append(shorts[i]);
		}
		System.out.println(value.toString());
	}
}