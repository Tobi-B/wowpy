Feature: Block programming
  As a developer writing complex control rules for the MiP
  I want to program the robot graphically with Blockly-style blocks
  So that I can build and try out behaviours quickly and still get a readable wowpy script

  Background:
    Given the dashboard server is running on localhost
    And I open the block editor at /blocks in a browser

  # -------------------------------------------------------------------- editor

  Rule: The editor offers every robot command and the full control language

    Scenario: Toolbox categories
      Then the toolbox shows these categories in this order:
        | category        |
        | Robot: LEDs     |
        | Robot: Move     |
        | Robot: Sound    |
        | Robot: Body     |
        | Robot: Sensing  |
        | Sensors         |
        | Events          |
        | Control         |
        | Logic           |
        | Math            |
        | Text            |
        | Variables       |
        | Functions       |
        | My blocks       |

    Scenario: Every sendable command from the protocol table has a block
      Then for each command in wowpy.protocol.COMMANDS that is not a query and not "Disconnect app" or "Send IR"
      there is a block in a "Robot:" category whose generated Python calls that command

    Scenario: Block fields carry the protocol's ranges
      When I drag a "drive forward" block into the workspace
      Then its speed field only accepts 0–30
      And its time field only accepts 0–1785 ms
      And typing 31 into speed snaps back to 30

    Scenario: The Python tab mirrors the workspace
      When I build: when program starts → chest LED red → wait 1 s → chest LED blue
      Then the "Python" tab shows:
        """
        async def main(mip):
            await mip.set_chest_led(255, 0, 0)
            await asyncio.sleep(1)
            await mip.set_chest_led(0, 0, 255)
        """
      And the code updates within 200 ms after any change in the workspace

    Scenario: Status panel and log are shared with the dashboard
      Given I am connected to "Mock MiP" in the dashboard
      When I switch to /blocks
      Then the status panel shows "Connected to Mock MiP"
      And the log panel is present and shows the same entries

  # ------------------------------------------------------------------ running

  Rule: A program runs on the server against the current connection

    Scenario: Running a simple program sends the commands in order
      Given I am connected to "Mock MiP"
      And the workspace contains: when program starts → chest LED red → wait 0.2 s → play sound 3 → stop
      When I press "Run"
      Then the mock robot receives, in order, the bytes 84 FF 00 00, 06 03, 77
      And the second and third command are at least 200 ms apart
      And the run indicator shows "Running" and then "Finished"

    Scenario: The current block is highlighted while running
      Given I am connected to "Mock MiP"
      And the workspace contains: when program starts → wait 1 s → chest LED green
      When I press "Run"
      Then during the first second the "wait" block is highlighted
      And afterwards the "chest LED" block is highlighted
      And no block is highlighted after the program finishes

    Scenario: Run is refused without a connection
      Given I am not connected to any device
      Then the "Run" button is disabled with the hint "Connect to a MiP first"

    Scenario: Stop cancels the program and stops the robot
      Given I am connected to "Mock MiP"
      And the workspace contains: when program starts → forever → drive continuously 2 s at speed 20
      And the program is running
      When I press "Stop"
      Then within 200 ms the mock robot receives the bytes 77
      And no further commands are received
      And the run indicator shows "Stopped"

    Scenario: Continuous drive never outlives its block
      Given I am connected to "Mock MiP"
      And the workspace contains: when program starts → drive continuously 0.5 s at speed 20 turn 0
      When I press "Run"
      Then the mock robot receives the bytes 78 14 00 at least 8 times within 500 ms
      And then receives the bytes 77
      And the program finishes

    Scenario: A disconnect stops a running program
      Given I am connected to "Mock MiP"
      And a program with "forever → wait 0.1 s" is running
      When the mock robot drops the connection
      Then within 500 ms the run indicator shows "Stopped (disconnected)"

    Scenario: A runtime error is shown at the offending block
      Given I am connected to "Mock MiP"
      And the workspace contains: when program starts → set variable x to 0 → play sound (10 / x)
      When I press "Run"
      Then the run indicator shows "Error"
      And the "play sound" block is marked with a red warning containing "division by zero"
      And the log contains an "error" entry with the same text

  # ------------------------------------------------------------ events & sensors

  Rule: Event hats react to notifications and sensor blocks read live values

    Scenario: Clap event starts its stack
      Given I am connected to "Mock MiP"
      And the workspace contains: when clapped → chest LED yellow
      And the program is running
      When the mock robot emits the notification "1D02"
      Then within 200 ms the mock robot receives the bytes 84 FF FF 00

    Scenario: Position event with a specific position
      Given I am connected to "Mock MiP"
      And the workspace contains: when position becomes "face down" → play sound 5
      And the program is running
      When the mock robot emits the notification "797901"
      Then within 200 ms the mock robot receives the bytes 06 05
      When the mock robot emits the notification "797902"
      Then no further commands are received

    Scenario: Every-t-seconds hat repeats until stopped
      Given I am connected to "Mock MiP"
      And the workspace contains: every 0.2 s → play sound 1
      And the program is running
      When 1 second passes
      Then the mock robot has received the bytes 06 01 at least 4 times
      When I press "Stop"
      Then no further commands are received

    Scenario: Sensor values feed conditions
      Given I am connected to "Mock MiP"
      And the mock robot answers 79 with "795502"
      And the workspace contains: when program starts → if battery % < 40 → chest LED red, else → chest LED green
      When I press "Run"
      Then the mock robot receives the bytes 84 FF 00 00

    Scenario: The generated code for sensors reads the shared status
      Given the workspace contains: when program starts → set variable b to battery %
      Then the "Python" tab contains "b = await sensors.battery()"

  # -------------------------------------------------------- Blockly functions

  Rule: Blockly's own Functions blocks become Python functions

    Scenario: A function definition and its call generate code
      Given the workspace contains a function "blinken" with the parameter "wie oft"
      And its body repeats "wie oft" times: chest LED red, wait 0.1 s, chest LED off
      And "when program starts" calls blinken with 3
      Then the "Python" tab contains "async def blinken(mip, wie_oft):"
      And it contains "await blinken(mip, 3)"
      And running it against the mock robot sends three red/off LED pairs

    Scenario: A function with a return value
      Given the workspace contains a function "doppelt" with parameter "x" returning x * 2
      Then the "Python" tab contains "async def doppelt(mip, x):" and "return (x * 2)"

    Scenario: A call placed above its definition still resolves
      Given "when program starts" calls "spaeter" and the definition sits below it
      Then the generated code defines and calls "spaeter" without error

    Scenario: A function named like the program entry point does not shadow it
      Given the workspace contains a function named "main"
      Then the generated code keeps "async def main(mip):" as the program
      And the user's function is generated under a different name

    Scenario: Variable names come from the workspace, not from Blockly's ids
      Given a function whose parameter is used inside its body
      Then the generated body uses the parameter's name, not its Blockly id
      And running the program does not raise a NameError

    Scenario: An empty argument socket is filled with a visible default
      Given the workspace contains a function "piepen" with the parameter "wie oft"
      When I drag a "piepen" call into "when program starts"
      Then its argument socket shows a grey default value
      And the generated code passes that value instead of "None"

    Scenario: Any other empty socket is called out before running
      Given an "if" block without a condition
      Then the editor shows "1 block has an empty socket (controls_if)"
      And the hint explains that an empty socket becomes "None" and stops the program

  # ------------------------------------------------------------- custom blocks

  Rule: Blocks can be composed from other blocks and reused

    Scenario: Shipped composite blocks are available
      Then the "My blocks" category contains at least:
        | block               |
        | Celebrate           |
        | Patrol              |
        | Look around         |
        | Alarm               |
        | Stand up and centre |
      And each of them has a definition file in blocks/

    Scenario: Make a block from a selection
      Given the workspace contains the stack: chest LED red → play sound 3 → turn left 90
      When I select the stack and choose "Make a block from selection"
      And I name it "Warn and turn" and pick the colour 20
      And I promote the field "degrees" of "turn left" to a parameter named "angle"
      And I confirm
      Then the stack in the workspace is replaced by a "Warn and turn" block with an "angle" input set to 90
      And "Warn and turn" appears in the "My blocks" category
      And the file blocks/warn-and-turn.json exists
      And the "Python" tab contains:
        """
        async def warn_and_turn(mip, angle):
            await mip.set_chest_led(255, 0, 0)
            await mip.play_sound(3)
            await mip.turn_left(angle, 12)
        """

    Scenario: A custom block can be used several times with different parameters
      Given the custom block "Warn and turn" with parameter "angle" exists
      And the workspace contains: when program starts → Warn and turn(angle 45) → Warn and turn(angle 180)
      And I am connected to "Mock MiP"
      When I press "Run"
      Then the mock robot receives, among others, the bytes 73 09 0C and then 73 24 0C

    Scenario: Editing a custom block updates all uses
      Given the custom block "Warn and turn" exists and is used twice in the workspace
      When I open "Warn and turn" for editing and change "play sound 3" to "play sound 7"
      And I save the block
      Then the "Python" tab shows "await mip.play_sound(7)" exactly once, inside warn_and_turn
      And both uses in the workspace are unchanged as blocks

    Scenario: Custom blocks may contain other custom blocks
      Given the custom block "Warn and turn" exists
      When I make a block "Double warn" from the stack: Warn and turn(90) → Warn and turn(90)
      Then "Double warn" appears in "My blocks"
      And its generated function calls warn_and_turn twice

    Scenario: Deleting a custom block that is still in use is refused
      Given the custom block "Warn and turn" is used in the workspace
      When I choose "Delete block" on "Warn and turn"
      Then I see the message "Warn and turn is still used 1 time in the workspace"
      And the block still exists

  # ------------------------------------------------------------- persistence

  Rule: Programs are files in the project

    Scenario: Saving a program
      Given the workspace contains: when program starts → chest LED red
      When I press "Save" and enter the name "red light"
      Then the files programs/red-light.json and programs/red-light.py exist
      And programs/red-light.py contains "await mip.set_chest_led(255, 0, 0)"

    Scenario: Loading a program
      Given programs/red-light.json exists
      When I press "Open" and choose "red light"
      Then the workspace shows the blocks from that file
      And the title shows "red light"

    Scenario: Unsaved changes are flagged
      Given the program "red light" is open
      When I add a block
      Then the title shows "red light *"
      And leaving the page asks for confirmation

    Scenario: A saved program runs without the browser
      Given programs/red-light.py exists
      And a MiP or the mock is reachable
      When I run `python -m wowpy.run programs/red-light.py --mock`
      Then the process exits with code 0
      And its output contains "sent Set chest LED [84 FF 00 00]"

    Scenario: Program names are sanitised
      When I press "Save" and enter the name "../etc/passwd"
      Then I see the message "letters, digits, spaces and dashes only"
      And no file is written

  # ------------------------------------------------------------------ hardware

  @hardware
  Scenario: Celebrate on the real robot
    Given a MiP named "Mip-52059" is connected and standing upright
    And the workspace contains: when program starts → Celebrate
    When I press "Run"
    Then the robot's chest LED flashes, it plays a sound and spins once
    And the program finishes without error
