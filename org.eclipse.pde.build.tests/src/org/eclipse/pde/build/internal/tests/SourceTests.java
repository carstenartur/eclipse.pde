/*******************************************************************************
 * Copyright (c) 2007 IBM Corporation and others. All rights reserved. This
 * program and the accompanying materials are made available under the terms of
 * the Eclipse Public License v1.0 which accompanies this distribution, and is
 * available at http://www.eclipse.org/legal/epl-v10.html
 * 
 * Contributors: IBM Corporation - initial API and implementation
 ******************************************************************************/

package org.eclipse.pde.build.internal.tests;

import java.io.*;
import java.util.*;
import java.util.jar.Manifest;

import junit.framework.Test;
import junit.framework.TestSuite;

import org.eclipse.core.resources.IFile;
import org.eclipse.core.resources.IFolder;
import org.eclipse.core.runtime.Platform;
import org.eclipse.pde.build.tests.BuildConfiguration;
import org.eclipse.pde.build.tests.PDETestCase;
import org.eclipse.update.core.model.FeatureModelFactory;
import org.osgi.framework.FrameworkUtil;

public class SourceTests extends PDETestCase {

	public static Test suite() {
		return new TestSuite(SourceTests.class);
	}

	public void testBug114150() throws Exception {
		IFolder buildFolder = newTest("114150");

		Properties buildProperties = BuildConfiguration.getBuilderProperties(buildFolder);
		Utils.storeBuildProperties(buildFolder, buildProperties);

		runBuild(buildFolder);

		Set entries = new HashSet();
		entries.add("eclipse/features/a.feature.sdk_1.0.0/feature.xml");
		entries.add("eclipse/features/a.feature.source_1.0.0/feature.xml");
		entries.add("eclipse/plugins/a.feature.source_1.0.0/src/a.plugin_1.0.0/src.zip");
		assertZipContents(buildFolder, "I.TestBuild/a.feature.sdk.zip", entries);

		entries.add("eclipse/features/a.feature_1.0.0/feature.xml");
		entries.add("eclipse/plugins/a.plugin_1.0.0.jar");
		assertZipContents(buildFolder, "I.TestBuild/a.feature.zip", entries);
	}

	// test that generated source fragments have a proper platform filter
	public void testBug184517() throws Exception {
		IFolder buildFolder = newTest("184517");
		IFolder features = Utils.createFolder(buildFolder, "features");

		//generate an SDK feature
		Utils.generateFeature(buildFolder, "sdk", new String[] {"org.eclipse.rcp", "org.eclipse.rcp.source"}, null);
		Properties properties = new Properties();
		properties.put("generate.feature@org.eclipse.rcp.source", "org.eclipse.rcp");
		IFolder sdk = features.getFolder("sdk");
		Utils.storeBuildProperties(sdk, properties);

		String os = Platform.getOS();
		String ws = Platform.getWS();
		String arch = Platform.getOSArch();

		//getScriptGenerationProperties sets buildDirectory to buildFolder by default
		properties = BuildConfiguration.getScriptGenerationProperties(buildFolder, "feature", "sdk");
		properties.put("configs", os + "," + ws + "," + arch);
		generateScripts(buildFolder, properties);

		String fragmentName = "org.eclipse.rcp.source." + os + "." + ws + "." + arch;
		IFolder fragment = buildFolder.getFolder("plugins/" + fragmentName);

		// check the manifest for a correct platform filter
		assertResourceFile(fragment, "META-INF/MANIFEST.MF");
		InputStream stream = new BufferedInputStream(fragment.getFile("META-INF/MANIFEST.MF").getLocationURI().toURL().openStream());
		Manifest manifest = new Manifest(stream);
		stream.close();

		String filter = manifest.getMainAttributes().getValue("Eclipse-PlatformFilter");
		assertTrue(filter.length() > 0);
		properties = new Properties();
		properties.put("osgi.os", os);
		properties.put("osgi.ws", ws);
		properties.put("osgi.arch", arch);
		assertTrue(FrameworkUtil.createFilter(filter).match(properties));
	}

	// test that '<' and '>' are properly escaped in generated source feature
	public void testbug184920() throws Exception {
		//the provided resource features/a.feature/feature.xml contains &lt;foo!&gt; 
		//which must be handled properly
		IFolder buildFolder = newTest("184920");

		Properties properties = BuildConfiguration.getScriptGenerationProperties(buildFolder, "feature", "a.feature.sdk");
		generateScripts(buildFolder, properties);

		assertResourceFile(buildFolder, "features/a.feature.source/feature.xml");
		IFile feature = buildFolder.getFile("features/a.feature.source/feature.xml");

		FeatureModelFactory factory = new FeatureModelFactory();
		InputStream stream = new BufferedInputStream(feature.getLocationURI().toURL().openStream());
		try {
			//this will throw an exception if feature.xml is not valid
			factory.parseFeature(stream);
		} finally {
			stream.close();
		}
	}

	// test that source can come before the feature it is based on
	public void testBug179616A() throws Exception {
		IFolder buildFolder = newTest("179616A");
		IFolder bundleFolder = Utils.createFolder(buildFolder, "plugins/a.bundle");
		IFolder sdkFolder = Utils.createFolder(buildFolder, "features/sdk");
		
		Utils.generateBundle(bundleFolder, "a.bundle");
		//add some source to a.bundle
		File src = new File(bundleFolder.getLocation().toFile(), "src/a.java");
		src.getParentFile().mkdir();
		FileOutputStream stream = new FileOutputStream(src);
		stream.write("//L33T CODEZ\n".getBytes());
		stream.close();

		Utils.generateFeature(buildFolder, "rcp", null, new String[] {"a.bundle"});

		Utils.generateFeature(buildFolder, "sdk", new String[] {"rcp.source", "rcp"}, null);
		Properties properties = new Properties();
		properties.put("generate.feature@rcp.source", "rcp");
		Utils.storeBuildProperties(sdkFolder, properties);

		Utils.generateAllElements(buildFolder, "sdk");
		Utils.storeBuildProperties(buildFolder, BuildConfiguration.getBuilderProperties(buildFolder));
		runBuild(buildFolder);

		Set entries = new HashSet();
		entries.add("eclipse/plugins/rcp.source_1.0.0/src/a.bundle_1.0.0/src.zip");
		assertZipContents(buildFolder, "I.TestBuild/eclipse.zip", entries);
	}

	public void testBug179616B() throws Exception {
		IFolder buildFolder = newTest("179616B");
		IFolder bundleFolder = Utils.createFolder(buildFolder, "plugins/a.bundle");
		IFolder singleFolder = Utils.createFolder(buildFolder, "features/single");

		Utils.generateBundle(bundleFolder, "a.bundle");
		File src = new File(bundleFolder.getLocation().toFile(), "src/a.java");
		src.getParentFile().mkdir();
		FileOutputStream stream = new FileOutputStream(src);
		stream.write("//L33T CODEZ\n".getBytes());
		stream.close();

		Utils.generateFeature(buildFolder, "single", null, new String[] {"single.source", "a.bundle"});
		Properties properties = new Properties();
		properties.put("generate.plugin@single.source", "single");
		Utils.storeBuildProperties(singleFolder, properties);

		Utils.generateAllElements(buildFolder, "single");
		Utils.storeBuildProperties(buildFolder, BuildConfiguration.getBuilderProperties(buildFolder));
		runBuild(buildFolder);

		Set entries = new HashSet();
		entries.add("eclipse/plugins/single.source_1.0.0/src/a.bundle_1.0.0/src.zip");
		assertZipContents(buildFolder, "I.TestBuild/eclipse.zip", entries);
	}
}
