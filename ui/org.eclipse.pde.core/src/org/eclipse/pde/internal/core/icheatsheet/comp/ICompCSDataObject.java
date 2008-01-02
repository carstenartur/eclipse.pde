/*******************************************************************************
 * Copyright (c) 2006 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/

package org.eclipse.pde.internal.core.icheatsheet.comp;

/**
 * ICompCSDataObject
 *
 */
public interface ICompCSDataObject extends ICompCSObject {

	/**
	 * PCDATA
	 * @param content
	 */
	public void setFieldContent(String content);

	/**
	 * PCDATA
	 * @return
	 */
	public String getFieldContent();

}
