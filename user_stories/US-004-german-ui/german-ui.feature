# Status: documented only - not scheduled. See story.md.
Feature: German user interface
  As a German-speaking developer
  I want the dashboard and the block editor in German
  So that blocks, buttons and the log read naturally while programming

  # ------------------------------------------------------------- block editor

  Rule: The block editor is German

    Scenario: Toolbox categories
      When I open /blocks
      Then the toolbox shows these categories in this order:
        | category          |
        | Roboter: LEDs     |
        | Roboter: Fahren   |
        | Roboter: Ton      |
        | Roboter: Körper   |
        | Roboter: Sensorik |
        | Sensoren          |
        | Ereignisse        |
        | Ablauf            |
        | Logik             |
        | Mathe             |
        | Text              |
        | Variablen         |
        | Funktionen        |
        | Meine Bausteine   |

    Scenario Outline: Block labels
      When I open the toolbox category "<category>"
      Then it contains a block labelled "<label>"

      Examples:
        | category          | label                                         |
        | Roboter: LEDs     | Brust-LED                                     |
        | Roboter: LEDs     | Kopf-LEDs                                     |
        | Roboter: Fahren   | fahre vorwärts mit Tempo 20 für 700 ms        |
        | Roboter: Fahren   | drehe links um 90 ° mit Tempo 12              |
        | Roboter: Fahren   | anhalten                                      |
        | Roboter: Ton      | spiele Klang 1                                |
        | Roboter: Körper   | steh auf                                      |
        | Sensoren          | Akku %                                        |
        | Sensoren          | Lage                                          |
        | Ereignisse        | wenn das Programm startet                     |
        | Ereignisse        | wenn 2 mal geklatscht wird                    |
        | Ablauf            | warte 1 s                                     |
        | Ablauf            | endlos                                        |

    Scenario: Blockly's own blocks are German too
      When I open the toolbox category "Logik"
      Then the blocks are labelled in German, for example "wenn" and "sonst"

    Scenario: Buttons and hints
      When I open /blocks
      Then the buttons read "▶ Start", "■ Stopp", "Öffnen", "Speichern" and "Baustein aus Auswahl erstellen"
      And the tabs read "Python", "Protokoll" and "Meine Bausteine"
      And while disconnected the start button's hint reads "Zuerst mit einem MiP verbinden"

    Scenario Outline: Run states
      Given the program is in state "<state>"
      Then the editor shows "<text>"

      Examples:
        | state                    | text                      |
        | idle                     | Bereit                    |
        | running                  | Läuft                     |
        | finished                 | Fertig                    |
        | stopped                  | Gestoppt                  |
        | stopped (disconnected)   | Gestoppt (Verbindung weg) |
        | error                    | Fehler                    |

    Scenario: The hint about loose blocks is German
      Given a command block lies outside any event block
      Then the editor shows "1 Baustein hängt an keinem Ereignisblock und wird nicht ausgeführt. Zieh ihn in \"wenn das Programm startet\"."

    Scenario: Dialog for making a block
      When I choose "Baustein aus Auswahl erstellen"
      Then the dialog is titled "Baustein aus Auswahl erstellen"
      And it offers "Name", "Farbe" and "Felder zu Parametern machen"

  # ---------------------------------------------------------------- dashboard

  Rule: The dashboard is German

    Scenario: Status panel labels
      When I open /
      Then the status panel shows the labels "Verbindung", "Signal", "Akku", "Lage",
        "Lagewechsel / 5 s", "Lautstärke", "Spielmodus", "Wegstrecke", "Brust-LED",
        "Kopf-LEDs", "Gesten / Radar", "Klatscherkennung", "Software-Version" and "Hardware-Version"

    Scenario: Connection states
      Then the connection indicator reads "Nicht verbunden", "Verbinde …" or "Verbunden mit <Name>"

    Scenario: Command panels and buttons
      Then the command panels are titled "LEDs", "Fahren", "Lage & Balance", "Ton",
        "Spielmodi", "Sensorik", "Infrarot", "System" and "Rohdaten"
      And the buttons read "Suchen", "Verbinden", "Trennen", "Jetzt aktualisieren" and "Protokoll leeren"

    Scenario: Validation messages
      When I enter 31 into the "Tempo" field of "vorwärts fahren"
      Then the field is marked invalid with the message "0–30"
      When I enter "F0 0G" into the raw command field
      Then the message reads "nur Hex-Bytes, z. B. 84 FF 00 00"

    Scenario: The low-battery warning
      Given the battery is below 40 %
      Then the warning icon's hint reads "MiP balanciert unter 40 % oft nicht mehr"

  # ------------------------------------------------------------------- log

  Rule: The log is German

    Scenario Outline: Decoded replies
      When the robot sends the notification "<hex>"
      Then the log shows "<text>"

      Examples:
        | hex      | text                        |
        | 797C02   | Akku 100 %, aufrecht        |
        | 794D00   | Akku 0 %, auf dem Rücken    |
        | 1D02     | 2 mal geklatscht            |
        | 8201     | App                         |
        | 85000000C8 | 200 cm                    |
        | 0C03     | Objekt < 10 cm              |

    Scenario: Command names in the log
      When I press "Brust-LED setzen"
      Then the log shows a "gesendet" entry named "Brust-LED setzen"
      And the direction column reads "gesendet", "empfangen", "info" or "Fehler"

    Scenario: An unknown reply
      When the robot sends the notification "F001"
      Then the log shows "unbekannt (0xF0)"

  # -------------------------------------------------- values must not change

  Rule: Only labels are translated, never the values programs depend on

    Scenario: A position dropdown keeps its English value
      Given a "wenn die Lage wechselt zu" block set to "auf dem Bauch"
      Then the generated Python contains "position='face down'"
      And it does not contain "auf dem Bauch"

    Scenario: Programs saved before the translation still run
      Given a program saved with the English interface that reacts to position "face down"
      When I open it in the German interface and run it against the mock robot
      Then it behaves exactly as before
      And the block shows the German label "auf dem Bauch"

    Scenario: Generated code stays English
      Given a "Brust-LED" block set to red
      Then the generated Python reads "await mip.set_chest_led(255, 0, 0)"

    Scenario: File names are unaffected
      When I save a program named "rotes Licht"
      Then the files programs/rotes-licht.json and programs/rotes-licht.py exist

    Scenario: The protocol table itself is untouched
      Then wowpy/protocol.py still maps position 1 to "face down"
      And the existing protocol tests pass unchanged
