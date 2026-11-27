Feature: One robot interface, the MiP as one driver among several
  As a developer who wants to keep this system when the robot changes
  I want programs, blocks and the dashboard to talk to a robot
  So that another robot can take the MiP's place without a rewrite

  Background:
    Given the dashboard server is running on localhost

  # ------------------------------------------------------- the interface

  Rule: A robot declares what it can do

    Scenario: The MiP driver declares its capabilities
      When I ask the MiP driver for its capabilities
      Then they include "drive", "chest_led", "sound", "distance" and "orientation"
      And every declared capability names the methods it provides

    Scenario: A capability a robot lacks is absent, not empty
      Given a driver that has no battery reading
      When I read its capabilities
      Then "battery" is not among them
      And asking it for a battery value raises a clear error rather than returning 0

    Scenario: The dashboard reports the connected robot's capabilities
      Given the mock MiP is connected
      When I GET /api/capabilities
      Then the response names the robot and lists its capabilities

  Rule: A device keeps its own full command table

    Scenario: The MiP's sixty-odd opcodes survive the abstraction
      Given the mock MiP is connected
      When I GET /api/commands
      Then the command panels still contain "Play sound" with its 106 indexes
      And "Set game mode", "Get status" and "Flash chest LED" are still offered
      And sending one still produces the same bytes as before this story

    Scenario: A command outside the capability set is still sendable
      Given the mock MiP is connected
      When I send the command "Play sound" with index 3
      Then the robot receives the bytes for opcode 0x06

  # ------------------------------------------------- programs and blocks

  Rule: Generated programs address a robot, not a MiP

    Scenario: The generated entry point takes a robot
      Given a workspace with one "drive forward" block
      When I generate the program
      Then it defines "async def main(robot)"
      And the body calls "await robot.drive_for(" rather than "mip."

    Scenario: A program states which capabilities it needs
      Given a workspace that drives and sets the chest LED
      When I generate the program
      Then it records the capabilities "drive" and "chest_led"

  Rule: Hand-written Python keeps working

    Scenario: An existing block body that uses "mip" still runs
      Given the shipped block "Blinkfolge" whose hand-written body calls "mip.set_chest_led"
      When I run a program that uses it against the mock robot
      Then it runs without error
      And the robot receives the chest LED commands in the order the body writes them

    Scenario: Saving a body that uses "mip" warns but is accepted
      When I save a block body that calls "mip.stop()"
      Then the save succeeds
      And the response warns that "mip" is deprecated and "robot" should be used

    Scenario: A new body uses the robot name
      When I save a block body that calls "await robot.stop()"
      Then the save succeeds without a warning

    Scenario: Both names reach the same object
      Given a block body that calls "mip.stop()" and another that calls "robot.stop()"
      When both run against the mock robot
      Then the robot receives one stop command from each

  Rule: A missing capability is refused before anything moves

    Scenario: Running a driving program on a robot that cannot drive
      Given a connected robot without the "drive" capability
      When I run a program that drives
      Then the run is refused before any command is sent
      And the error names the missing capability "drive" and the robot

    Scenario: The editor marks blocks the robot cannot do
      Given a connected robot without the "sound" capability
      When I open the block editor
      Then the "play sound" block is shown as unavailable
      And the reason names the connected robot

  # ----------------------------------------------------- nothing regresses

  Rule: The MiP keeps behaving exactly as before

    Scenario: Every existing test still passes
      When I run the test suite
      Then all tests pass
      And the MiP tests assert the same encoded bytes as before this story

    Scenario: A saved program from before this story still runs
      Given a program saved before this story in programs/
      When I run it against the mock robot
      Then it runs to completion
      And it produces the same sequence of commands as it did before

    Scenario: The sensor chart still samples the same opcodes
      Given the mock MiP is connected
      And "Akku" and "Neigung" are charted
      Then the fast loop still polls 0x79 and 0x81 and nothing else

  @hardware
  Scenario: The real MiP works through the driver
    Given a MiP named "Mip-52059" is connected through the MiP driver
    When I set the chest LED to green through the robot interface
    Then the robot's chest LED turns green
    And reading its orientation returns the position it is actually in
