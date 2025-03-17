import multiprocessing
from multiprocessing import Event, Queue, Value, Process, Lock
import gpiozero
import board
import digitalio
import adafruit_max31855
import busio
import adafruit_ads1x15.ads1115 as ADS
import RPi.GPIO as GPIO
from adafruit_ads1x15.analog_in import AnalogIn
from time import sleep
import os
from os import system
from ctypes import c_double
import csv
import gi
import time
import tkinter as tk
from tkinter import filedialog


# MAX31855
# Pin # 23, 24, 21, 11, 13, 15
# GPIO # 11, 8, 9, 17, 27, 22
# SCK, CS, S0, T0, T1, T2
SCK = 11
CS = 8
S0 = 9
T0 = 17
T1 = 13
T2 = 15

# ADS1115
# Pin # 3 5
# GPIO # 2 3
# SDA1, SCL1
# Note, doesn't seem to mix well with screen GPIO, but screen works without these so idk.

gain = 10
detectWattSensor = True

# Gas Input
# Pin # 31 (Pin 29 might be busted, check later. I made Gas and Water Identical for the next time this is checked)
# GPIO # 6

gasInput = 6

# Water Input (Needs to be changed to better match expected flow)
# Pin # 22
# GPIO # 25

waterInput = 25

# Relay Control
# Pin # 32 33
# GPIO # 12, 13
# Motor 1 and 2

motor_1 = 12
motor_2 = 13

# Number of active Thermocouples. Wire these in numerical order starting from 0.

thermoNum = 0

# Collects data every DataCollectFrequency seconds. Note: low values will increase the data collection speed, but currently may freeze the program. Modify with care.

DataCollectFrequency = 1 
pulsesPerGallon = 1588
pulsesPerCubicFoot = 1
voltage = 120

thermocouple_num = 7
return_farenheit = True

gasTally = Value(c_double, 0.00)
gasTallyTotal = Value(c_double, 0.00)
gasFlowRate = Value('d', 0.00)
gasFlowRateLock = Lock()
waterTally = Value(c_double, 0.00)
waterTallyTotal = Value(c_double, 0.00)
waterFlowRate = Value('d', 0.00)
waterFlowRateLock = Lock()

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk
"""
This is a library for the octo MAX31855 thermocouple breakout board.

MIT License

Copyright (c) 2020 Mitchell Herbert

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import RPi.GPIO as GPIO
from time import sleep

class MAX31855:
    """
    Initializes GPIO pins and instance variables.
    CS initializes to high because it is active low.
    SO is an input pin.

    :param SCK: the BCM pin number of the SCK line
    :param CS: the BCM pin number of the CS line
    :param SO: the BCM pin number of the SO line
    :param T0: the BCM pin number of the T0 line
    :param T1: the BCM pin number of the T1 line
    :param T2: the BCM pin number of the T2 line
    """
    def __init__(self, SCK, CS, SO, T0, T1, T2):
        GPIO.setmode(GPIO.BCM)
        # Setup all of the GPIO pins
        for pin_number in [SCK, T0, T1, T2]:
            GPIO.setup(pin_number, GPIO.OUT)
            GPIO.output(pin_number, 0)
        GPIO.setup(CS, GPIO.OUT)
        GPIO.output(CS, 1)
        GPIO.setup(SO, GPIO.IN)
        # Initialize instance variables
        self.SCK = SCK
        self.CS = CS
        self.SO = SO
        self.T0 = T0
        self.T1 = T1
        self.T2 = T2
        # Initialize the poll data to zero
        self.latest_data = 0b0

    """
    Communicates with the octo MAX31855 board to retrieve
    temperature and fault data. The data is stored in
    self.latest_data for later reference.

    :param therm_id: id of the thermocouple (0 - 7)
    """
    def read_data(self, therm_id):
        # Select the thermocouple using multiplexer
        GPIO.output(self.T2, therm_id & 0b100)
        GPIO.output(self.T1, therm_id & 0b10)
        GPIO.output(self.T0, therm_id & 0b1)
        # Wait for the multiplexer to update
        sleep(0.125)
        # Select the chip and record incoming data
        data = 0b0
        GPIO.output(self.CS, 0)
        # Shift in 32 bits of data
        for bitshift in reversed(range(0, 32)):
            GPIO.output(self.SCK, 1)
            data += GPIO.input(self.SO) << bitshift
            GPIO.output(self.SCK, 0)
        GPIO.output(self.CS, 1)
        self.latest_data = data

    """
    Gets the temperature of the most recently polled
    thermocouple.

    :returns: float representing the temperature in celsius
    """
    def get_thermocouple_temp(self, return_farenheit):
        data = self.latest_data
        # Select appropriate bits
        data = data >> 18
        # Handle twos complement
        if data >= 0x2000:
            data = -((data ^ 0x3fff) + 1)
        # Divide by 4 to handle fractional component
        celsius = data / 4
        fahrenheit = (celsius * 9/5) + 32
        if return_farenheit:
            return fahrenheit
        else:
            return celsius

    """
    Gets the temperature of the reference junction from
    the most recent poll.

    :returns: float representing the temperature in celsius
    """
    def get_reference_temp(self):
        data = self.latest_data
        # Select appropriate bits
        data = (data & 0xfff0) >> 4
        # Handle twos complement
        if data & 0x800:
            data = -((data ^ 0xfff) + 1)
        # Divide by 16 to handle fractional component
        return data / 16

    """
    Returns a value signififying a particular fault in the most
    recent poll.

    0 indicates that no faults exist
    1 indicates an SCV fault (thermocouple is shorted to VCC)
    2 indicates an SCG fault (thermocouple is shorted to GND)
    3 indicates an OC fault (the thermocouple is not connected)

    :returns: an integer representing the fault
    """
    def get_faults(self):
        data = self.latest_data
        if data & 0x00010000:
            if data & 0b100:
                return 1
            if data & 0b10:
                return 2
            if data & 0b1:
                return 3
        return 0

    """
    Should be called at the end of program execution to bring
    all GPIO pins to a 'safe' state.
    """
    def cleanup(self):
        GPIO.cleanup()


    """
    Returns the value of latest_data

    :returns: the value of latest_data
    """
    def get_latest_data(self):
        return self.latest_data

def flowControl(target, endDataCollect):
    setValve = 0  # 0 Open, 100 Closed
    errorMargin = target * 0.05
    while not endDataCollect.is_set():
        with waterFlowRate.get_lock():
            waterFlow = waterFlowRate.value 
        if abs(target - waterFlow) > errorMargin:
            setValve = max(0, min(100, setValve + (1 if target < waterFlow else -1)))
        sleep(0.05)
    setValve = 100

def getData(queue, totalTime, endDataCollect, wattChan):
    
    Temperature = MAX31855(SCK, CS, S0, T0, T1, T2)
    
    gasFlow = queue.get()
    allTemperatureReadings = queue.get()
    tempAvg = queue.get()
    wattage = queue.get()
    CookTime = queue.get()
    totalTime = queue.get()
    gasUsage = queue.get()
    waterUsage = queue.get()
    waterFlow = queue.get()
    gasTotalUsage = queue.get()
    # RotateRead = -1
    temperatureReadings = []
    
    # gasCurrentTest = len(totalTime)-1
    # #startTime = totalTime[-1]
    CookTime[-1] = 0

    while not endDataCollect.is_set():
        
        if len(gasFlow) >= 10000:
            gasFlow.pop(0)
            allTemperatureReadings.pop(0)
            tempAvg.pop(0)
            wattage.pop(0)
            CookTime.pop(0)
            totalTime.pop(0)
            gasUsage.pop(0)
            waterUsage.pop(0)
            waterFlow.pop(0)
            gasTotalUsage.pop(0)
        
        # gasFlow.append()
        
        # tempAvg.append(Temperature.get_thermocouple_temp() * 9 / 5 + 32)
        # Temperature.get_thermocouple_temp()
        wattage.append(round(wattChan.value, 2)) # Requires ADS1115 to run
        
        CookTime.append(round(CookTime[-1] + DataCollectFrequency, 2))
        totalTime.append(round(totalTime[-1] + DataCollectFrequency, 2))

        for i in range(thermocouple_num):
            Temperature.read_data(i)
            temperatureReadings.append(round(Temperature.get_thermocouple_temp(return_farenheit), 2))
        
        allTemperatureReadings.append(temperatureReadings)
        tempAvg.append(round(sum(allTemperatureReadings[-1])/len(allTemperatureReadings[-1]), 2))
        
        with gasTally.get_lock():
            gasUsage.append(round(gasTally.value, 2))   # This is measured as ft^3/s. As the data is collected every second, the total can be gotten through summation
        with gasFlowRate.get_lock():
            gasFlow.append(round(gasFlowRate.value, 2))
        with waterTally.get_lock():
            waterUsage.append(round(waterTally.value, 2))
        with waterFlowRate.get_lock():
            waterFlow.append(round(waterFlowRate.value, 2))
        with gasTallyTotal.get_lock():
            gasTotalUsage.append(round(gasTallyTotal.value, 2))
        
        queue.put(gasFlow)
        queue.put(allTemperatureReadings)
        queue.put(tempAvg)
        queue.put(wattage)
        queue.put(CookTime)
        queue.put(totalTime)
        queue.put(gasUsage)
        queue.put(waterUsage)
        queue.put(waterFlow)
        queue.put(gasTotalUsage)
        
        sleep(DataCollectFrequency)

def gasCounter(endDataCollect):
    edgeCount = 0
    lastState = GPIO.LOW
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gasInput, GPIO.IN)
    secondTracker = time.time()

    while  not endDataCollect.is_set():
        currentState = GPIO.input(gasInput)

        if currentState == GPIO.HIGH and lastState == GPIO.LOW:
            edgeCount += 1

        # 1 pulse per cubic foot
        if time.time() >= secondTracker + DataCollectFrequency:
            instantaneous_flow = edgeCount / pulsesPerCubicFoot
            with gasTally.get_lock():
                gasTally.value += instantaneous_flow
            with gasTallyTotal.get_lock():
                gasTallyTotal.value += instantaneous_flow
            with gasFlowRateLock:
                gasFlowRate.value = instantaneous_flow / DataCollectFrequency
    
            secondTracker = time.time()
            edgeCount = 0

        lastState = currentState

def waterCounter(endDataCollect):
    edgeCount = 0
    lastState = GPIO.LOW
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(waterInput, GPIO.IN)
    secondTracker = time.time()

    while  not endDataCollect.is_set():
        currentState = GPIO.input(waterInput)

        if currentState == GPIO.HIGH and lastState == GPIO.LOW:
            edgeCount += 1

        # 1588 pulses per gallon
        if time.time() >= secondTracker + DataCollectFrequency:
            instantaneous_flow = edgeCount / pulsesPerGallon
            with waterTally.get_lock():
                waterTally.value += instantaneous_flow
            with waterTallyTotal.get_lock():
                waterTallyTotal.value += instantaneous_flow
            with waterFlowRateLock:
                waterFlowRate.value = instantaneous_flow / DataCollectFrequency
    
            secondTracker = time.time()
            edgeCount = 0

        lastState = currentState

def get_unique_filename(filepath):
    base, ext = os.path.splitext(filepath)
    num = 1

    while os.path.exists(filepath):
        filepath = f"{base} ({num}){ext}"
        num += 1

    return filepath

class ProgramLoop(Gtk.Window):
    
    def __init__(self, queue):
        super().__init__(title="Looping App")
        self.endDataCollect = Event()
        self.set_default_size(800, 480)
        self.set_border_width(8)

        self.dataProcess = None
        self.queue = queue
        
        GLib.timeout_add(100, self.check_queue_detailed)
        GLib.timeout_add(100, self.check_queue_simple)
        
        self.gasFlow = [0]
        self.allTemperatureReadings = [0]
        self.tempAvg = [0]
        self.wattage = [0]
        self.CookTime = [0]
        self.totalTime = [0]
        self.gasUsage = [0]
        self.waterUsage = [0]
        self.waterFlow = [0]
        self.gasTotalUsage = [0]
        
        self.motor = digitalio.DigitalInOut(board.D7)
        self.motor.direction = digitalio.Direction.OUTPUT
        self.motor.value = 0
        
        self.gasTotal = 0
        self.fileName = "Test"

        self.stack = Gtk.Stack()
        self.add(self.stack)
        self.output_directory = '/home/pengo/VULCAN_FRY/Output'
        self.targetFlowRate = 6
        

        self.userDataCheck = f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test, use the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nFile Directory: {self.output_directory}\nTarget Flow Rate: {self.targetFlowRate}"
        
        # Screen 1: Naming the file
        self.nameFile1 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)
        self.nameFile1.set_vexpand(True)
        self.nameFile1.set_valign(Gtk.Align.START)
        
        self.nameFilelabel1 = Gtk.Label(label="Welcome to the simulated ASTM F1361 test apparatus.\nPlease read the user manual prior to setting up this test.\nEnsure that the sensors are affixed to the frier being tested.\nEnter a file name for saving the test in the first box.\nIf the file already exists, it will be overwritten.\nEnter a file directory in the second box.\nIf none is given, the default will be attempted\nEnter the target flow rate in the third box.\nPress Enter to continue.")
        self.nameFilelabel1.set_line_wrap(True)
        self.nameFilelabel1.set_xalign(0)
        self.nameFilelabel1.set_yalign(0)
        
        self.nameFileEntry1 = Gtk.Entry()
        self.nameFileEntry1.connect("key-press-event", self.saveFileName1)

        self.targetFlowRate1 = Gtk.Entry()
        self.targetFlowRate1.connect("key-press-event", self.saveFileName1)
        
        self.nameFile1.pack_start(self.nameFileEntry1, False, False, 10)
        self.nameFile1.pack_start(self.targetFlowRate1, False, False, 10)
        self.nameFile1.pack_start(self.nameFilelabel1, False, False, 10)
        
        self.stack.add_named(self.nameFile1, "nameFile1")      

        # Screen 2: Waits for user input to begin test
        self.waitToBegin2 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.waitToBeginlabel = Gtk.Label(label=self.userDataCheck)
        self.waitToBeginlabel.set_line_wrap(True)

        self.waitToBeginbutton = Gtk.Button(label="Begin Test")
        self.waitToBeginbutton.connect("clicked", self.beginTest)

        self.cancelBegin = Gtk.Button(label="Cancel")
        self.cancelBegin.connect("clicked", self.resetProgram)

        self.waitToBegin2.pack_start(self.waitToBeginlabel, True, True, 0)
        self.waitToBegin2.pack_start(self.waitToBeginbutton, True, True, 0)
        self.waitToBegin2.pack_start(self.cancelBegin, True, True, 0)
        self.stack.add_named(self.waitToBegin2, "waitToBegin2")

        # Screen 3: Waits for motors to turn on
        self.motorStartup3 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.motorStartuplabel = Gtk.Label(label="The motors should be turing on. If they do not, end the test and contact the VULCAN_FRY team.")
        self.motorStartuplabel.set_line_wrap(True)

        self.motorStartup3.pack_start(self.motorStartuplabel, True, True, 0)
        self.stack.add_named(self.motorStartup3, "motorStartup3")

        # Screen 4: Displays Data until user Input
        self.dataCollection4 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.dataCollectionlabelSimple = Gtk.Label(label="")
        self.dataCollectionlabelSimple.set_line_wrap(True)
        self.dataCollectionlabelSimple.set_name("bigLabel") # I think I add this label thing to anything I want to make bigger. Data_Simple_CSS() has the text size settings

        self.dataCollectionbutton = Gtk.Button(label="End Test")
        self.dataCollectionbutton.connect("clicked", self.endTest)

        self.topRightButton = Gtk.Button(label="Swap to detailed View")  # Simple symbol for now
        self.topRightButton.connect("clicked", self.swapToDetailed)

        self.dataCollection4.pack_start(self.dataCollectionlabelSimple, True, True, 0)
        self.dataCollection4.pack_start(self.dataCollectionbutton, True, True, 0)
        self.dataCollection4.pack_start(self.topRightButton, True, True, 0)
        self.stack.add_named(self.dataCollection4, "dataCollection4")

        self.Data_Simple_CSS()

        # Screen 4_2: Displays Data until user Input
        self.dataCollection4_2 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.dataCollectionlabelDetailed = Gtk.Label(label="")
        self.dataCollectionlabelDetailed.set_line_wrap(True)

        self.dataCollectionbutton_2 = Gtk.Button(label="End Test")
        self.dataCollectionbutton_2.connect("clicked", self.endTest)

        self.topRightButton_2 = Gtk.Button(label="Swap to simple view")  # Simple symbol for now
        self.topRightButton_2.connect("clicked", self.swapToSimple)

        self.dataCollection4_2.pack_start(self.dataCollectionlabelDetailed, True, True, 0)
        self.dataCollection4_2.pack_start(self.dataCollectionbutton_2, True, True, 0)
        self.dataCollection4_2.pack_start(self.topRightButton_2, True, True, 0)
        self.stack.add_named(self.dataCollection4_2, "dataCollection4_2")

        # Screen 5: Waits for motors to turn off
        self.motorWindDown5 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.motorWindDownlabel = Gtk.Label(label="The motors should be turing off. If they do not,end the test and contact the VULCAN_FRY team.")
        self.motorWindDownlabel.set_line_wrap(True)

        self.motorWindDown5.pack_start(self.motorWindDownlabel, True, True, 0)
        self.stack.add_named(self.motorWindDown5, "motorWindDown5")

        # Screen 6: Continue Testing Querry
        self.continueTestingQuerry6 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.TQbuttonNextTest = Gtk.Button(label="Click to begin the next test.")
        self.TQbuttonEndTesting = Gtk.Button(label="Click to end testing.")
        self.TQbuttonNextTest.connect("clicked", self.beginTest)
        self.TQbuttonEndTesting.connect("clicked", self.saveDataQuerry)

        self.continueTestingQuerry6.pack_start(self.TQbuttonNextTest, True, True, 0)
        self.continueTestingQuerry6.pack_start(self.TQbuttonEndTesting, True, True, 0)

        self.stack.add_named(self.continueTestingQuerry6, "continueTestingQuerry6")

        # Screen 7: Save Data to file Querry
        self.saveDataQuerry7 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.DQbuttonSave = Gtk.Button(label="Click to save test to given destination. Program will restart.")
        self.DQbuttonReset = Gtk.Button(label="Click to restart program without saving.")
        self.DQbuttonSave.connect("clicked", self.saveData)
        self.DQbuttonReset.connect("clicked", self.resetProgram)

        self.saveDataQuerry7.pack_start(self.DQbuttonSave, True, True, 0)
        self.saveDataQuerry7.pack_start(self.DQbuttonReset, True, True, 0)

        self.stack.add_named(self.saveDataQuerry7, "saveDataQuerry7")

        # Screen 8: Saving data to file
        self.savingData8 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.savingDatalabel = Gtk.Label(label="Saving Data...")
        self.savingDatalabel.set_line_wrap(True)

        self.savingData8.pack_start(self.savingDatalabel, True, True, 0)
        self.stack.add_named(self.savingData8, "savingData8")

        # Screen 9: Data saved to file
        self.dataSaved9 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.dataSavelabel = Gtk.Label(label="Data Saved.")
        self.dataSavelabel.set_line_wrap(True)

        self.dataSaved9.pack_start(self.dataSavelabel, True, True, 0)
        self.stack.add_named(self.dataSaved9, "dataSaved9")
        
    def Data_Simple_CSS(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        #bigLabel {
            font-size: 24px;
            font-weight: bold;
            color: #333333;  /* Optional: Dark gray text */
        }
        """)
        
        screen = Gdk.Screen.get_default()
        style_context = Gtk.StyleContext()
        style_context.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def saveFileName1(self, widget, event):
        try:
            self.I2C = busio.I2C(board.SCL, board.SDA)   # Set up the Wattage Sensor
            self.ads = ADS.ADS1115(i2c = self.I2C, gain = 1) # Requires ADS1115 to run
            self.wattChan = AnalogIn(self.ads, ADS.P0) # Requires ADS1115 to run
            self.detectWattSensor = True
        except:
            class WattChanFallback:
                @property
                def value(self):
                    return -1

            self.wattChan = WattChanFallback()
            self.detectWattSensor = False
        with gasTallyTotal.get_lock():
            gasTallyTotal.value = 0.00
        with waterTallyTotal.get_lock():
            waterTallyTotal.value = 0.00
        if event.keyval == Gdk.KEY_Return:
            self.fileName = self.nameFileEntry1.get_text()
            target_flow_rate_input = self.targetFlowRate1.get_text()
            try:
                self.targetFlowRate = float(target_flow_rate_input)
            except ValueError:
                self.targetFlowRate = self.targetFlowRate
            print(self.fileName)
            print(self.nameFileEntry1.get_text())
            self.stack.set_visible_child_name("waitToBegin2")
            if detectWattSensor:
                self.userDataCheck = f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test, use the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
            else:
                self.detectWattSensor = f"Warning: Wattmeter is not connected correctly. Please check the wiring and hit cancel if this is unintentional.\n\nPress \"Begin Test\" to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test, use the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
            self.waitToBeginlabel.set_text(self.userDataCheck)
        
    def beginTest(self, *args):
        self.stack.set_visible_child_name("motorStartup3")
        GPIO.output(motor_1, GPIO.HIGH)
        GPIO.output(motor_2, GPIO.HIGH)
        GLib.timeout_add(5000, self.startDataCollection)
        
    def startDataCollection(self):
        self.queue.put(self.gasFlow)
        self.queue.put(self.allTemperatureReadings)
        self.queue.put(self.tempAvg)
        self.queue.put(self.wattage)
        self.queue.put(self.CookTime)
        self.queue.put(self.totalTime)
        self.queue.put(self.gasUsage)
        self.queue.put(self.waterUsage)
        self.queue.put(self.waterFlow)
        self.queue.put(self.gasTotalUsage)
        self.endDataCollect.clear()
        self.dataProcess = multiprocessing.Process(
            target=getData, args=(self.queue, totalTime, self.endDataCollect, self.wattChan), daemon=True
        )
        self.GasProcess = multiprocessing.Process(
            target=gasCounter, args=(self.endDataCollect, ), daemon=True
        )
        self.WaterProcess = multiprocessing.Process(
            target=waterCounter, args=(self.endDataCollect, ), daemon=True
        )
        self.ControlProcess = multiprocessing.Process(
            target=flowControl, args=(self.targetFlowRate, self.endDataCollect), daemon=True
        )
        
        self.dataProcess.start()
        self.GasProcess.start()
        self.WaterProcess.start()
        self.ControlProcess.start()
        self.stack.set_visible_child_name("dataCollection4")
        return False
    
    def swapToDetailed(self):
        self.stack.set_visible_child_name("dataCollection4_2")

    def swapToSimple(self):
        self.stack.set_visible_child_name("dataCollection4")
        
    def check_queue_detailed(self):
        while not self.queue.empty():
            self.gasFlow = self.queue.get()
            self.allTemperatureReadings = self.queue.get()
            self.tempAvg = self.queue.get()
            self.wattage = self.queue.get()
            self.CookTime = self.queue.get()
            self.totalTime = self.queue.get()
            self.gasUsage = self.queue.get()
            self.waterUsage = self.queue.get()
            self.waterFlow = self.queue.get()
            self.gasTotalUsage = self.queue.get()

            if len(self.allTemperatureReadings[-1]) < 8:
                for i in range(8 - len(self.allTemperatureReadings[-1])):
                   self.allTemperatureReadings[-1].append("Unused") 

            if self.stack.get_visible_child_name() == "dataCollection4":
                dataUpdateDetailed = (
                    f"gasFlow: {self.gasFlow[-1]}\t\t\tThermocouple 1: {self.allTemperatureReadings[-1][0]}\n"
                    f"tempAvg: {self.tempAvg[-1]}\t\t\tThermocouple 2: {self.allTemperatureReadings[-1][1]}\n"
                    f"wattage: {self.wattage[-1]}\t\t\tThermocouple 3: {self.allTemperatureReadings[-1][2]}\n"
                    f"CookTime: {self.CookTime[-1]}\t\t\tThermocouple 4: {self.allTemperatureReadings[-1][3]}\n"
                    f"totalTime: {self.totalTime[-1]}\t\t\tThermocouple 5: {self.allTemperatureReadings[-1][4]}\n"
                    f"gasUsage: {self.gasUsage[-1]}\t\t\tThermocouple 6: {self.allTemperatureReadings[-1][5]}\n"
                    f"waterUsage: {self.waterUsage[-1]}\t\t\tThermocouple 7: {self.allTemperatureReadings[-1][6]}\n"
                    f"waterFlow: {self.waterFlow[-1]}\t\t\tThermocouple 8: {self.allTemperatureReadings[-1][7]}\n"
                    f"gasTotalUsage: {self.gasTotalUsage[-1]}\n"
                )
                self.dataCollectionlabelDetailed.set_text(dataUpdateDetailed)
        return True 
    
    def check_queue_simple(self):
        while not self.queue.empty():
            self.gasFlow = self.queue.get()
            self.allTemperatureReadings = self.queue.get()
            self.tempAvg = self.queue.get()
            self.wattage = self.queue.get()
            self.CookTime = self.queue.get()
            self.totalTime = self.queue.get()
            self.gasUsage = self.queue.get()
            self.waterUsage = self.queue.get()
            self.waterFlow = self.queue.get()
            self.gasTotalUsage = self.queue.get()

            if len(self.allTemperatureReadings[-1]) < 8:
                for i in range(8 - len(self.allTemperatureReadings[-1])):
                   self.allTemperatureReadings[-1].append("Unused") 

            if self.stack.get_visible_child_name() == "dataCollection4":
                dataUpdate = (
                    f"Temperature Average: {self.tempAvg[-1]}\n"
                    f"Wattage: {self.wattage[-1]}\n"
                    f"Cook Time: {self.CookTime[-1]}\n"
                    f"Total Time: {self.totalTime[-1]}\n"
                    f"Gas Usage: {self.gasUsage[-1]}\n"
                    f"Water Flow: {self.waterFlow[-1]}\n"
                )
                self.dataCollectionlabelSimple.set_text(dataUpdate)
        return True 
        
    def endTest(self, *args):
        GPIO.output(motor_1, GPIO.LOW)
        GPIO.output(motor_2, GPIO.LOW)
        self.endDataCollect.set()
        self.dataProcess.join()
        self.GasProcess.join()
        self.WaterProcess.join()
        self.ControlProcess.join()
        with gasTally.get_lock():
            gasTally.value = 0.00
        with waterTally.get_lock():
            waterTally.value = 0.00
        self.stack.set_visible_child_name("motorWindDown5")
        self.motor.value = 0
        GLib.timeout_add(5000, self.continueTestingQuerry)
        
    def continueTestingQuerry(self):
        self.stack.set_visible_child_name("continueTestingQuerry6")
        return False
        
    def saveDataQuerry(self, *args):
        self.stack.set_visible_child_name("saveDataQuerry7")
        
    def saveData(self, *args):

        directory = filedialog.askdirectory(title="Save Test")

        if directory:
            None
        else:
            return None

        self.stack.set_visible_child_name("savingData8")
        
        initial_path = os.path.join(directory, self.fileName)
        file_path = get_unique_filename(initial_path)
        num_thermocouples = len(self.allTemperatureReadings[0]) if self.allTemperatureReadings else 0
        header = [
            "Gas Flow Rate",
            "Temperature Average",
            "Wattage",
            "Current Test Time (sec)",
            "Total Time (sec)",
            "Gas Usage",
            "Water Usage",
            "Gas Total Usage",
            "Water Total Usage"
        ] + [f"Thermocouple {i+1}" for i in range(num_thermocouples)]

        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)

            writer.writerow(header)

            for i in range(len(self.gasFlow)):
                temp_readings = self.allTemperatureReadings[i] if i < len(self.allTemperatureReadings) else [None] * num_thermocouples

                writer.writerow([
                    self.gasFlow[i],
                    self.tempAvg[i],
                    self.wattage[i],
                    self.CookTime[i+1],
                    self.totalTime[i+1],
                    self.gasUsage[i],
                    self.waterUsage[i],
                    self.gasTotalUsage[i],
                    self.waterFlow[i]
                ] + temp_readings)
                
        self.stack.set_visible_child_name("dataSaved9")
        GLib.timeout_add(5000, self.resetProgram)
        
    def resetProgram(self, *args):
        self.gasFlow = []
        self.tempAvg = []
        self.wattage = []
        self.allTemperatureReadings = []
        self.CookTime = [0]
        self.totalTime = [0]
        self.gasUsage = []
        self.gasTotalUsage = []
        self.waterUsage = []
        self.waterFlow = []
        self.stack.set_visible_child_name("nameFile1")
        return False
        
        
def main():
    global gasFlow, tempAvg, wattage, totalTime, CookTime, gasUsage, gasTotalUsage
    global gasAnalogIn, max31855, wattChan
    gasFlow = []
    gasFlowTotal = []
    gasUsage = []
    gasTotalUsage = []
    tempAvg = []
    wattage = []
    CookTime = [0]
    totalTime = [0]

    # Preparing Pins
    GPIO.setmode(GPIO.BCM)

    spi = board.SPI()   # Set up the Thermocoupler
    cs = digitalio.DigitalInOut(board.D5)
    max31855 = adafruit_max31855.MAX31855(spi, cs)
    
    """
    try:
        I2C = busio.I2C(board.SCL, board.SDA)   # Set up the Wattage Sensor
        ads = ADS.ADS1115(i2c = I2C, gain = 1) # Requires ADS1115 to run
        wattChan = AnalogIn(ads, ADS.P0) # Requires ADS1115 to run
    except Exception as e:
        class WattChanFallback:
            @property
            def value(self):
                return -1

        wattChan = WattChanFallback()
        detectWattSensor = False"
    """

    gasAnalogIn = digitalio.DigitalInOut(board.D6)   # TBD When Gas Flow Meter compatible with pi is found

    # Sets up two relays to control two pumps
    # HIGH is closed and on. LOW is open and off
    GPIO.setup(motor_1, GPIO.OUT)
    GPIO.setup(motor_2, GPIO.OUT)
    GPIO.output(motor_1, GPIO.LOW)
    GPIO.output(motor_2, GPIO.LOW)

    queue = multiprocessing.Queue()

    app = ProgramLoop(queue)
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
    GPIO.cleanup()
    
if __name__ == "__main__":
    main()
