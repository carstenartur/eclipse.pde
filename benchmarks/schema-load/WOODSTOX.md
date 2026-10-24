# Woodstox im PDE-Schema-Lesepfad: Auswertung

Stand: 24. Oktober 2026. Empfehlung: **vorerst keinen Produktions-PR für den Providerwechsel eröffnen**. Der isolierte Prototyp beschleunigt den warmen Lesepfad, kostet beim ersten einzelnen Schema aber deutlich zusätzliche CPU, Speicherallokation und Klassenladung. Hinzu kommen zwei neue Laufzeitbundles und eine Änderung der ausgewählten Eclipse-Zielplattform. Die bisherige Messung begründet einen nachvollziehbaren Prototyp, noch keine Umstellung des Standards.

## Was tatsächlich ausgeführt wurde

Gemessen wurde `SchemaDescriptor.getSchema(false)` → `Schema.load()` → `Schema.load(InputStream)` → `XMLDefaultHandler` → `Schema.traverseDocumentTree()`, einschließlich Referenzauflösung, Schema-Modellaufbau, Öffnen/Schließen der JAR-Einträge und der tatsächlich benötigten Includes. Pro Durchlauf werden 49 Schemas aus dem vorhandenen Workbench-Korpus und 15 zusätzlich benötigte Includes geladen; die 49 Hauptmodelle enthalten zusammen 229 Elemente.

Das sind echte PDE-Klassen und der vollständige nicht-abgekürzte Schema-Lesepfad, **kein vollständiger IDE-Start und keine Messung des OSGi-Bundle-Starts**. Der Standalone-Treiber stellt über PDEs bestehende `SchemaProvider`-Schnittstelle die lokalen Include-Dateien bereit. `schema://org.eclipse.core.expressions/...` wird auf die Schema-Dateien des vorhandenen Eclipse-Quellbundles abgebildet. Damit ist keine gestartete IDE-Zielplattform erforderlich. Der abgekürzte Lesepfad mit PDEs globaler `SchemaRegistry` wurde hier nicht neu vermessen.

Basis ist PDE-Commit `081876347068847fff2f06e11f8a945a393d0a79`: Text-Coalescing bereits enthalten, Parser-Wiederverwendung nicht enthalten. Der Woodstox-Prototyp erzeugt für jedes Dokument einen frischen Parser. Er setzt keine globalen XML-Systemeigenschaften.

## Erster Zugriff

20 alternierende JDK/Woodstox-Paare pro Fall, jeweils ein neuer JVM-Prozess. Die Zeitmessung beginnt vor dem ersten Schema-Zugriff; nur URL-Liste und Messinstrumente sind vorher vorbereitet. Sie umfasst Klasseninitialisierung und den tatsächlichen Lesevorgang, jedoch nicht den Start des JVM-Prozesses. JDK 25, ein fest zugewiesener Prozessor (CPU 0), `-Xms512m -Xmx512m -XX:+UseSerialGC -XX:ActiveProcessorCount=1`. Die Dateien lagen im Betriebssystem-Cache; dies ist keine Messung einer kalten Festplatte.

| Erster Zugriff | JDK CPU, Median | Woodstox CPU, Median | Median der gepaarten CPU-Differenzen | JDK / Woodstox Wall-Time, Median |
|---|---:|---:|---:|---:|
| `views.exsd`, 1 Schema | 102,49 ms | 138,70 ms | +36,93 ms | 228,56 / 314,78 ms |
| `menus.exsd`, 1 Schema + 1 Include | 119,85 ms | 155,19 ms | +34,86 ms | 284,76 / 351,45 ms |
| 49 Schemas + 15 Includes | 248,69 ms | 262,39 ms | +11,24 ms | 622,59 / 636,50 ms |

Bei den beiden Einzelzugriffen war Woodstox in allen 20 Paaren CPU-seitig langsamer. Ein einfacher Bootstrap der gepaarten Median-Differenzen ergibt ungefähr +31,0 bis +45,2 ms für `views.exsd` und +29,3 bis +39,9 ms für `menus.exsd` (95%-Intervalle). Beim vollständigen ersten Batch reicht das Intervall von −8,9 bis +23,7 ms: **kein verlässlich nachgewiesener Vorteil beim ersten Batch**, aber auch kein statistisch klarer Batch-Rückschritt.

Bei `views.exsd` wurden beim JDK 319 und bei Woodstox 452 zusätzliche Klassen geladen: **133 zusätzliche Klassen**. Die gemessene Allokation stieg von rund 5,09 MB auf 7,23 MB. Dies ist allokierter Speicher auf dem ausführenden Thread, keine Aussage über dauerhaft belegten Heap.

Rohdaten: `woodstox-first-use.csv` (120 Prozesse). Zusammenfassung und Unsicherheitsrechnung: `woodstox-first-use-summary.json`.

## Warmer Durchsatz

Die abschließende gemeinsame JMH-Serie verwendete pro Fall drei JVM-Forks, 8 × 2 s Aufwärmphase und 6 × 1 s Messung; die Reihenfolge der sieben Vergleichsfälle wurde zwischen den Forks gedreht. Der relevante Providervergleich nutzt auf beiden Seiten den Coalescing-Handler, frische Parser, Originaldateien und den vollständigen Modellaufbau einschließlich Includes.

| Provider | CPU pro 49-Schema-Batch, Mittel | Spannweite der drei Fork-Mittel | Allokation pro Batch |
|---|---:|---:|---:|
| JDK, Coalescing | 13,56 ms | 12,55–14,91 ms | 8,19 MB |
| Woodstox, Coalescing | 8,99 ms | 8,69–9,45 ms | 6,08 MB |

Das sind in dieser Messung etwa **33,7 % weniger CPU** beziehungsweise **4,57 ms Ersparnis pro warmem Batch**. Woodstox ist damit ein klarer Durchsatzkandidat. Der gewonnene Betrag pro Batch ist jedoch deutlich kleiner als die zusätzliche CPU beim ersten einzelnen Schema; außerdem ist die neue Provider-/Target-Abhängigkeit erforderlich. Eine exakte Amortisationsgrenze wird aus diesen unterschiedlichen Warm- und Erstzugriffsszenarien nicht abgeleitet.

Die frühere Serie mit nur 4 × 1 s Aufwärmphase bleibt als Pilot unter `woodstox-validation/jmh-*.json` erhalten und wird nicht für diese Schlussfolgerung verwendet. Maßgeblich sind die finale Vergleichsserie und `xml-followup-benchmark/woodstox-first-use-summary.json`; deren Dateien werden mit dem Gesamtbericht archiviert.

Die JMH-`AuxCounters` summieren in dieser Konfiguration die berichteten Getter-Werte im `score`-Feld. Die Mittelwerte wurden deshalb aus `secondaryMetrics.*.rawData` berechnet, nicht aus dem summierten `score`. Fork-Spannweiten sind keine Konfidenzintervalle.

## Kompatibilität und Absicherung

- Alle 49 Originalschemata ergeben auf beiden Providern denselben SHA-256-Wert ihrer PDE-Modellserialisierung. Für die reine Ausgabeprüfung wird die Schema-Zielversion erst nach dem Lesen auf 3.4 gesetzt; dies liegt außerhalb jeder Zeitmessung.
- Der Korpus lädt auf beiden Providern 229 Hauptelemente und 15 Include-Modelle. Ein zusätzliches Modellfixture prüft Text, CDATA, Entity-Referenz, Kommentargrenzen und Attribute anhand fester Erwartungen.
- Fünf DOCTYPE-Formen werden abgewiesen: einfacher DOCTYPE, interne Entity, Datei-DTD, HTTP-DTD und externe Parameter-Entity. Nach jeder Ablehnung funktioniert ein gültiges Schema. Fehlerhaft geschachteltes XML wird ebenfalls abgewiesen.
- 32 gleichzeitige Ladevorgänge auf vier Threads behalten getrennte Modellnamen.
- Die drei neuen Grenztests plus sechs vorhandene Handler-Tests bestehen für JDK und Woodstox: **9/9**. Entfernt man nur den ablehnenden LexicalHandler, schlägt genau der DOCTYPE-Test fehl: **8/9**. `SUPPORT_DTD=false` allein erhält die bisherige DOCTYPE-Ablehnung somit nicht.
- Ein zusätzlicher Charakterisierungslauf bestätigt das bisherige Schließen des übergebenen `InputStream` bei beiden Providern.

Der Prototyp deaktiviert DTD-Verarbeitung und externe Entities, setzt einen ablehnenden Resolver und weist DOCTYPE über `LexicalHandler.startDTD` ausdrücklich zurück. Die Erstellung des frischen Parsers erfolgt synchronisiert über eine lokale Factory. Dokumenthandler werden ausdrücklich am jeweiligen Reader gesetzt. Parser-Wiederverwendung ist nicht Teil dieses Experiments.

## Zielplattform und Integrationsaufwand

Verwendet wurden **Woodstox 7.3.0** und **Stax2 API 4.3.2**, zusammen **1.822.244 Byte / 1,74 MiB** JAR-Daten, ohne Quellbundles. Diese Versionen sind im bereits verwendeten [Orbit-Milestone S202610121234](https://download.eclipse.org/tools/orbit/simrel/orbit-aggregation/milestone/S202610121234/) vorhanden. Die frühere DOM-Messung verwendete 7.2.0/4.3.0; Zahlen beider Untersuchungen sind deshalb auch aus diesem Grund nicht unmittelbar austauschbar.

Ein echter Tycho-`verify`-Lauf für `org.eclipse.pde.core` mit den neuen Package-Imports scheitert nach 17,6 s bereits bei der Zielplattformauflösung:

```text
Missing requirement: org.eclipse.pde.core 3.21.500.qualifier requires
'java.package; com.ctc.wstx.sax [7.3.0,8.0.0)' but it could not be found
```

Das ist ein konkreter Integrationsblocker: Die ausgewählte `eclipse-sdk-prereqs`-Zielplattform enthält die beiden Bundles noch nicht. Ein Produktionswechsel benötigt deren Auswahl und die Prüfung ihrer Aufnahme in die ausgelieferte PDE/SDK-Konfiguration. Ein bloßer Import im PDE-Manifest reicht nicht. Es wurden keine Zielplattform-, Feature- oder CI-Änderungen vorgenommen. Eine vollständige OSGi-Integration und das volle PDE-Testprogramm sind daher **nicht** als bestanden ausgewiesen.

Die Java-Kompilation des Prototyps gegen die tatsächlichen Abhängigkeiten und die fokussierten Tests sind erfolgreich. Das belegt die eng begrenzte Java-Integration, ersetzt aber die noch ausstehende Zielplattform-/OSGi-Prüfung nicht.

## Separater Befund zum alten kompakten Korpus

`corpus/original/schema/acceleratorConfigurations.exsd:136` enthält im `apiInfo`-Abschnitt einen nur aus Whitespace bestehenden Dokumentationstext. Der alte kompakte Korpus macht daraus `<documentation/>`. `Schema.processSchemaAnnotation()` dereferenziert in Zeile 829 jedoch `child.getFirstChild().getNodeValue()` ohne Nullprüfung. Der vollständige Modellaufbau scheitert dadurch; der reine DOM-Vergleich konnte dies nicht erkennen.

Die ursprünglichen Providerprüfungen verglichen beide Provider jeweils innerhalb derselben Dateivariante. Beide lieferten für die kompakte Datei denselben leeren DOM-Knoten und bestanden damit den Vergleich, ohne die nachfolgende PDE-Modellbildung auszuführen. Kompakte Dateien wurden deshalb aus den neuen Zeitmessungen ausgeschlossen. Der Befund ist unabhängig vom Woodstox-Wechsel. Stacktrace: `woodstox-validation/compact-real-model-failure.log`.

## Reproduzierbarkeit und Stand des Prototyps

Der Prototyp ist in `sources/woodstox/` und `woodstox-prototype.patch` enthalten. Die vollständige Messreihe, Quellenidentitäten und der Vergleich mit Parser-Wiederverwendung stehen im Hauptbericht. Das [Reproduktionspaket](REPRODUCE.md) enthält die exakten Abhängigkeiten, ihre Herkunft und Lizenzhinweise sowie einen relativen Offline-Runner. Anleitung: [REPRODUCE.md](REPRODUCE.md). Alle fünf Implementierungen wurden aus diesem Paket frisch kompiliert; die 735 Modellvergleiche bestanden.

Die Produktions-Zielplattform wurde nicht erweitert. Der Prototyp ist ein Messvergleich und kein zur Integration vorgeschlagener Providerwechsel.
