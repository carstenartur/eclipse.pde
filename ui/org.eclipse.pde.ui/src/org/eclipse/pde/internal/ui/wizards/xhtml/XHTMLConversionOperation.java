/*******************************************************************************
 * Copyright (c) 2005, 2006 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *******************************************************************************/
package org.eclipse.pde.internal.ui.wizards.xhtml;

import java.util.HashSet;
import java.util.Iterator;

import org.eclipse.core.resources.IProject;
import org.eclipse.core.resources.IWorkspaceRunnable;
import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.IProgressMonitor;
import org.eclipse.core.runtime.IStatus;
import org.eclipse.core.runtime.MultiStatus;
import org.eclipse.core.runtime.Status;
import org.eclipse.jface.dialogs.ErrorDialog;
import org.eclipse.osgi.util.NLS;
import org.eclipse.pde.core.IBaseModel;
import org.eclipse.pde.core.plugin.IExtensions;
import org.eclipse.pde.core.plugin.IExtensionsModelFactory;
import org.eclipse.pde.core.plugin.IPluginElement;
import org.eclipse.pde.core.plugin.IPluginExtension;
import org.eclipse.pde.core.plugin.IPluginModelBase;
import org.eclipse.pde.core.plugin.IPluginObject;
import org.eclipse.pde.internal.ui.PDEUIMessages;
import org.eclipse.pde.internal.ui.util.ModelModification;
import org.eclipse.pde.internal.ui.util.PDEModelUtility;
import org.eclipse.pde.internal.ui.wizards.xhtml.TocReplaceTable.TocReplaceEntry;
import org.eclipse.swt.widgets.Shell;


public class XHTMLConversionOperation implements IWorkspaceRunnable {
	
	private class AddDynamicHelpExtensions extends ModelModification {

		private String F_CP_POINT = "org.eclipse.help.contentProducer"; //$NON-NLS-1$
		private String F_LSP_POINT = "org.eclipse.help.base.luceneSearchParticipants"; //$NON-NLS-1$
		private String F_BIND_ELEMENT = "binding"; //$NON-NLS-1$
		private String F_PROD_ATT_NAME = "producerId"; //$NON-NLS-1$
		private String F_PROD_ATT_VALUE = "org.eclipse.help.dynamic"; //$NON-NLS-1$
		private String F_PART_ATT_NAME = "participantId"; //$NON-NLS-1$
		private String F_PART_ATT_VALUE = "org.eclipse.help.base.xhtml"; //$NON-NLS-1$

		public AddDynamicHelpExtensions(IProject project) {
			super(project);
		}

		protected void modifyModel(IBaseModel baseModel, IProgressMonitor monitor) throws CoreException {
			if (!(baseModel instanceof IPluginModelBase))
				return;
			IPluginModelBase model = (IPluginModelBase)baseModel;
			IExtensions ext = model.getExtensions();
			IPluginExtension[] extensions = ext.getExtensions();
			
			boolean contentProducerFound = false;
			boolean luceneSearchParticipantFound = false;
			for (int i = 0; i < extensions.length; i++) {
				String point = extensions[i].getPoint();
				if (point.equals(F_CP_POINT)) {
					contentProducerFound = true;
					ensureExists(extensions[i], F_BIND_ELEMENT, F_PROD_ATT_NAME, F_PROD_ATT_VALUE);
				} else if (point.equals(F_LSP_POINT)) {
					luceneSearchParticipantFound = true;
					ensureExists(extensions[i], F_BIND_ELEMENT, F_PART_ATT_NAME, F_PART_ATT_VALUE);
				}
				if (luceneSearchParticipantFound && contentProducerFound)
					break;
			}
			
			IExtensionsModelFactory factory = model.getFactory();
			if (!contentProducerFound) {
				IPluginExtension extension = factory.createExtension();
				extension.setPoint(F_CP_POINT);
				IPluginElement element = factory.createElement(extension);
				element.setName(F_BIND_ELEMENT);
				element.setAttribute(F_PROD_ATT_NAME, F_PROD_ATT_VALUE);
				extension.add(element);
				model.getPluginBase().add(extension);
			}
			if (!luceneSearchParticipantFound) {
				IPluginExtension extension = factory.createExtension();
				extension.setPoint(F_LSP_POINT);
				IPluginElement element = factory.createElement(extension);
				element.setName(F_BIND_ELEMENT);
				element.setAttribute(F_PART_ATT_NAME, F_PART_ATT_VALUE);
				extension.add(element);
				model.getPluginBase().add(extension);
			}
		}
		
		private void ensureExists(IPluginExtension extension, String elementName, String attrName, String attrValue) throws CoreException {
			IPluginObject[] children = extension.getChildren();
			boolean foundElement = false;
			for (int i = 0; i < children.length; i++) {
				if (children[i] instanceof IPluginElement) {
					IPluginElement element = (IPluginElement)children[i];
					if (element.getName().equals(elementName)) {
						foundElement = attrValue.equals(element.getAttribute(attrName));
						if (foundElement)
							break;
					}
				}
			}
			if (!foundElement) {
				IPluginElement element = extension.getPluginModel().getFactory().createElement(extension);
				element.setName(elementName);
				element.setAttribute(attrName, attrValue);
				extension.add(element);
			}
		}
		
	}
	
	private TocReplaceEntry[] fEntries;
	private Shell fShell;
	private XHTMLConverter fConverter;
	
	public XHTMLConversionOperation(TocReplaceEntry[] entries, Shell shell) {
		fShell = shell;
		fEntries = entries;
		fConverter = new XHTMLConverter(XHTMLConverter.XHTML_TRANSITIONAL);
	}

	public void run(IProgressMonitor monitor) throws CoreException {
		MultiStatus ms = new MultiStatus(
				"org.eclipse.pde.ui", IStatus.OK, //$NON-NLS-1$
				PDEUIMessages.XHTMLConversionOperation_failed, null);
		
		monitor.beginTask(PDEUIMessages.XHTMLConversionOperation_taskName, fEntries.length * 3);
		
		HashSet touchedProjects = new HashSet();
		for (int i = 0; i < fEntries.length; i++)
			convert(fEntries[i], ms, monitor, touchedProjects);
		
		Iterator it = touchedProjects.iterator();
		while (it.hasNext())
			PDEModelUtility.modifyModel(new AddDynamicHelpExtensions((IProject)it.next()), monitor);
		monitor.worked(1);
		
		checkFailed(ms);
	}
	
	private void checkFailed(final MultiStatus ms) {
		if (ms.getChildren().length > 0) {
			fShell.getDisplay().syncExec(new Runnable() {
				public void run() {
					String message;
					if (ms.getChildren().length == 1)
						message = PDEUIMessages.XHTMLConversionOperation_1prob;
					else
						message = NLS.bind(PDEUIMessages.XHTMLConversionOperation_multiProb, Integer.toString(ms.getChildren().length));
					ErrorDialog.openError(fShell, PDEUIMessages.XHTMLConversionOperation_title, message, ms);
				}
			});
		}
	}
	
	private void convert(TocReplaceEntry entry, MultiStatus ms, IProgressMonitor monitor, HashSet touchedProjects) {
		if (monitor.isCanceled())
			return;
		monitor.subTask(NLS.bind(PDEUIMessages.XHTMLConversionOperation_createXHTML, entry.getHref()));
		try {
			fConverter.convert(entry.getEntryFile(), monitor);
			IProject project = entry.getEntryFile().getProject();
			if (!touchedProjects.contains(project))
				touchedProjects.add(project);
		} catch (CoreException e) {
			ms.add(new Status(
					IStatus.WARNING, "org.eclipse.pde.ui",  //$NON-NLS-1$
					IStatus.OK, entry.getTocFile().getName(), e));
		}
	}
	

}
