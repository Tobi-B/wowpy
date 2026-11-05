Feature: Edit a custom block's blocks after the fact
  As a developer who builds his own blocks from a stack of blocks
  I want to reopen such a block later and change it
  So that a block can grow instead of being rebuilt from scratch

  Background:
    Given the dashboard server is running on localhost
    And I open the block editor at /blocks in a browser
    And the custom block "Warn and turn" with the parameter "angle" exists,
      built from: chest LED red, play sound 3, turn left by angle

  # ------------------------------------------------------------- the dialog

  Rule: A block made of blocks can be reopened and changed

    Scenario: The list offers editing
      When I look at "Warn and turn" in "My blocks"
      Then it offers "Blöcke bearbeiten" next to "In Python umwandeln" and "Löschen"

    Scenario: Opening shows the block's own stack
      When I choose "Blöcke bearbeiten" on "Warn and turn"
      Then a dialog opens with its own block canvas
      And that canvas contains the three blocks the block is made of
      And the parameter "angle" is available as a block to drop in
      And the program on the main canvas is unchanged

    Scenario: Adding a block to the stack
      Given I am editing "Warn and turn"
      When I append "wait 0.5 s" to the stack and save
      Then blocks/warn-and-turn.json contains the extra block
      And the generated function ends with "await asyncio.sleep(0.5)"
      And every use of the block in the workspace is unchanged

    Scenario: Cancelling discards the change
      Given I am editing "Warn and turn"
      When I append a block and press "Abbrechen"
      Then blocks/warn-and-turn.json is unchanged

    Scenario: The dialog shows the Python the stack generates
      Given I am editing "Warn and turn"
      Then the dialog shows "await mip.turn_left(angle, 12)"
      When I change the turn speed to 20
      Then within 200 ms it shows "await mip.turn_left(angle, 20)"

    Scenario: A shipped block is editable like any other
      When I choose "Blöcke bearbeiten" on "Celebrate" and change the sound to 12
      And I save
      Then blocks/celebrate.json shows that change
      And the file is the only thing that changed

    Scenario: A Python block is not editable as blocks
      Given "Suchlauf" is a Python block
      Then "Blöcke bearbeiten" is not offered for it
      And "Python bearbeiten" is

  # ----------------------------------------------------------- parameters

  Rule: Parameters can be added, renamed and removed

    Scenario: Adding a parameter
      Given I am editing "Warn and turn"
      And the block is used twice in the workspace, with angle 45 and 90
      When I add the parameter "tempo" with default 12 and save
      Then the function signature is "async def warn_and_turn(mip, angle, tempo):"
      And both uses now show a "tempo" socket holding 12
      And their "angle" values are still 45 and 90

    Scenario: Renaming a parameter keeps the values plugged into it
      Given I am editing "Warn and turn"
      And the block is used in the workspace with angle 45
      When I rename "angle" to "winkel" and save
      Then the function signature is "async def warn_and_turn(mip, winkel):"
      And the block's own body uses "winkel"
      And the use in the workspace still holds 45, now labelled "winkel"

    Scenario: Renaming does not break a saved program
      Given the program "test" was saved using "Warn and turn" with angle 45
      When I rename "angle" to "winkel" and save the block
      And I open the program "test"
      Then the block still holds 45

    Scenario: Removing an unused parameter
      Given "Warn and turn" has a parameter "tempo" that no block references
      When I remove "tempo" and save
      Then the signature is "async def warn_and_turn(mip, angle):"
      And the "tempo" socket is gone from every use

    Scenario: Removing a parameter that is still referenced is refused
      Given I am editing "Warn and turn"
      When I remove the parameter "angle" and save
      Then the dialog refuses with a message naming the block that still uses it
      And blocks/warn-and-turn.json is unchanged

    Scenario: A parameter keeps its identity across a rename
      Given blocks/warn-and-turn.json lists its parameters with ids
      When I rename "angle" to "winkel"
      Then the parameter's id is unchanged
      And the socket on every use is keyed by that id, not by the label

    Scenario: Blocks saved before ids existed still work
      Given a blocks/*.json whose parameters have no "id"
      When I open it for editing
      Then each parameter is given an id
      And the block generates and runs exactly as before

  # ---------------------------------------------------------------- safety

  Rule: A block cannot contain itself

    Scenario: The block being edited is not offered in its own canvas
      When I am editing "Warn and turn"
      Then "My blocks" inside the dialog does not list "Warn and turn"

    Scenario: An indirect cycle is refused on save
      Given the block "A" contains the block "B"
      When I edit "B" to contain "A" and save
      Then the dialog refuses with a message naming the cycle
      And neither block is changed

  # ---------------------------------------------------------------- running

  Rule: An edited block takes effect immediately

    Scenario: The change reaches a running program's next run
      Given I am connected to "Mock MiP"
      And a program calls "Warn and turn" with angle 90
      When I edit the block to play sound 7 instead of 3 and save
      And I run the program
      Then the mock robot receives the bytes 06 07
      And it does not receive 06 03

    Scenario: Editing while a program runs does not disturb it
      Given a program using "Warn and turn" is running
      When I open "Blöcke bearbeiten" and save a change
      Then the running program keeps using the code it started with
      And the next run uses the change

  @hardware
  Scenario: An edited block on the real robot
    Given a MiP named "Mip-52059" is connected
    When I add "wait 0.5 s" to "Warn and turn" and run a program that calls it
    Then the robot pauses half a second longer than before
