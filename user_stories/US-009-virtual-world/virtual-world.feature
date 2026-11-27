Feature: A virtual robot in a 3D world
  As a developer who wants to program without working hardware
  I want a visible robot in a 3D world that my block programs drive
  So that I can build and try programs with no robot at hand

  Background:
    Given the simulator package is installed
    And a world with a floor and one obstacle 50 cm in front of the robot

  # --------------------------------------------------- the world itself

  Rule: The world runs without a browser

    Scenario: Stepping the world headlessly
      Given no browser is connected
      When I drive the robot forward for 20 cm in stepped time
      Then its position has moved 20 cm along its heading
      And no browser was needed at any point

    Scenario: Stepped time is deterministic
      When I run the same program twice in stepped time
      Then both runs end with the robot in the same position and heading
      And both produce the same sequence of sensor readings

    Scenario: Real time tracks the clock
      When I run a program that waits 2 seconds in real time
      Then the run takes about 2 seconds

  Rule: Driving moves the robot and obstacles stop it

    Scenario: Driving forward
      When the robot drives forward 30 cm
      Then its odometer reads about 30 cm

    Scenario: Turning changes the heading, not the place
      When the robot turns 90 degrees left
      Then its heading has changed by 90 degrees
      And its position is unchanged

    Scenario: Bumping into an obstacle
      When the robot drives forward 100 cm towards the obstacle
      Then it stops at the obstacle rather than passing through it
      And its odometer reads the distance it actually travelled, not 100 cm
      And a bump is reported

  Rule: Sensors read the world

    Scenario: Distance reports the MiP's three classes
      Given the obstacle is 50 cm away
      Then the distance reading is "free"
      When the robot drives 25 cm forward
      Then the distance reading is "object 10-30 cm"
      When the robot drives 15 cm further
      Then the distance reading is "object < 10 cm"

    Scenario: Distance is not more precise than the real sensor
      When I read the distance
      Then the value is one of the three classes
      And no centimetre figure is offered

    Scenario: A simulated robot has no battery
      When I read the simulated robot's capabilities
      Then "battery" is absent
      And the sensor chart offers no battery lane for this robot

  # ------------------------------------------------ as a robot driver

  Rule: The simulated robot is just another robot

    Scenario: A program written for the MiP runs in the world
      Given a program saved for the MiP that drives forward and sets the chest LED
      When I run it against the simulated robot
      Then it runs to completion without modification
      And the robot in the world moved and its chest LED is the colour the program set

    Scenario: The program cannot tell which robot it drives
      When a program reads its robot's capabilities
      Then it sees capability names, not a device name or a transport

    Scenario: Capabilities the world cannot provide are absent
      When I read the simulated robot's capabilities
      Then "sound" is absent
      And a program that plays a sound is refused before it starts, naming "sound"

  # ------------------------------------------------------ the viewer

  Rule: The browser shows the world

    Scenario: Choosing the world as the target
      When I open the block editor
      Then I can choose the virtual world next to the real robot as a run target

    Scenario: Watching a program run
      Given the virtual world is chosen and the viewer is open
      When I run a program that drives forward and turns
      Then the robot in the viewer moves along the same path the world reports
      And each block lights up as it runs, as it does for the real robot

    Scenario: The chest LED is visible
      When the program sets the chest LED to red
      Then the robot in the viewer shows a red chest

    Scenario: Closing the viewer does not stop the program
      Given a program is running in the world
      When I close the viewer
      Then the program runs to completion
      And reopening the viewer shows the robot where the world says it is

    Scenario: Stop halts the robot in the world
      Given a program is driving in the world
      When I press Stop
      Then the robot stops moving within one tick
      And the world reports it stationary
