













VULCAN_FRY User Guide
























Table of Contents

Computer Code Guide	3
Setup	3
Performing the test	3
Maintenance Guide	5
Manual Installation	7
Mechanical Maintenance Schedule	9






























Welcome to the Vulcan Testing Apparatus for the simulation of the ASTM Test. 
Read through this user guide prior to operation of the apparatus.
Computer Code Guide
Setup
This program runs on the raspberry pi 4B and is included on the .img file. The .img is set by default to run this program on startup. If the microSD card has not been imaged yet, or the raspberry pi does not have this behavior on startup, the microSD card can be reimaged with Win32 Disk Imager on a seperate computer
Remove the microSD card from the pi and plug it into the seperate computer.
Download and run Win32 Disk Imager (https://sourceforge.net/projects/win32diskimager/)
Click the blue folder.
Locate the .img file. A copy of the .img file is on the USB flash drive provided by the VULCAN_FRY team.
Click Write.
Once finished, Eject the microSD card and plug it into the pi

Note: Imaging the pi will erase any test data contained on the pi. Move these files
off of the pi if it is possible to do so prior to imaging.
Performing the test
To start the pi, plug in the included USB-C Cable. If it’s connected to power, it should turn on.
Upon being powered, the pi will start up the OS (Gnome), and will autostart the program on startup.
Note the E-Stop button. This will cut power to the oil pumps. Press the E-stop button if they behave unexpectedly. The program will not be affected by the E-stop, so you can finish these steps when its safe to do so. It is recommended that the apparatus is supervised during tests and operation and is ready to hit the e-stop if something goes wrong (Program crash and motors do not deactivate, electrical box smoke, unexpected motor noise, ect).

Be sure the water line is attached and is supplying water to the apparatus. Use a cold water line when possible. Submerge the fryer HX into the fryer being tested. Depending on the fryer a different sized HX may need to be acquired and attached to the apparatus. Locate the loose thermocouple on the apparatus. This is linked to “fryer actual” and will be used to measure fryer oil temperature. Place the tip of the probe into the fryer oil. If during the test “fryer actual” displays as -1, move the probe until the short is resolved, or replace the probe. 

Turn on the fryer being tested and have it set to the desired temperature. Attach the gas meter or wattmeter to the fryer as needed. Note the watt meter can only read one wire at a time. A traditional wall outlet has three such wires (Line, neutral, ground) and would need to be split so the watt meter can read one wire.

This program is designed to stay open as long as the device is powered on. There is no reason to close the program at any point. If the program is accidentally closed by the user or a crash occurs, there are two ways to run it again.
Unpower and repower the pi. Can be done either from the pi itself, the 3 way splitter, or from the wall.
Activities -> Geany -> Build -> Execute. 
This should select the code when opened and will execute the program after following these steps.
If the code window is empty, File -> Open, Locate and open the .py file with the code in the home/Vulcan Directory. This may be named “DevRevUnstable0.1.9.py” or “VulcanFryTestApparatus_Ver_1_0_X.py”. 
Note that running the program this way will also open a terminal window displaying prints, warnings, errors, tracebacks, and exceptions. Never close the terminal first as this will not give the program an opportunity to shut down the motors and flow valve. If this is accidentally done, re-run the program, hit the e-stop, and/or disconnect power to stop the motors and reset the program.

Note that all data collected during an active test will be lost if the program is closed. Data may be lost if the test is ran for particularly long periods of time (Hours or Days) as the list of dictionaries used to store the list may overflow. “dataListMaxLength” attempts to prevent this by only storing the equivalent of the  32-bit integer limit number of entries. Lower this if data loss occurs due to program crash, or raise if it is found to be too few data points. 

The device comes with a 32GB microSD card. This should be more than enough to store several tests as these files average a few MB. After extended use these files should be cleaned up and removed from the pi such that there is space to save new tests. This may result in data loss if the pi is full. Save any important tests to another computer, then delete any .csv files on the system. Never delete .py files as these are used to run the program.

Step 1: Test Parameters
You will be prompted to enter a test name in the first text entry box and a target temperature in the second text entry box. Tap the box to bring up the on-screen keyboard. If the keyboard does not appear, check that on-screen keyboard is turned on in the accessibility settings, located on the top right bar. Look for the person icon. Type in the test name and the target temperature for “fryer actual” to reach (the thermocouple that is placed in the fryer). If the desired target is not listed, modify “TargetTemperatureOptions” in program parameters  of the .py file to add the desired targets. Hit enter on the on-screen keyboard or click the “next” button to advance to the next screen.
Note that the target temperature for the apparatus may not be the same target temperature as the fryer being tested. If the apparatus target is lower than the fryer target, expect the fryer to constantly attempt to heat up. If the inverse is true, the apparatus will most likely be locked to the minimum valve position during the test. If the apparatus has not been recently used, the fryer may cool down significantly even at low valve positions as the barrel has not had a chance to heat up.

Step 2: Verify Parameters
Check that the parameters match what you have entered in the previous screen. Hit start test to advance to the next screen, or cancel to re-enter the test parameters and/or cool the drum.

Step 3: Data Collection
Upon hitting “start test”, the program will attempt to turn on the motors and reach the target temperature. Once the motors are on and target temperature is reached, data collection will begin. To skip reaching the temperature target, click “Skip to data collection”. Some of the data being collected will display on the screen. This is the simple view. To swap to the detailed view and view all collected parameters, click swap to detailed view on the top right. You can freely swap between views this way. 

During tests the time the current test has run will display as Current Test Time. The program will also attempt to automatically match the target temperature by adjusting the control valve in relation to the measured flow rate. Note the minimum valve opening during a test is ~12% (or 66 in range 50-127 in code. Ctrl + F “setValve” and modify if needed).
 
Click End Test to end the current test. The Current Test Time will reset to 0 and the control valve will close, but all other data points will continue to be tracked. "Click to begin the next test." will start a new test, counting a new Current Test Time and operating the control valve again automatically.  "Click to end testing." will end all testing. All data collection will stop at this stage.

Step 3: Saving the File
"Click to pick a file directory to save the test. Program will restart." will bring up a file selection dialog.
Navigate the dialog window and select a location to save the test data. If a file of the same name is already in the directory, a number "(#)" will be added at the end of the file name. After selecting a location, the program will save the data to that directory as a .csv file and restart. "Click to restart program without saving." will restart the program without saving the test data.

Step 4: Accessing the File
If the selected directory was a USB Drive, simply eject the USB stick from the pi and insert into your computer of choice. To access the file on the pi, select activities on the top left. Select Files on the leftmost side of the quick access bar under the desktop with the program. It looks like a file cabinet.
Navigate to the directory you selected earlier.
A web browser can be opened from the quick access bar as well. Select FireFox and navigate to your website of choice for uploading or sharing .csv files. Some websites may crash on the raspberry pi os. Github was used to upload a .csv file to the internet for later use. 

Optional: Drum cooling
To cool the drum, select “Cool Drum” on the file name and target temperature selection screen. This will activate the non-fryer HX motor and open the valve fully, accelerating the cooling of the oil in the barrel. Run as long as needed prior to storage, next test, or draining the drum. 

Note: The message automatic suspension may appear when the program is left idle. Automatic suspension has been disabled on the .img, but this message may still erroneously appear. Tapping on the screen will remove the pop-up.

Notice: Demo mode
A demo mode was created for “replaying” .csv files that were generated during a real test. By default versions of the apparatus code past 1_0_4 have this mode set to false in the program parameters. If for some reason the apparatus is received and is not displaying expected values or time appears to reset during a test, check that “demoMode” in the program .py file is not set to True. If so, change this value to False. If it is desirable to replay the results of a test, change this value to true and input the file directory of the .csv file to replay in “demoPath”. Disconnect the motor power and shut off the water prior to attempting this.
Maintenance Guide
This section is for developers looking to fix/upgrade the program. It is recommended to have a basic understanding of Python 3.13.2 before creating modifications. This program uses GPIO pins to communicate with other boards specialized in collecting data from sensors. The Raspberry Pi 4B has a 40-pin header. The pinout can be found on the Raspberry Pi documentation: (Ctrl + f "GPIO and the 40-pin header") (https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
Here is the default pinout in relation to the device it connects with:

MAX31855 (Octo Board 1.0.2) (Not used in final design)
# Pin # 23, 24, 21, 11, 13, 15
# GPIO # 11, 8, 9, 17, 27, 22
# SCK, CS, S0, T0, T1, T2
# MISO
# Thermocouples wired to this device should be wired from 0 to 7. 
# This is the order the program will register thermocouples relative to the parameters
# If a port can’t be used, the code needs to be modified to skip that port.

MAX31855 (Individual boards 1.0.3)
# Pin # 23, 40, 21, 11, 13, 15, 12, 16, 18
# GPIO # 11, 21, 9, 17, 27, 22, 18, 23, 24
# SCK, CS0, S0, CS1, CS2, CS3, CS4, CS5, CS6
# Import adafruit_max31855 instead of MAX31855

ADS1115 & DS3502
# Pin # 3 5
# GPIO # 2 3
# SDA1, SCL1
# Uses I2C
# ADSAddress = 0x48
# DSAddress = 0x28

Gas Input
# Pin # 31 
# GPIO # 6

Water Input
# Pin # 22
# GPIO # 25

Relay Control
# Pin # 32 33
# GPIO # 12, 13
# Motors 1 and 2

The Thermocouples can be wired to the MAX31855 Octo board. Their port number can be seen on the MAX31855 Board. Ports 0-5 are used in the apparatus, with 2 spare slots. In the program, the numbers currently correspond to the following: 0: "Water Out", 1: "Water In", 2: "HX In", 3: "HX Out", 4: "Fryer HX Out", 5: "Fryer HX In", 6: "Spare 1", 7: "Spare 2" These can be changed in the program parameters. If using this board, use the included MAX31855 .py file. Note in testing the Octo Board has been inaccurate, reporting lower temperatures as 20 degrees higher than expected and takes several minutes to accurately report higher temperatures.

The thermocouples are currently wired to 7 MAX31855 boards. 0: "Fryer HX In", 1: "Water In", 2: "Water Out", 3: "Fryer Actuall", 4: "Fryer HX Out", 5: "HX In", 6: "HX Out", correspond to pins 21, 17, 18, 22, 23, 24, and 27. 2 probes need to be replaced. If a probe is disconnected and was reading temperature data accurately, it will display as -1 in a test. This can be done to identify which probe connects where. With water and motors off, remove the problem probe at the point on the apparatus and at the corresponding MAX31855 board. Replace with a new probe, and verify that the code reflects the location of the probe as expected.

Geany is used to modify and test new versions of the program. It can be found on the quick access bar by selecting activities on the top left and looking under the program desktop. It appears as a genies lamp.
The .img file should load the program .py file by default. It can be found under /home/Vulcan/DevRev0.1.9. Modifications made to the program here will affect the program on the next reboot. It is recommended to use a keyboard and mouse when editing the program directly on the Pi
As the onscreen keyboard will close Geany upon hitting the backspace button, making edits difficult.
Alternatively, copy and paste the latest revision of this program into your code editor of choice. 
The text of the code can either be pasted directly into Geany, or you can replace the file 
with one of an identical name with the new modifications. When running the program on Geany, a terminal window will appear alongside the program which displays any errors, warnings, tracebacks, and exceptions the program experiences. Do not close the terminal window during a test. The motor relays will be locked on and the valve will be locked to its last setting. If this is accidentally done, press the e-stop, execute the program again from Geany, or power cycle the pi so that the program can regain control over the motors and valve.

The program uses a dictionary “params” to control various aspects of the program from one place. This is located just under the program imports. Use Ctrl + F to locate what areas they affect. Additional params can be set by adding to the dictionary and replacing the object in the code with params[“key”][“subkeys”]. Modify these as needed. 

The latest functional rev as of writing is VulcanFryTestApparatus Ver. 1.0.4.py

The program uses Gtk 3.0 to create and load GUI elements. Refer to the Gtk documentation
for more information on how these elements work. (https://python-gtk-3-tutorial.readthedocs.io/en/latest/)

The program uses Adafruit for communication with the MAX31855, ADS1115, and DS3502 boards.
Refer to their respective documentation for how they work. Note that the Octo MAX31855 has its own library separate from Adafruit. Do not use the adafruit_max31855 library with the 1.0.2 version of this program as that version uses the Octo Max31855 board.
MAX31855: (https://github.com/Neem-Tech/Octo-MAX31855-Breakout-Board)
ADS1115: (https://docs.circuitpython.org/projects/ads1x15/en/latest/)
DS3502: (https://docs.circuitpython.org/projects/ds3502/en/latest/)

The program uses many other libraries to perform program functions. Refer to their respective documentation to learn how they work. While the os should log in the user automatically, some changes may require a login.
Username: Vulcan
Password: FrySpring2025

A keyboard extension is used to improve the base keyboard. If it is not installed, use these instructions to do so. https://github.com/nick-shmyrev/improved-osk-gnome-ext
The keyboard should always take up the full width of the screen, but may be missing buttons upon a reboot. Turn the screen keyboard on and off using the accessibility menu on the top right (Person icon) to get the missing buttons, such as ctrl for related copy and paste functions.

The program window may clip out of the screen if the os font size is too big, causing buttons to become inaccessible. The default size has been lowered by default, but this can be adjusted from the GNOME Tweaker. Activities->Quick access bar->Tweaker. (Appears as two switches). Navigate to fonts and adjust the font size. Recommended: 0.8 is recommended for future code iterations to add in auto-resizing of ui elements, should a new screen or alternative window resolution be used. Text markup can also be adjusted in the code (ctrl + f markup).

Manual Installation
To manually install the program onto the Raspberry Pi, you will need the Raspberry Pi Imager v1.8.5 and an internet connection. Format the MicroSD card being used. You may need to use DiskPart to clean the microSD card if the card has previously been used for the Pi.

Step 1: Imaging
Insert the MicroSD card into the computer and open Raspberry Pi Imager v1.8.5. Select device Raspberry Pi 4, Raspberry Pi OS (64-BIT), and the MicroSD card as the storage device. The card provided by the Vulcan Fry team is ~32 GB. Next, edit the settings by setting hostname and username to Vulcan, setting password to FrySpring2025, under the config wireless lan, set SSID and password accordingly, and under services, disable SSH. Click SAVE > YES > YES (This will erase all data on the card if there was any at this stage). Once the Write is complete, eject the microSD card and insert it into the Raspberry Pi 4. It is recommended to remove the GPIO pin attachment during this stage.

Step 2: Terminal Lines
Plug the Pi into the touch screen or use a micro-HDMI cable into another monitor. It is recommended to use a keyboard and mouse for setup. Open the Terminal. This can be found at the top left of the desktop.
Run these commands:
sudo raspi-config
Interface Options > VNC (Disable) & SPI (Enable) & I2C (Enable)
Finish
sudo apt-get remove realvnc-vnc-server
sudo apt-get update
sudo apt-get upgrade
y + enter when prompted
ctrl-c if stuck on "Looking for font path" or connect pi via SSH to seperate computer prior to running sudo apt-get upgrade command.
sudo pip install Adafruit-Blinka --break-system-packages
sudo pip install adafruit-circuitpython-ads1x15 --break-system-packages
sudo pip install adafruit-circuitpython-ds3502 --break-system-packages
sudo pip install adafruit-circuitpython-max31855 --break-system-packages
sudo apt update && sudo apt install xorg gnome gnome-shell --no-install-recommends
y + enter when prompted
enter
Highlight gdm3 and hit enter
sudo pip install Adafruit-Blinka --break-system-packages
sudo pip install adafruit-circuitpython-ads1x15 --break-system-packages
sudo pip install adafruit-circuitpython-ds3502 --break-system-packages
sudo pip install adafruit-circuitpython-max31855 --break-system-packages
Restart the pi

Step 3: OS setup
Click activities.
Unpin all but Files
Pin terminal, web browser of choice (firefox recommended), geany, task manager, settings, tweaker
In Settings:
Power > Screen Blank > Never
Accessibility > Enable Animations (Disable) & Always Show Accessibility Menu (Enable) & Screen Keyboard (Enable)
Users > Unlock > Enter Password > Automatic Login (Enable)
In Tweaker:
Fonts > Scaling Factor (Set to 0.8)
Install the keyboard extension (https://github.com/nick-shmyrev/improved-osk-gnome-ext)
Terminal > sudo apt-get reinstall chrome-gnome-shell (You may need to do this on chromium browsers)
Install and turn extension on. 
Reload website and hit setting
Adjust Landscape Height to 50% or as needed.
Navigate to project github and download VulcanFryTestApparatus_Ver_1_0_4.py
Move these files to the home directory
In the terminal:
mkdir -p ~/.config/autostart
nano ~/.config/autostart/TestApp.desktop
Copy the following:
"""
[Desktop Entry]
Type=Application
Exec=/usr/bin/python3 /home/Vulcan/VulcanFryTestApparatus_Ver_1_0_4.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Vulcan Fry Data Collection Service
Comment=Collects test data according to user input
"""
ctrl s + ctrl x
chmod +x /home/Vulcan/VulcanFryTestApparatus_Ver_1_0_4.py
Restart Pi

The Pi is now set up to run the test program! To update VulcanFryTestApparatus_Ver_1_0_4.py, edit it in Geany or replace the file with one of the same name. To update the name, edit the .desktop file as shown above with the new name.

If important changes are made and a new image file is needed, use Win32 Disk Imager to read the setup MicroSD card. Select a directory and enter "(Filename).img".  Writing is significantly faster than manual installation and can fix bugs after modifications are made to code or pi. Select "(Filename).img" in the directory and click read. This will overwrite the MicroSD card. If using a MicroSD to SD card, make sure the switch is in the read-write position.
Mechanical Maintenance Schedule 
Outlined in this section is the recommended maintenance schedule for the VULCAN_FRY apparatus to ensure continued optimal performance.

Before Each Use:
Visually inspect apparatus for any loose fittings or connections. Ensure that the raspberry pi is running as expected by opening the program through the touch screen. 
Every 3-6 Months:
Tighten all hose connections
Tighten steel pipe connections on drum lid 
Inspect connections for any oil buildup and/ or blockages
Every Year:
Inspect all mechanical equipment. This includes the two (2) pumps as well as both heat exchangers
Replace any equipment that is not functioning properly, or has reached the end of its life span
If equipment does not need replacing, thoroughly clean the equipment and all of its connections and ensure that the apparatus functions properly upon reinstall. 


