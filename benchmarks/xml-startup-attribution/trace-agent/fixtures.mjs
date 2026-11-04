import fs from 'node:fs';
import path from 'node:path';

/** Two real PDE/Java projects: an extension provider and a dependent consumer. */
export function createFixtures(root) {
 const provider='org.eclipse.pde.xmlstudy.control',consumer='org.eclipse.pde.xmlstudy.consumer';
 for(const name of [provider,consumer]) {
  const project=path.join(root,name);
  for(const dir of ['META-INF','src/control/'+(name===provider?'api':'consumer'),'.settings']) fs.mkdirSync(path.join(project,dir),{recursive:true});
  fs.writeFileSync(path.join(project,'.project'),`<?xml version="1.0"?><projectDescription><name>${name}</name><comment>Explicit XML attribution fixture</comment><projects/><buildSpec><buildCommand><name>org.eclipse.jdt.core.javabuilder</name><arguments/></buildCommand><buildCommand><name>org.eclipse.pde.ManifestBuilder</name><arguments/></buildCommand><buildCommand><name>org.eclipse.pde.SchemaBuilder</name><arguments/></buildCommand></buildSpec><natures><nature>org.eclipse.pde.PluginNature</nature><nature>org.eclipse.jdt.core.javanature</nature></natures></projectDescription>`);
  fs.writeFileSync(path.join(project,'.classpath'),'<?xml version="1.0"?><classpath><classpathentry kind="src" path="src"/><classpathentry kind="con" path="org.eclipse.pde.core.requiredPlugins"/><classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER"/><classpathentry kind="output" path="bin"/></classpath>');
  fs.writeFileSync(path.join(project,'.settings/org.eclipse.jdt.core.prefs'),'eclipse.preferences.version=1\norg.eclipse.jdt.core.compiler.codegen.targetPlatform=21\norg.eclipse.jdt.core.compiler.compliance=21\norg.eclipse.jdt.core.compiler.source=21\n');
  fs.writeFileSync(path.join(project,'build.properties'),'source.. = src/\noutput.. = bin/\nbin.includes = META-INF/,.,plugin.xml'+(name===provider?',schema/':'')+'\n');
  fs.writeFileSync(path.join(project,'META-INF/MANIFEST.MF'),`Manifest-Version: 1.0\nBundle-ManifestVersion: 2\nBundle-Name: XML attribution ${name===provider?'provider':'consumer'}\nBundle-SymbolicName: ${name};singleton:=true\nBundle-Version: 1.0.0\nBundle-RequiredExecutionEnvironment: JavaSE-21\n${name===provider?'Export-Package: control.api':'Require-Bundle: '+provider}\n\n`);
 }
 const providerRoot=path.join(root,provider),consumerRoot=path.join(root,consumer);
 fs.mkdirSync(path.join(providerRoot,'schema'));
 fs.writeFileSync(path.join(providerRoot,'src/control/api/Service.java'),'package control.api; public final class Service { public String value() { return "xml-control"; } }\n');
 fs.writeFileSync(path.join(consumerRoot,'src/control/consumer/Contribution.java'),'package control.consumer; public final class Contribution { public String value() { return new control.api.Service().value(); } }\n');
 fs.writeFileSync(path.join(providerRoot,'plugin.xml'),`<?xml version="1.0"?><?eclipse version="3.4"?><plugin><extension-point id="point" name="Control" schema="schema/control.exsd"/></plugin>`);
 fs.writeFileSync(path.join(consumerRoot,'plugin.xml'),`<?xml version="1.0"?><?eclipse version="3.4"?><plugin><extension point="${provider}.point"><contribution name="control"/></extension></plugin>`);
 fs.writeFileSync(path.join(providerRoot,'schema/control.exsd'),`<?xml version="1.0"?><schema targetNamespace="${provider}" xmlns="http://www.w3.org/2001/XMLSchema"><annotation><appinfo><meta.schema plugin="${provider}" id="point" name="Control"/></appinfo></annotation><element name="extension"><complexType><sequence><element ref="contribution" minOccurs="1" maxOccurs="unbounded"/></sequence><attribute name="point" type="string" use="required"/><attribute name="id" type="string"/><attribute name="name" type="string"/></complexType></element><element name="contribution"><complexType><attribute name="name" type="string" use="required"/></complexType></element></schema>`);
 return providerRoot;
}
