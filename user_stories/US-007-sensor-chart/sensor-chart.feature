Feature: Time chart of the sensors
  As a developer testing control rules on the MiP
  I want a time chart of every available sensor, with checkboxes to pick them
  So that I can see how the robot's values move together over time

  Background:
    Given the dashboard server is running on localhost
    And I open the dashboard at / in a browser
    And I am connected to "Mock MiP"

  # ------------------------------------------------------------- the filter

  Rule: Checkboxes decide what is charted

    Scenario: Every chartable sensor has a checkbox
      Then the chart offers checkboxes for:
        | sensor       |
        | Akku         |
        | Lage         |
        | Wegstrecke   |
        | Neigung      |
        | Lautstärke   |
        | Spielmodus   |
        | Radar        |
        | Geste        |
        | Klatschen    |
        | Brust-LED    |
        | Kopf-LEDs    |

    Scenario: Battery and position are ticked to begin with
      When I open the dashboard for the first time
      Then "Akku" and "Lage" are ticked and the rest are not

    Scenario: Ticking a sensor adds its lane
      When I tick "Neigung"
      Then a lane labelled "Neigung" appears below the existing ones
      And it shares the time axis with them

    Scenario: Unticking removes the lane but keeps the data
      Given "Neigung" is ticked and has been recording for 30 seconds
      When I untick it
      Then its lane disappears
      When I tick it again
      Then the lane returns with the 30 seconds it already has

    Scenario: The selection is remembered for next time
      Given I ticked "Neigung" and "Wegstrecke"
      When I reload the page
      Then those two are still ticked

    Scenario: Nothing ticked
      When I untick every sensor
      Then the chart shows "keine Sensoren ausgewählt"
      And the fast poll stops

  # --------------------------------------------------------------- the lanes

  Rule: Each sensor gets a lane that suits it

    Scenario: A numeric lane has its own scale
      Given "Akku" and "Lautstärke" are ticked
      Then the "Akku" lane is scaled 0–100
      And the "Lautstärke" lane is scaled 0–7
      And neither is squashed by the other's range

    Scenario: The odometer scales to what it has seen
      Given "Wegstrecke" is ticked and the values run from 200 to 260 cm
      Then the lane's scale covers that range, not 0 to 260

    Scenario: A low battery is marked in the lane
      Given the mock robot reports 38 %
      Then the "Akku" line is red below the 40 % mark

    Scenario: Position is a band of coloured states
      Given "Lage" is ticked
      When the mock robot reports "upright" for 3 s, then "face down"
      Then the lane shows a green bar 3 s wide followed by an orange one
      And hovering a bar names the state and how long it lasted

    Scenario: Balance wobble is visible as a striped band
      Given "Lage" is ticked
      When the mock robot alternates between "face down on tray" and "on back with kickstand" 8 times in 2 seconds
      Then the "Lage" lane shows 8 alternating bars in that period

    Scenario: Events appear as markers
      Given "Klatschen" and "Geste" are ticked
      When the mock robot emits "1D02" and then "0A0F"
      Then the "Klatschen" lane shows a marker labelled 2
      And the "Geste" lane shows a marker labelled "forward"

    Scenario: The chest LED lane shows the actual colour
      Given "Brust-LED" is ticked
      When I set the chest LED to green
      Then the lane continues in green from that moment

    Scenario: All lanes share one time axis
      Given three sensors are ticked
      Then a vertical line at the same x position crosses all three lanes at the same instant
      And the axis is labelled with the last 60 minutes

  # ------------------------------------------------------------- sampling

  Rule: Only what is charted is polled faster

    Scenario: Ticking a sensor starts a 1 s poll for it
      Given only "Akku" is ticked
      When 10 seconds pass
      Then the mock robot has received 79 about 10 times
      And it has not received 81 at all

    Scenario: Adding a sensor adds its query
      Given only "Akku" is ticked
      When I tick "Neigung" and 10 seconds pass
      Then the mock robot has received 81 about 10 times

    Scenario: Closing the chart returns to the 5 s poll
      Given "Akku" and "Neigung" are ticked
      When I collapse the chart and 10 seconds pass
      Then the mock robot has received 79 about 2 times
      And it has not received 81

    Scenario: Driving still pauses the poll
      Given "Akku" is ticked
      When I press and hold "▲" for 3 seconds
      Then the mock robot receives no 79 while the button is held
      And the lane shows a gap for that period rather than a straight line

    Scenario: A sensor that stops answering leaves a gap
      Given "Neigung" is ticked
      And the mock robot stops answering 81
      When 5 seconds pass
      Then the lane shows a gap
      And the last known value is not repeated forward

    Scenario: Weight is queried only because it is charted
      Given no sensor is ticked
      Then the mock robot never receives 81
      Which is why 0x81 is absent from the ordinary status poll

  # ---------------------------------------------------------------- window

  Rule: The history is bounded and tied to the connection

    Scenario: The window holds an hour
      Given "Akku" is ticked and 2 hours of samples exist
      Then the chart shows the most recent 60 minutes
      And the page stays responsive

    Scenario: Reconnecting clears the chart
      Given the chart holds several minutes of data
      When I disconnect and connect again
      Then every lane starts empty from the moment of connecting

    Scenario: A disconnect ends the lanes rather than flattening them
      Given "Akku" is ticked
      When the robot disconnects
      Then the lane stops at the last sample
      And the area after it is marked as not connected

  @hardware
  Scenario: Watching a real balance attempt
    Given a MiP named "Mip-52059" is connected
    And "Akku", "Lage" and "Neigung" are ticked
    When I stand the robot up and it falls over
    Then the "Lage" lane shows the flips between upright and fallen
    And the "Neigung" lane shows the swing that preceded them
    And the "Akku" lane shows whether the voltage moved while the motors worked
