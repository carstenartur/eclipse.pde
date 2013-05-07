/*******************************************************************************
 * Copyright (c) 2008, 2013 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/
package a.b.c;

/**
 * Tests invalid @noimplement tags on nested inner types
 * @noimplement
 */
public class test3 {

	/**
	 * @noimplement
	 */
	class InnerNoRef4 {
		
	}
	
	/**
	 * @noimplement
	 */
	private class Inner2NoRef4 {
		
	}
	
	class InnerNoRef4_2 {
		
	}
}

class OuterNoRef4 {
	
	/**
	 * @noimplement
	 */
	class InnerNoRef4 {
		
	}
}
