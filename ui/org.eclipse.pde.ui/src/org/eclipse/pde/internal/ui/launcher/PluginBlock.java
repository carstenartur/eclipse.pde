/*******************************************************************************
 * Copyright (c) 2005, 2007 IBM Corporation and others.
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * which accompanies this distribution, and is available at
 * http://www.eclipse.org/legal/epl-v10.html
 *
 * Contributors:
 *     IBM Corporation - initial API and implementation
 *     Ian Bull <irbull@cs.uvic.ca> - bug 204404
 *******************************************************************************/
package org.eclipse.pde.internal.ui.launcher;

import java.util.TreeSet;

import org.eclipse.core.runtime.CoreException;
import org.eclipse.debug.core.ILaunchConfiguration;
import org.eclipse.debug.core.ILaunchConfigurationWorkingCopy;
import org.eclipse.jface.viewers.CheckboxTreeViewer;
import org.eclipse.jface.viewers.StructuredSelection;
import org.eclipse.pde.core.plugin.IPluginAttribute;
import org.eclipse.pde.core.plugin.IPluginElement;
import org.eclipse.pde.core.plugin.IPluginExtension;
import org.eclipse.pde.core.plugin.IPluginModelBase;
import org.eclipse.pde.core.plugin.PluginRegistry;
import org.eclipse.pde.core.plugin.TargetPlatform;
import org.eclipse.pde.internal.core.util.IdUtil;
import org.eclipse.pde.internal.ui.IPDEUIConstants;
import org.eclipse.pde.ui.launcher.AbstractLauncherTab;
import org.eclipse.pde.ui.launcher.EclipseLaunchShortcut;
import org.eclipse.pde.ui.launcher.IPDELauncherConstants;

public class PluginBlock extends AbstractPluginBlock {
	
	protected ILaunchConfiguration fLaunchConfig;

	public PluginBlock(AbstractLauncherTab tab) {
		super(tab);
	}
	
	public void initializeFrom(ILaunchConfiguration config, boolean customSelection) throws CoreException {
		super.initializeFrom(config);
		if (customSelection) {
			initWorkspacePluginsState(config);
			initExternalPluginsState(config);
		} else {
			handleRestoreDefaults();
		}
		enableViewer(customSelection);
		updateCounter();
		fTab.updateLaunchConfigurationDialog();
		fLaunchConfig = config;
		handleFilterButton(); // Once the page is initialized, apply any filtering
	}
	
	/*
	 * if the "automatic add" option is selected, then we save the ids of plugins
	 * that have been "deselected" by the user.
	 * When we initialize the tree, we first set the workspace plugins subtree to 'checked',
	 * then we check the plugins that had been deselected and saved in the config.
	 *
	 * If the "automatic add" option is not selected, then we save the ids of plugins
	 * that were "selected" by the user.
	 * When we initialize the tree, we first set the workspace plugins subtree to 'unchecked',
	 * then we check the plugins that had been selected and saved in the config.
	 */
	protected void initWorkspacePluginsState(ILaunchConfiguration configuration) throws CoreException {
		boolean automaticAdd = configuration.getAttribute(IPDELauncherConstants.AUTOMATIC_ADD, true);		
		fPluginTreeViewer.setSubtreeChecked(fWorkspacePlugins, automaticAdd);
		fNumWorkspaceChecked = automaticAdd ? fWorkspaceModels.length : 0;
		
		String attribute = automaticAdd
							? IPDELauncherConstants.DESELECTED_WORKSPACE_PLUGINS
							: IPDELauncherConstants.SELECTED_WORKSPACE_PLUGINS;
		TreeSet ids = LaunchPluginValidator.parsePlugins(configuration, attribute);
		for (int i = 0; i < fWorkspaceModels.length; i++) {
			String id = fWorkspaceModels[i].getPluginBase().getId();
			if (id == null)
				continue;
			if (automaticAdd && ids.contains(id)) {
				if (fPluginTreeViewer.setChecked(fWorkspaceModels[i], false))
					fNumWorkspaceChecked -= 1;
			} else if (!automaticAdd && ids.contains(id)) {
				if (fPluginTreeViewer.setChecked(fWorkspaceModels[i], true))
					fNumWorkspaceChecked += 1;
			} 
		}			

		fPluginTreeViewer.setChecked(fWorkspacePlugins, fNumWorkspaceChecked > 0);
		fPluginTreeViewer.setGrayed(
			fWorkspacePlugins,
			fNumWorkspaceChecked > 0 && fNumWorkspaceChecked < fWorkspaceModels.length);
	}
	
	protected void initExternalPluginsState(ILaunchConfiguration config)
			throws CoreException {
		fNumExternalChecked = 0;

		fPluginTreeViewer.setSubtreeChecked(fExternalPlugins, false);
		TreeSet selected = LaunchPluginValidator.parsePlugins(config,
								IPDELauncherConstants.SELECTED_TARGET_PLUGINS);
		for (int i = 0; i < fExternalModels.length; i++) {
			if (selected.contains(fExternalModels[i].getPluginBase().getId())) {
				if (fPluginTreeViewer.setChecked(fExternalModels[i], true))
					fNumExternalChecked += 1;
			}
		}

		fPluginTreeViewer.setChecked(fExternalPlugins, fNumExternalChecked > 0);
		fPluginTreeViewer.setGrayed(fExternalPlugins, fNumExternalChecked > 0
				&& fNumExternalChecked < fExternalModels.length);
	}

	protected void savePluginState(ILaunchConfigurationWorkingCopy config) {
		if (isEnabled()) {
			// store deselected projects
			StringBuffer wbuf = new StringBuffer();
			for (int i = 0; i < fWorkspaceModels.length; i++) {
				IPluginModelBase model = fWorkspaceModels[i];
				// if "automatic add" option is selected, save "deselected" workspace plugins
				// Otherwise, save "selected" workspace plugins
				if (fPluginTreeViewer.getChecked(model) != fAddWorkspaceButton.getSelection()) {
					if (wbuf.length() > 0)
						wbuf.append(","); //$NON-NLS-1$
					wbuf.append(model.getPluginBase().getId());
				}
			}
			
			String value = wbuf.length() > 0 ? wbuf.toString() : null;
			if (fAddWorkspaceButton.getSelection()) {
				config.setAttribute(IPDELauncherConstants.DESELECTED_WORKSPACE_PLUGINS, value);
				config.setAttribute(IPDELauncherConstants.SELECTED_WORKSPACE_PLUGINS, (String)null);
			} else {
				config.setAttribute(IPDELauncherConstants.SELECTED_WORKSPACE_PLUGINS, value);
			}
			// Store selected external models
			StringBuffer exbuf = new StringBuffer();
			Object[] checked = fPluginTreeViewer.getCheckedElements();
			for (int i = 0; i < checked.length; i++) {
				if (checked[i] instanceof IPluginModelBase) {
					IPluginModelBase model = (IPluginModelBase) checked[i];
					if (model.getUnderlyingResource() == null) {
						if (exbuf.length() > 0)
							exbuf.append(","); //$NON-NLS-1$
						exbuf.append(model.getPluginBase().getId());
					}
				}
			}
			value = exbuf.length() > 0 ? exbuf.toString() : null;
			config.setAttribute(IPDELauncherConstants.SELECTED_TARGET_PLUGINS, value);
		} else {
			config.setAttribute(IPDELauncherConstants.SELECTED_TARGET_PLUGINS, (String) null);
			config.setAttribute(IPDELauncherConstants.SELECTED_WORKSPACE_PLUGINS, (String) null);
			config.setAttribute(IPDELauncherConstants.DESELECTED_WORKSPACE_PLUGINS, (String)null);
		}
	}

	protected void computeSubset() {
		validateExtensions();
		super.computeSubset();
	}
	
	private void validateExtensions() {
		try {
			if (fLaunchConfig.getAttribute(IPDELauncherConstants.USE_PRODUCT, true)) {
				String product = fLaunchConfig.getAttribute(IPDELauncherConstants.PRODUCT, (String)null);
				if (product != null) {
					validateLaunchId(product);
					String application = getApplication(product);
					if (application != null)
						validateLaunchId(application);
				}
			} 
			else {
				String configType = fLaunchConfig.getType().getIdentifier();
				String attribute = configType.equals(EclipseLaunchShortcut.CONFIGURATION_TYPE)
				? IPDELauncherConstants.APPLICATION : IPDELauncherConstants.APP_TO_TEST;
				String application = fLaunchConfig.getAttribute(attribute, TargetPlatform.getDefaultApplication());
				if (!IPDEUIConstants.CORE_TEST_APPLICATION.equals(application))
					validateLaunchId(application);
			}
		} catch (CoreException e) {
		}
	}
	
	private void validateLaunchId(String launchId) {
		if (launchId != null) {
			int index = launchId.lastIndexOf('.');
			if (index > 0) {
				String pluginId = launchId.substring(0, index);
				// see if launcher plugin is already included
				IPluginModelBase base = findPlugin(pluginId);
				if (base == null) {
					base = PluginRegistry.findModel(pluginId);
					if (base != null) {
						fPluginTreeViewer.setChecked(base, true);
					}
				}
			}
		}
	}
	
	private String getApplication(String product) {
		String bundleID = product.substring(0, product.lastIndexOf('.'));
		IPluginModelBase model = findPlugin(bundleID);
		
		if (model != null) {
			IPluginExtension[] extensions = model.getPluginBase().getExtensions();
			for (int i = 0; i < extensions.length; i++) {
				IPluginExtension ext = extensions[i];
				String point = ext.getPoint();
				if ("org.eclipse.core.runtime.products".equals(point)  //$NON-NLS-1$
						&& product.equals(IdUtil.getFullId(ext))) { 
					if (ext.getChildCount() == 1) {
						IPluginElement prod = (IPluginElement)ext.getChildren()[0];
						if (prod.getName().equals("product")) { //$NON-NLS-1$
							IPluginAttribute attr = prod.getAttribute("application"); //$NON-NLS-1$
							return attr != null ? attr.getValue() : null;
						}
					}
				}
			}
		}
		return null;
	}
	
	protected LaunchValidationOperation createValidationOperation() {
		return new EclipsePluginValidationOperation(fLaunchConfig);
	}

	protected void refreshTreeView(CheckboxTreeViewer treeView) {
		treeView.setSelection(StructuredSelection.EMPTY);
	}
}
