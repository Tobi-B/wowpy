# Sketch only — this story is parked (see story.md).
# The scenarios below fix the intent; they will be worked out properly when
# the story is scheduled, after US-009 has built the world.

Feature: Tasks and goals in the virtual world
  As a developer learning to program the robot
  I want the world to set me a task and judge the result
  So that there is something to solve, not only a place to drive

  Background:
    Given the virtual world from US-009 is available
    And the task "Reach the blue field without touching anything" is loaded

  Rule: A task is a world plus a goal

    Scenario: Loading a task sets up its world
      When I load the task
      Then the world contains the obstacles the task file describes
      And the robot stands at the start the task file describes
      And the goal is shown in the viewer

    Scenario: A task comes from a file
      Then the task is a file alongside the shipped worlds
      And loading it required no code change

  Rule: The world judges the run

    Scenario: Solving it
      When I run a program that reaches the blue field touching nothing
      Then the verdict is "solved"

    Scenario: Missing the goal
      When I run a program that stops 30 cm short of the blue field
      Then the verdict is "not solved"
      And the reason says how far short it stopped

    Scenario: Breaking a condition
      When I run a program that reaches the field but bumps an obstacle
      Then the verdict is "not solved"
      And the reason names the obstacle it touched

    Scenario: The verdict watches, it does not instrument
      Then the program that ran is unchanged by the task
      And the same program run outside a task behaves identically

  Rule: A task can be tried again

    Scenario: Resetting
      Given a finished attempt
      When I reset the task
      Then the robot is back at its start
      And the odometer reads zero
      And the world is exactly as it was before the attempt
