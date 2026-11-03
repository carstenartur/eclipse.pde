package org.eclipse.pde.core.tests.internal;

import org.eclipse.pde.core.tests.internal.core.builders.DependencyLoopFinderTest;
import org.eclipse.pde.core.tests.internal.schema.StorageSchemaDescriptorTest;
import org.junit.platform.suite.api.SelectClasses;
import org.junit.platform.suite.api.Suite;

@Suite
@SelectClasses({ //
	DependencyManagerTest.class, //
	DependencyLoopFinderTest.class, //
	StaleDependencyResolutionTest.class, //
	WorkspaceModelManagerTest.class, //
	WorkspaceProductModelManagerTest.class, //
	ModelManagerBackgroundInitializationTest.class, //
	StorageSchemaDescriptorTest.class, //
})
public class AllPDECoreTests {
}
