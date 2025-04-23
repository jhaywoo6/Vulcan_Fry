User Guide:
Welcome to the Vulcan Testing Apparatus for the simulation of the ASTM Test. 
Read through this user guide prior to opperation of the apparatus.

1. Setup
This program runs on the raspberry pi 4B and is included on the .img file. 
The .img is set by default to run this program on startup. If the microSD card
has not been imaged yet, or the raspberry pi does not have this behavior on startup,
the microSD card can be reimaged with Win32 Disk Imager on a seperate computer
  a. Remove the microSD card from the pi and plug it into the seperate computer.
  b. Download and run Win32 Disk Imager (https://sourceforge.net/projects/win32diskimager/)
  c. Click the blue folder.
  d. Locate the .img file. A copy of the .img file is on the USB flash drive provided by the VULCAN_FRY team.
  e. Click Write.
  f. Once finished, Eject the microSD card and plug it into the pi

Note: Imaging the pi will erase any test data contained on the pi. Move these files
off of the pi if it is possible to do so prior to imaging.

2. Preforming the test
To start the pi, plug in the included USB-C Cable. If its connected to power, it should turn on.
Upon being powered, the pi will start up the OS (Gnome), and will autostart the program on startup.
Note the E-Stop button. This will cut power to the oil pumps. Press the E-stop button if they behave unexpectedly.
The program will not be affected by the E-stop, so you can finish these steps when its safe to do so.

This program is designed to stay open as long as the device is powered on.
There is no reason to close the program at any point.
If the program is accidentially closed by the user, there are two ways to run it again. Note that all data collected during an active test
will be lost if the program is closed.
1. Unpower and repower the pi. Can be done either from the pi itself, the 3 way splitter, or from the wall.
2. Activities -> geany -> Build -> Execute.
This should select the code when opened and will execute the program after following these steps.
If the code window is empty, File -> Open, Locate and open the .py file with the code in the home/Vulcan Directory.

Step 1: Test Parameters
  You will be prompted to enter a test name in the first text entry box and a target temperature in the second text entry box.
  Tap the box to bring up the on-screen keyboard. If the keyboard does not appear,
  check that on-screen keyboard is turned on in the accessibility settings, located on the top right bar. Look for the person icon.
  Type in the test name and the target temperature in gallons per second.
  Hit enter on the on-screen keyboard to advance to the next screen.

Step 2: Verify Parameters
  Check that the parameters match what you have entered in the previous screen.
  Hit start test to advance to the next screen, or cancel to re enter the test parameters.

Step 3: Data Collection
  Upon hitting start test the program will attempt to turn on the motors.
  Once the motors are on, data collection will begin. Some of the data being collected will display on the screen.
  This is the simple view. To swap to the detailed view and view all collected parameters, click swap to detailed view on the top right.
  You can freely swap between views this way. 
  During tests the time the current test has ran will display as Cook Time.
  The program will also attempt to automatically match the target temperature by adjusting the control valve in relation to the measured flow rate.
  Click End Test to end the current test.
  The Cook time will reset to 0 and the control valve will close, but all other data points will continue to be tracked.
  "Click to begin the next test." Will start a new test, counting a new Cook Time and operating the control valve again automatically.
  "Click to end testing." will end all testing. All data collection will stop at this stage.

Step 3: Saving the File
  "Click to pick a file directory to save the test. Program will restart." Will bring up a file selection dialog.
  Navigate the dialog window and select a location to save the test data.
  If a file of the same name is already in the directory, a number "(#)" will be added at the end of the file name.
  After selecting a location, the program will save the data to that directory as a .csv file and restart.
  "Click to restart program without saving." Will restart the program without saving the test data.

Step 4: Accessing the File
  If the selected directory was a USB Drive, simply eject the USB stick from the pi and insert into your computer of choice.
  To access the file on the pi, select activities on the top left.
  Select Files on the leftmost side of the quick access bar under the desktop with the program. It looks like a file cabinet.
  Navigate to the directory you selected earlier.
  A web browser can be opened from the quick access bar as well. Select FireFox and navigate to your website of choice 
  for uploading or sharing .csv files.

Note: The message automatic suspension may appear when the program is left idle.
Automatic suspension has been disabled on the .img, but this message may still erroneously appear.
Tapping on the screen will remove the popup.

Maintenence Guide:
This section is for developers looking to fix/upgrade the program.
It is recommended to have a basic understanding of python 3.13.2 prior to creating modifications.
This program uses GPIO pins to communicate with other boards specialized in collecting data from sensors. The Raspberry Pi 4B has a 40-pin header. The pinout can be found on the raspberry pi documentation: (ctrl + f "GPIO and the 40-pin header")
(https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
Here is the default pinout in relation to the device it connects with:

MAX31855
# Pin # 23, 24, 21, 11, 13, 15, 12, 16, 18
# GPIO # 11, 8, 9, 17, 27, 22, 18, 23, 24
# SCK, CS0, S0, CS1, CS2, CS3, CS4, CS5
# MISO
# Thermocouples wired to this device should be wired from 0 to 7. 
# If a port can't be used 

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
# Motor 1 and 2

The Thermocouples are wired to the MAX31855. Their port number can be seen on the MAX31855 Board. Ports 0-5 are used in the apparatus, with 2 spare slots.
Facing the 4 hoses on the heat exchanger with the motors on the right:
1 0
3 2
Just to the right of the heat exchanger facing the motors:
4 5
In the program, the numbers currently corespond to the following:
0: "Water Out", 1: "Water In", 2: "HX In", 3: "HX Out", 4: "Fryer HX Out", 5: "Fryer HX In", 6: "Spare 1", 7: "Spare 2"
These can be changed in the program parameters.

Geany is used to modify and test new versions of the program. It can be found on
the quick access bar by selecting activities on the top left and looking under the program desktop.
It appears as a genies lamp.
The .img file should load the program .py file by default.
It can be found under /home/Vulcan/DevRev0.1.9.
Modifications made to the program here will affect the program on next reboot.
It is recommended to use a keyboard and mouse when editing the program directly on the pi
as the onsceen keyboard will close geany upon hitting the backspace button, making edits difficult.
Alternativly, copy and paste the latest revision of this program into your code editor of choice. 
The text of the code can either be pasted directly into geany, or you can replace the file 
with one of an identical name with the new modifications.

The latest functional rev as of writing is VulcanFryTestApparatus Ver. 1.0.1.py

The program uses Gtk 3.0 to create and load GUI elements. Refer to the Gtk documentation
for mor info on how these elements work. (https://python-gtk-3-tutorial.readthedocs.io/en/latest/)

The program uses Adafruit for communication with the MAX31855, ADS1115, and DS3502 boards.
Refer to their respective documentation for how they work.
Note the Octo MAX31855 has its own library seperate from adafruit. Do not use the adafruit_max31855
library with this program.
MAX31855: (https://github.com/Neem-Tech/Octo-MAX31855-Breakout-Board)
ADS1115: (https://docs.circuitpython.org/projects/ads1x15/en/latest/)
DS3502: (https://docs.circuitpython.org/projects/ds3502/en/latest/)

The program uses many other libraries to perform program functions. Refer to their respective documentation to learn how they work.
While the os should log in the user automatically, some changes may require a login.
Username: Vulcan
Password: FrySpring2025

A keyboard extension is used to inprove the base keyboard. If it is not installed, use these instructions to do so.
https://github.com/nick-shmyrev/improved-osk-gnome-ext

The program window may clip out of the scree if the os font size is too big, causing buttons to become inaccessible. The default size has been lowered by default,
but this can be adjusted from the gnome tweaker. Activities->Quick access bar->Tweaker. (Appears as two switches)
Navigate to fonts and adjust the font size. Recommended: 0.8.
It is recommended for future code iterations to add in auto resizing of ui elements should a new screen or alternative window resolution be used.

Manual installation:
To manually install the program onto the Raspberry Pi, you will need the Raspberry Pi Imager v1.8.5 and an internet connection.
Format the MicroSD card being used. You may need to use DiskPart to clean the MicroSD card if the card has previously been used for the pi.

Step 1: Imaging
Insert the MicroSD card into the computer and open Raspberry Pi Imager v1.8.5. Select device Raspberry Pi 4, Raspberry Pi OS (64-BIT), and the
MicroSD card as the storage device. The card provided by the Vulcan Fry team is ~32 GB. 
NEXT > EDIT SETTINGS
Set hostname and username to Vulcan
Set password to FrySpring2025
Under config wireless lan, set SSID and password accordingly
Under services disable SSH
Click SAVE > YES > YES (This will erase all data on the card if there was any at this stage)
Once the Write is complete, eject the MicroSD card and insert into the Raspberry Pi 4. It is recommended to remove the GPIO pin attachment during this stage.

Step 2: Terminal Lines
Plug the pi into the touch screen or us a micro-hdmi cable into another monitor. It is recommended to use a keyboard and mouse for setup.
Open the Terminal. This can be found at the top left of the desktop.
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
sudo apt update && sudo apt install xorg gnome gnome-shell --no-install-recommends
y + enter when prompted
enter
Highlight gdm3 and hit enter
sudo pip install Adafruit-Blinka --break-system-packages
sudo pip install adafruit-circuitpython-ads1x15 --break-system-packages
sudo pip install adafruit-circuitpython-ds3502 --break-system-packages
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
Navigate to project github and download VulcanFryTestApparatus_Ver_1_0_2.py
Move these files to the home directory
In the terminal:
mkdir -p ~/.config/autostart
nano ~/.config/autostart/TestApp.desktop
Copy the following:
"""
[Desktop Entry]
Type=Application
Exec=/usr/bin/python3 /home/Vulcan/VulcanFryTestApparatus_Ver_1_0_2.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Vulcan Fry Data Collection Service
Comment=Collects test data according to user input
"""
ctrl s + ctrl x
chmod +x /home/Vulcan/VulcanFryTestApparatus_Ver_1_0_2.py
Restart Pi

The Pi is now set up to run the test program! To update VulcanFryTestApparatus_Ver_1_0_2.py, edit it in geany or replace the file with one of the same name.
To update the name, edit the .desktop file as shown above with the new name.

If important changes are made and a new image file is needed, use Win32 Disk Imager to Read the set up MicroSD card. Select a directory and enter "(Filename).img". 
Writing is significantly faster than manuall installation and can fix bugs. Select "(Filename).img" in the directory and click read. This will overwrite the MicroSD card.
If using a MicroSD to SD card, make sure the switch is in the read write position.





