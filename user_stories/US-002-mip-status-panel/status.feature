Feature: MiP status panel
  As a developer testing control rules on the MiP
  I want the dashboard to show the robot's current state at a glance
  So that I can see the effect of my commands and catch problems without reading the raw log

  Background:
    Given the dashboard server is running on localhost
    And I open the dashboard in a browser

  # ---------------------------------------------------------------- connection

  Rule: Connection state is always visible

    Scenario: Panel shows disconnected state before connecting
      Given I am not connected to any device
      Then the status panel shows connection "Disconnected"
      And every other status field shows "—"

    Scenario: Panel shows connecting state
      Given "Mip-52059" is in the device list
      When I select "Mip-52059" and press "Connect"
      Then the status panel shows connection "Connecting…" until the link is up
      And then shows connection "Connected to Mip-52059" with its address

    Scenario: Signal strength from the scan is shown
      Given "Mip-52059" was listed with RSSI -78
      When I connect to "Mip-52059"
      Then the status panel shows signal "-78 dBm" with 2 of 4 bars

    Scenario: Panel stays visible while scrolling
      Given I am connected to "Mock MiP"
      When I scroll to the bottom of the command panels
      Then the status panel is still fully visible

  # ------------------------------------------------------------------- polling

  Rule: Queried values are refreshed automatically while connected

    Scenario: Values are populated right after connecting
      Given the mock robot answers 79 with "797C02", 16 with "1604", 82 with "8201", 85 with "85000000C8", 14 with "1417011B01" and 19 with "190103"
      When I connect to "Mock MiP"
      Then within 2 seconds the status panel shows:
        | field            | value            |
        | Battery          | 100 %            |
        | Position         | upright          |
        | Volume           | 4                |
        | Game mode        | app              |
        | Odometer         | 200 cm           |
        | Software version | 2023-01-27 rev 1 |
        | Hardware version | 1 (voice chip 3) |

    Scenario: Status is polled every 5 seconds
      Given I am connected to "Mock MiP"
      When 12 seconds pass
      Then the mock robot has received the bytes 79 at least 3 times
      And the "Last update" field shows a time no older than 5 seconds

    Scenario: Refresh now forces an immediate poll
      Given I am connected to "Mock MiP"
      And the last poll happened 1 second ago
      When I press "Refresh now"
      Then within 500 ms the mock robot receives the bytes 79

    Scenario: Polling pauses while driving
      Given I am connected to "Mock MiP"
      When I press and hold "▲" for 6 seconds
      Then the mock robot receives no 79 command while "▲" is held
      And within 5 seconds after releasing "▲" a 79 command is received

    Scenario: Versions are queried only once per connection
      Given I am connected to "Mock MiP"
      When 30 seconds pass
      Then the mock robot has received the bytes 14 exactly once
      And the mock robot has received the bytes 19 exactly once

    Scenario: A poll that gets no reply does not break the panel
      Given I am connected to "Mock MiP"
      And the mock robot stops answering 79
      When 10 seconds pass
      Then the Battery and Position fields keep their last known values
      And the "Last update" field shows the time of the last successful poll
      And the log contains a "timeout" entry for "Get status"

  # ------------------------------------------------------------------- battery

  Rule: Battery level is easy to read and warns when low

    Scenario Outline: Raw battery value is converted to a percentage
      Given I am connected to "Mock MiP"
      And the mock robot answers 79 with "79<raw>02"
      When I press "Refresh now"
      Then the status panel shows battery "<percent> %"

      Examples:
        | raw | percent |
        | 4D  | 0       |
        | 65  | 51      |
        | 7C  | 100     |

    Scenario: Low battery is highlighted below 40 %
      Given I am connected to "Mock MiP"
      And the mock robot answers 79 with "795F02"
      When I press "Refresh now"
      Then the status panel shows battery "38 %"
      And the battery bar is red
      And a low-battery warning icon with the hint "MiP may not balance below 40 %" is shown

    Scenario: Battery at or above 40 % is not highlighted
      Given I am connected to "Mock MiP"
      And the mock robot answers 79 with "796002"
      When I press "Refresh now"
      Then the status panel shows battery "40 %"
      And the battery bar is not red
      And no low-battery warning icon is shown

  # -------------------------------------------------------------------- trend

  Rule: The session trend makes slow battery decline and balance wobble visible

    Scenario: Battery history is charted since connect
      Given I am connected to "Mock MiP"
      And the mock robot answers 79 with "796702", then "796602", then "796402"
      When three polls have completed
      Then the trend chart shows a battery line with the points 55 %, 53 %, 49 %
      And the chart's time axis starts at the moment of connecting

    Scenario: Position changes are plotted on the same time axis
      Given I am connected to "Mock MiP"
      When the mock robot emits the notifications "797906", "797902", "797905" 300 ms apart
      Then the trend chart shows three position markers labelled "on back w/ kickstand", "upright", "face down on tray" at those times

    Scenario: Rapid position flips are flagged as balance wobble
      Given I am connected to "Mock MiP"
      When the mock robot emits 8 position notifications alternating "797905" and "797906" within 2 seconds
      Then the "position changes / 5 s" counter shows 8
      And the counter is highlighted as a warning with the hint "balance wobble – check batteries and gyro calibration"

    Scenario: Stable position is not flagged
      Given I am connected to "Mock MiP"
      When the mock robot emits the notification "797902"
      And 5 seconds pass with no further position change
      Then the "position changes / 5 s" counter shows 0 without highlight

    Scenario: Trend is cleared on reconnect
      Given I am connected to "Mock MiP"
      And the trend chart holds at least 3 battery points
      When I press "Disconnect" and connect to "Mock MiP" again
      Then the trend chart is empty except for the first poll after reconnecting

    Scenario: Trend keeps a bounded history
      Given I am connected to "Mock MiP"
      When 2 hours of polling have elapsed
      Then the trend chart shows the most recent 60 minutes
      And the page remains responsive

  # ------------------------------------------------------------------- events

  Rule: Event-driven values update immediately

    Scenario Outline: Position changes are reflected without waiting for a poll
      Given I am connected to "Mock MiP"
      When the mock robot emits the notification "7979<code>"
      Then within 200 ms the status panel shows position "<text>"

      Examples:
        | code | text                     |
        | 00   | on back                  |
        | 01   | face down                |
        | 02   | upright                  |
        | 03   | picked up                |
        | 04   | hand stand               |
        | 05   | face down on tray        |
        | 06   | on back with kickstand   |

    Scenario: Fallen-over robot is highlighted
      Given I am connected to "Mock MiP"
      When the mock robot emits the notification "797901"
      Then the Position field is highlighted as a warning

    Scenario: Setting the chest LED updates the swatch
      Given I am connected to "Mock MiP"
      When I set "Set chest LED" to r=0 g=255 b=0 and press it
      Then the chest LED swatch in the status panel turns green

    Scenario: Resetting the odometer
      Given I am connected to "Mock MiP"
      And the status panel shows odometer "200 cm"
      When I press "Reset" next to the odometer
      Then the mock robot receives the bytes 86
      And the mock robot answers 85 with "8500000000"
      And within 5 seconds the status panel shows odometer "0 cm"

  # ------------------------------------------------------------------ hardware

  @hardware
  Scenario: Live status from the real robot
    Given a MiP named "Mip-52059" is powered on and nearby
    When I connect to "Mip-52059"
    Then within 5 seconds the status panel shows a battery percentage between 0 and 100
    And the position matches how the robot is actually lying
    When I stand the robot upright
    Then within 5 seconds the status panel shows position "upright"
