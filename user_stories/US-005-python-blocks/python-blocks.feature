Feature: Editable Python inside my own blocks
  As a developer building complex control rules for the MiP
  I want my own blocks to hold plain Python that I can edit
  So that a block can do what the block language cannot express

  Background:
    Given the dashboard server is running on localhost
    And I open the block editor at /blocks in a browser
    And the custom block "Warn and turn" with the parameter "angle" exists

  # ------------------------------------------------------- writing one from scratch

  Rule: A Python block can be written without any blocks at all

    Scenario: Creating an empty Python block
      When I choose "Neuer Python-Baustein" in "My blocks"
      And I name it "Suchlauf", pick the colour 200 and add the parameter "sekunden" with default 5
      And I enter the body:
        """
        import time
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            await mip.drive(12, 8)
            await asyncio.sleep(0.05)
        await mip.stop()
        """
      And I save
      Then blocks/suchlauf.json exists with "mode": "python"
      And it has no "workspace"
      And "Suchlauf" appears in the "My blocks" category with a "sekunden" socket

    Scenario: A block written from scratch generates and runs
      Given the Python block "Suchlauf" with the parameter "sekunden" exists
      And a program calls it with 1
      Then the generated code contains "async def suchlauf(mip, sekunden):"
      And it contains "await suchlauf(mip, 1)"
      When I run it against the mock robot
      Then the mock robot receives 78 commands and finally the bytes 77

    Scenario: A block written from scratch offers no regeneration
      Given the Python block "Suchlauf" was written from scratch
      Then "Aus Blöcken neu erzeugen" is not offered for it

    Scenario: A new block needs a name and a body
      When I choose "Neuer Python-Baustein" and save without a name
      Then the dialog shows "letters, digits, spaces and dashes only"
      When I give it a name but leave the body empty and save
      Then the dialog shows "der Baustein braucht mindestens eine Zeile"

    Scenario: A new block cannot take an existing block's name
      Given the custom block "Celebrate" exists
      When I create a Python block named "Celebrate"
      Then the dialog shows that the name is already taken
      And blocks/celebrate.json is unchanged

  # ----------------------------------------------------------- the conversion

  Rule: A block made of blocks can be turned into code, once

    Scenario: Converting pre-fills the editor with the block's own code
      When I open "Warn and turn" in "My blocks" and choose "In Python umwandeln"
      Then a code editor opens containing exactly the body that block generated:
        """
        await mip.set_chest_led(255, 0, 0)
        await mip.play_sound(3)
        await mip.turn_left(angle, 12)
        """
      And the parameter "angle" is listed as available in the code
      And a note warns that a loop without "await" freezes the server

    Scenario: After converting, the block is a Python block
      Given I converted "Warn and turn" and saved it unchanged
      Then blocks/warn-and-turn.json has "mode": "python"
      And it still has its "workspace" for provenance
      And "Warn and turn" still appears in the "My blocks" category with its "angle" socket

    Scenario: The generated program is unchanged by a conversion without edits
      Given a program uses "Warn and turn" with angle 45
      When I convert the block and save it unchanged
      Then the generated Python is byte for byte what it was before

    Scenario: Editing the code changes every use
      Given "Warn and turn" is a Python block used twice in the workspace
      When I change "play_sound(3)" to "play_sound(7)" and save
      Then the "Python" tab shows "await mip.play_sound(7)" exactly once, inside warn_and_turn
      And both uses in the workspace are unchanged as blocks

    Scenario: A Python block cannot be converted again
      Given "Warn and turn" is a Python block
      Then "My blocks" offers "Python bearbeiten", not "In Python umwandeln"

    Scenario: A block-mode block is unaffected
      Given the custom block "Celebrate" was never converted
      Then blocks/celebrate.json has no "mode" or "mode": "blocks"
      And it is still generated from its workspace

  # -------------------------------------------------------------- validation

  Rule: Invalid code never reaches a saved block

    Scenario: Broken syntax is refused with the line
      When I edit "Warn and turn" to:
        """
        await mip.set_chest_led(255, 0, 0
        """
      And I save
      Then the dialog shows an error naming line 1
      And blocks/warn-and-turn.json is unchanged

    Scenario: Code that dedents out of the function is refused
      When I edit "Warn and turn" to:
        """
        await mip.stop()
          await mip.stop()
        """
      And I save
      Then the dialog shows an indentation error
      And the block is unchanged

    Scenario: An empty body is refused
      When I clear the code of "Warn and turn" and save
      Then the dialog shows "der Baustein braucht mindestens eine Zeile"

    Scenario: A name that does not exist is accepted at save time
      When I edit "Warn and turn" to use "await mip.flauschen()" and save
      Then the block saves
      But running a program that uses it shows "Error" with "AttributeError"
      And the error is attributed to the block that called it

    Scenario: Validation runs on the server
      Given the browser cannot compile Python
      When I save any code
      Then the editor asks the server to validate it before writing the file

  # --------------------------------------------------------------- generation

  Rule: Python blocks generate like any other function

    Scenario: The body is indented into the function
      Given "Warn and turn" is a Python block with the body "await mip.stop()"
      And a program calls it with angle 90
      Then the generated code contains:
        """
        async def warn_and_turn(mip, angle):
            await mip.stop()
        """
      And it contains "await warn_and_turn(mip, 90)"

    Scenario: Used twice, generated once
      Given a program uses the Python block "Warn and turn" twice
      Then the generated code defines warn_and_turn exactly once

    Scenario: Parameters are plain Python names
      Given "Warn and turn" has the parameters "angle" and "wie oft"
      Then its function signature is "async def warn_and_turn(mip, angle, wie_oft):"

    Scenario: A Python block may use its own imports
      Given "Warn and turn" has the body:
        """
        import random
        await mip.turn_left(random.randint(10, angle), 12)
        """
      Then the generated program compiles
      And running it turns the robot

    Scenario: A Python block may call another custom block's function
      Given the Python block "Doppelt warnen" has the body "await warn_and_turn(mip, 90)"
      And a program uses "Doppelt warnen"
      Then both functions are generated
      And the program runs without a NameError

    Scenario: Saving a program writes the Python block's code into the .py file
      Given a program uses the Python block "Warn and turn"
      When I save the program as "test"
      Then programs/test.py contains the block's hand-written body

    Scenario: The saved program runs without the browser
      Given programs/test.py uses a Python block
      When I run `python -m wowpy.run programs/test.py --mock`
      Then the process exits with code 0

  # ---------------------------------------------------------------- running

  Rule: Running behaves like the rest of the editor

    Scenario: Highlighting stops at the block
      Given a program calls the Python block "Warn and turn"
      When I run it
      Then the "Warn and turn" block is highlighted while its code runs
      And no inner block is highlighted, because there are none

    Scenario: An error inside the code names the calling block
      Given "Warn and turn" has the body "1 / 0"
      When I run a program that calls it
      Then the run indicator shows "Error"
      And the "Warn and turn" block is marked with "division by zero"

    Scenario: Stop still works for code that awaits
      Given "Warn and turn" has the body:
        """
        while True:
            await asyncio.sleep(0.05)
        """
      And the program is running
      When I press "Stop"
      Then within 200 ms the program state is "stopped"
      And the mock robot receives the bytes 77

  # ------------------------------------------------------------ the escape hatch

  Rule: A conversion can be undone from the kept workspace

    Scenario: Regenerating from the blocks discards the code
      Given "Warn and turn" is a Python block with edited code
      When I choose "Aus Blöcken neu erzeugen"
      Then I am warned that the edited code will be lost
      And on confirming, the block is a block-mode block again
      And its body is what the stored workspace generates

    Scenario: Cancelling the regeneration keeps the code
      Given "Warn and turn" is a Python block with edited code
      When I choose "Aus Blöcken neu erzeugen" and cancel
      Then the block is unchanged


  # -------------------------------------------------------------------- risk

  Rule: The freeze hazard is made visible

    Scenario: The dialog warns about loops without await
      When I open the code editor of any Python block
      Then it shows the note "Eine Schleife ohne await blockiert den Server - Stopp wirkt dann nicht mehr."

    Scenario: The generated file carries the same warning
      Given a program uses a Python block
      When I save it
      Then the generated .py file notes that the block's body is hand-written

  @hardware
  Scenario: A Python block on the real robot
    Given a MiP named "Mip-52059" is connected
    And the Python block "Warn and turn" flashes the LED and turns
    When I run a program that calls it with angle 90
    Then the robot flashes its chest LED and turns about 90 degrees
