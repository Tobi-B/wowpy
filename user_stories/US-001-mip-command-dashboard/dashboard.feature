Feature: MiP command dashboard
  As a developer building complex control rules for the MiP
  I want a browser dashboard with a button for every command the MiP understands
  So that I can exercise and observe each function without writing code first

  Background:
    Given the dashboard server is running on localhost
    And I open the dashboard in a browser

  # ---------------------------------------------------------------- connection

  Rule: The dashboard connects to exactly one MiP chosen by the user

    Scenario: Scanning lists nearby MiPs
      Given a MiP named "Mip-52059" is advertising nearby
      When I press "Scan"
      Then within 15 seconds the device list shows "Mip-52059" with its address and RSSI
      And the device list always contains an entry "Mock MiP"

    Scenario: Connecting to a listed device
      Given "Mip-52059" is in the device list
      When I select "Mip-52059" and press "Connect"
      Then the connection indicator shows "Connected to Mip-52059"
      And all command buttons become enabled

    Scenario: Command buttons are disabled while disconnected
      Given I am not connected to any device
      Then every command button is disabled
      And hovering a disabled button shows the hint "Connect to a MiP first"

    Scenario: Unexpected disconnect is shown and buttons are disabled again
      Given I am connected to "Mip-52059"
      When the MiP drops the connection
      Then within 2 seconds the connection indicator shows "Disconnected"
      And every command button is disabled
      And the log contains an entry "disconnected"

    Scenario: Disconnecting on request
      Given I am connected to "Mip-52059"
      When I press "Disconnect"
      Then the connection indicator shows "Disconnected"
      And the device list is still shown so I can reconnect

  # ------------------------------------------------------------------ commands

  Rule: Every documented MiP command is reachable through a button

    Scenario: Commands are grouped by family
      Given I am connected to "Mock MiP"
      Then the page shows a panel for each of these families:
        | family             |
        | LEDs               |
        | Driving            |
        | Position & balance |
        | Sound              |
        | Game modes         |
        | Sensing            |
        | IR                 |
        | System             |
        | Raw                |
      And each documented opcode from the MiP BLE protocol appears as a button in exactly one panel

    Scenario Outline: Pressing a button sends the correctly encoded command
      Given I am connected to "Mock MiP"
      When I set the parameters of "<command>" to <parameters>
      And I press "<command>"
      Then the mock robot receives the bytes <bytes>
      And the log shows a "sent" entry for "<command>" with the bytes <bytes>

      Examples: one sample per family
        | command           | parameters                  | bytes             |
        | Set chest LED     | r=255 g=0 b=128             | 84 FF 00 80       |
        | Flash chest LED   | r=0 g=255 b=0 on=500 off=200| 89 00 FF 00 19 0A |
        | Set head LEDs     | 1=off 2=on 3=slow 4=fast    | 8A 00 01 02 03    |
        | Drive forward     | speed=20 time=700           | 71 14 64          |
        | Turn left         | degrees=90 speed=12         | 73 12 0C          |
        | Stop              |                             | 77                |
        | Get status        |                             | 79                |
        | Play sound        | index=10                    | 06 0A             |
        | Set volume        | level=7                     | 15 07             |
        | Set game mode     | mode=app                    | 76 01             |
        | Get odometer      |                             | 85                |
        | Get software ver. |                             | 14                |

    Scenario: Parameter fields enforce the protocol's ranges
      Given I am connected to "Mock MiP"
      When I enter 31 into the "speed" field of "Drive forward"
      Then the field is marked invalid with the message "0–30"
      And the "Drive forward" button is disabled
      And nothing is sent to the mock robot

    Scenario: Parameter fields show their allowed range and unit
      Given I am connected to "Mock MiP"
      Then the "time" field of "Drive forward" is labelled with "0–1785 ms"
      And the "degrees" field of "Turn left" is labelled with "0–1275 °"

    Scenario: Raw bytes can be sent for undocumented opcodes
      Given I am connected to "Mock MiP"
      When I enter "F0 01 02" into the raw command field
      And I press "Send raw"
      Then the mock robot receives the bytes F0 01 02

    Scenario: Malformed raw input is rejected
      Given I am connected to "Mock MiP"
      When I enter "F0 0G" into the raw command field
      Then the field is marked invalid with the message "hex bytes only, e.g. 84 FF 00 00"
      And the "Send raw" button is disabled

  # -------------------------------------------------------------------- driving

  Rule: Continuous driving keeps the robot moving only while a button is held

    Scenario: Holding a drive button resends the command
      Given I am connected to "Mock MiP"
      When I press and hold "▲" for 500 ms
      Then the mock robot receives the bytes 78 14 00 at least 8 times
      And no two consecutive receipts are more than 50 ms apart

    Scenario: Releasing a drive button stops the robot
      Given I am connected to "Mock MiP"
      And I am holding "▲"
      When I release "▲"
      Then within 50 ms the mock robot receives the bytes 77
      And no further 78 commands are received

    Scenario: Drive speed and turn rate are adjustable
      Given I am connected to "Mock MiP"
      When I set the "speed" slider of "Drive" to 10
      And I set the "turn" slider of "Drive" to -5
      And I press and hold "▲"
      Then the mock robot receives the bytes 78 0A 65

    Scenario: Leaving the page while driving stops the robot
      Given I am connected to "Mock MiP"
      And I am holding "▲"
      When the browser tab loses focus
      Then within 50 ms the mock robot receives the bytes 77

  # ----------------------------------------------------------------------- log

  Rule: Everything the MiP sends back is visible in a live log

    Scenario: Query replies are decoded and named
      Given I am connected to "Mock MiP"
      And the mock robot will answer 79 with "797C02"
      When I press "Get status"
      Then within 1 second the log shows a "received" entry
      And that entry contains the opcode name "Get status"
      And that entry contains the raw bytes 79 7C 02
      And that entry contains the decoded text "battery 100%, upright"

    Scenario: Unsolicited events are logged as they arrive
      Given I am connected to "Mock MiP"
      When the mock robot emits the notification "1D02"
      Then within 1 second the log shows a "received" entry named "Clap detected" with the decoded text "2 claps"

    Scenario: Unknown replies are still logged
      Given I am connected to "Mock MiP"
      When the mock robot emits the notification "F001"
      Then the log shows a "received" entry named "unknown (0xF0)" with the raw bytes F0 01

    Scenario: Log entries carry a timestamp and can be cleared
      Given I am connected to "Mock MiP"
      And the log contains at least one entry
      Then every log entry starts with a timestamp in the form HH:MM:SS.mmm
      When I press "Clear log"
      Then the log is empty

    Scenario: The log keeps the newest entries in view
      Given I am connected to "Mock MiP"
      When 200 notifications arrive
      Then the log shows the newest entry at the bottom without manual scrolling
      And the log holds at most 1000 entries

  # ------------------------------------------------------------------ hardware

  @hardware
  Rule: The dashboard works against a real MiP

    @hardware
    Scenario: Round trip on the real robot
      Given a MiP named "Mip-52059" is powered on and nearby
      When I scan, select "Mip-52059" and connect
      And I set "Set chest LED" to r=255 g=0 b=0 and press it
      Then the robot's chest LED turns red
      When I press "Get status"
      Then the log shows a "received" entry named "Get status" with a battery percentage and position

    @hardware
    Scenario: Hold-to-drive moves the real robot
      Given I am connected to "Mip-52059" and the robot is upright on the floor
      When I press and hold "▲" for 1 second
      Then the robot drives forward for about 1 second
      And it stops when I release the button
