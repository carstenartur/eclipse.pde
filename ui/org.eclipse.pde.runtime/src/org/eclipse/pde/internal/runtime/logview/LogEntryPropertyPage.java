/*******************************************************************************
 * Copyright (c) 2000, 2003 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials 
 * are made available under the terms of the Common Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/cpl-v10.html
 * 
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/
package org.eclipse.pde.internal.runtime.logview;

import org.eclipse.jface.dialogs.Dialog;
import org.eclipse.pde.internal.runtime.PDERuntimePlugin;
import org.eclipse.swt.SWT;
import org.eclipse.swt.graphics.*;
import org.eclipse.swt.layout.*;
import org.eclipse.swt.widgets.*;
import org.eclipse.ui.dialogs.PropertyPage;

public class LogEntryPropertyPage extends PropertyPage {
	private LogViewLabelProvider labelProvider;

	public LogEntryPropertyPage() {
		labelProvider = new LogViewLabelProvider();
		noDefaultAndApplyButton();
	}
	protected Control createContents(Composite parent) {
		LogEntry entry = (LogEntry) getElement();
		Composite container = new Composite(parent, SWT.NULL);
		GridLayout layout = new GridLayout();
		layout.numColumns = 3;
		container.setLayout(layout);

		Label label = new Label(container, SWT.NULL);
		label.setText(PDERuntimePlugin.getResourceString("LogEntryPropertyPage.date")); //$NON-NLS-1$
		label = new Label(container, SWT.NULL);
		label.setText(entry.getDate());
		GridData gd = new GridData(GridData.FILL_HORIZONTAL);
		gd.horizontalSpan = 2;
		label.setLayoutData(gd);

		label = new Label(container, SWT.NULL);
		label.setText(PDERuntimePlugin.getResourceString("LogEntryPropertyPage.severity")); //$NON-NLS-1$
		label = new Label(container, SWT.NULL);
		label.setImage(labelProvider.getColumnImage(entry, 1));

		label = new Label(container, SWT.NULL);
		gd = new GridData(GridData.FILL_HORIZONTAL);
		label.setText(entry.getSeverityText());
		label.setLayoutData(gd);

		label = new Label(container, SWT.NULL);
		label.setText(PDERuntimePlugin.getResourceString("LogEntryPropertyPage.message")); //$NON-NLS-1$
		gd = new GridData(GridData.VERTICAL_ALIGN_BEGINNING);
		label.setLayoutData(gd);
		label = new Label(container, SWT.WRAP);
		label.setText(entry.getMessage());
		gd =
			new GridData(
				GridData.FILL_HORIZONTAL | GridData.VERTICAL_ALIGN_BEGINNING);
		gd.widthHint = computeWidthLimit(label, 80);
		gd.horizontalSpan = 2;
		label.setLayoutData(gd);

		String stack = entry.getStack();
		if (stack != null) {
			label = new Label(container, SWT.NULL);
			label.setText(PDERuntimePlugin.getResourceString("LogEntryPropertyPage.exception")); //$NON-NLS-1$
			gd = new GridData(GridData.FILL_HORIZONTAL);
			gd.horizontalSpan = 3;
			label.setLayoutData(gd);

			Text text =
				new Text(
					container,
					SWT.MULTI | SWT.V_SCROLL | SWT.H_SCROLL | SWT.BORDER);
			gd = new GridData(GridData.FILL_BOTH);
			gd.horizontalSpan = 3;
			gd.widthHint = 300;
			gd.heightHint = 300;
			text.setLayoutData(gd);
			text.setText(stack);
		}
		return container;
	}
	
	public void dispose() {
		labelProvider.dispose();
		super.dispose();
	}
	
	private int computeWidthLimit(Label label, int nchars) {
		GC gc = new GC(label);
		gc.setFont(label.getFont());
		FontMetrics fontMetrics= gc.getFontMetrics();
		gc.dispose();
		return Dialog.convertWidthInCharsToPixels(fontMetrics, nchars);
	}
}
