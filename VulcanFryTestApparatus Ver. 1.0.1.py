import multiprocessing
from multiprocessing import Event, Queue, Value, Process, Lock
import gpiozero
import board
import digitalio
import busio
import adafruit_ads1x15.ads1115 as ADS # sudo pip3 install adafruit-circuitpython-ads1x15 --break-system-packages
import adafruit_ds3502 # sudo pip3 install adafruit-circuitpython-ds3502 --break-system-packages
import RPi.GPIO as GPIO
from adafruit_ads1x15.analog_in import AnalogIn
from time import sleep
import os
from ctypes import c_double
import csv
import gi
import time
from tkinter import filedialog
import numpy as np

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

params = {
    "MAX31855Pinout": (11, 8, 9, 17, 27, 22),
    "ADS1115": {
        "ADSAddress": 0x48,
        "ADSGain": 1,
        "ADSSamples": 500,
        "burdenResistor": 10.0,
        "SCTRatio": 100.0,
        "voltageSupply": 120.0,
        "currentCorrection": 17.8
    },
    "DS3502": {
        "DSAddress": 0x28,
        "targetFlowRateDefault": 6,
        "setValveDefault": 127,
        "valveAdjustmentFrequency": 0.05,
        "margin": 0.05
    },
    "targetFlowRateOptions": {
        "Option A": 4,
        "Option B": 6,
        "Option C": 8
    },
    "sensors": {
        "gas": {"pin": 6, "pulses_per_unit": 1, "tally": Value('d', 0.00), "totalTally": Value('d', 0.00), "flowRate": Value('d', 0.00)},
        "water": {"pin": 25, "pulses_per_unit": 1588, "tally": Value('d', 0.00), "totalTally": Value('d', 0.00), "flowRate": Value('d', 0.00)}
    },
    "motor": {
        "pin1": 12,
        "pin2": 13,
        "windUpTime": 5000
    },
    "thermoNum": 7,
    "returnFarenheit": True,
    "DataCollectionFrequency": 1, # Reading the MAX31855, the fastest this can go is ~0.88.
    "clocks": {
        "cookTime": Value(c_double, 0.00),
        "totalTime": Value(c_double, 0.00)
    },
    "dataListMaxLength": 2147483647,
    "resolution": (800, 428),
    "defaultFileName": "Test",
    "significantFigures": 2,
    "returnFarenheit": True  # Set to True to return Farenheit, False for Celsius
}

# Install into a seperate file later

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
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
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
    def get_thermocouple_temp(self, returnFarenheit=False):
        data = self.latest_data
        # Select appropriate bits
        data = data >> 18
        # Handle twos complement
        if data >= 0x2000:
            data = -((data ^ 0x3fff) + 1)
        # Divide by 4 to handle fractional component
        celsius = data / 4
        if returnFarenheit:
            return (celsius * 9 / 5) + 32
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

def readPower(chan, ADS1115Params):
    rawVrms = 0.0
    samples = ADS1115Params["ADSSamples"]
    for _ in range(samples):
        voltage = chan.voltage
        rawVrms += voltage ** 2
    
    vrms = (rawVrms / samples) ** 0.5
    current = (vrms / ADS1115Params["burdenResistor"]) * ADS1115Params["SCTRatio"] / ADS1115Params["currentCorrection"] # Note: currentCorrection is a bandaid fix for adjusting read current to expected value. May need fixed in the future.
    power = ADS1115Params["voltageSupply"] * current
    return power

# Adds a number to the end of the file name if it already exists. Test, Test(1), Test(2), ect.

def duplicateLabeler(filepath):
    base, ext = os.path.splitext(filepath)
    num = 1

    while os.path.exists(filepath):
        filepath = f"{base} ({num}){ext}"
        num += 1

    return filepath

# Looping functions. These are started by programLoop after selecting self.waitToBegin2button = Gtk.Button(label="Begin Test")
# The current test ends after selecting self.dataCollection4SimpleEndTestButton = Gtk.Button(label="End Test")
# A new test starts after selecting self.continueTestingQuerry6NextTest = Gtk.Button(label="Click to begin the next test.")
# Between tests cookTime is stopped and set to 0
# Between tests flowControl is set to close the valve
# All other functions run and collect data during and between tests until self.continueTestingQuerry6EndTesting = Gtk.Button(label="Click to end testing.") is pressed.

def flowControl(target, endDataCollect, ds3502, DS3502Params):
    setValve = DS3502Params["setValveDefault"]  # 0 Open, 127 Closed

    try:
        ds3502.wiper = setValve
        print("DS3502 is connected")
    except:
        print("DS3502 is not connected")

    errorMargin = target * DS3502Params["margin"]

    while not endDataCollect.is_set():
        with params["sensors"]["water"]["flowRate"].get_lock():
            waterFlow = params["sensors"]["water"]["flowRate"].value
        if abs(target - waterFlow) > errorMargin:
            setValve = max(0, min(127, setValve + (1 if target < waterFlow else -1)))
            try:
                ds3502.wiper = setValve
            except:
                None
        sleep(DS3502Params["valveAdjustmentFrequency"])

    setValve = DS3502Params["setValveDefault"]

    try:
        ds3502.wiper = setValve
    except:
        None

def clockTracker(endDataCollect, clock):
    startTime = time.time()
    while not endDataCollect.is_set():
        currentTime = time.time()
        with params["clocks"][clock].get_lock():
            params["clocks"][clock].value = round(currentTime - startTime, 2)

    with params["clocks"][clock].get_lock():
        params["clocks"][clock].value = 0  

def getData(queue, endDataCollect, wattChan, DataCollectionFrequency, Temperature, ADS1115Params):
    try:
        Temperature = MAX31855(*params["MAX31855Pinout"])
        print("MAX31855 is connected")
    except:
        print("MAX31855 is not connected")

    data = {
        "gasFlow": {"value": 0, "unit": "cu ft / sec"},
        "thermocouple no.": {"value" : [0 for _ in range(params["thermoNum"])], "unit": "F"},
        "tempAvg": {"value": 0, "unit": "F"},
        "wattage": {"value": 0, "unit": "W"},
        "CookTime": {"value": 0, "unit": "sec"},
        "totalTime": {"value": 0, "unit": "sec"},
        "gasUsage": {"value": 0, "unit": "cu ft"},
        "waterUsage": {"value": 0, "unit": "gal"},
        "waterFlow": {"value": 0, "unit": "gal / sec"},
        "gasTotalUsage": {"value": 0, "unit": "cu ft"}
    }


    while not endDataCollect.is_set():
        startTime = time.time()
        try:
            data["wattage"]["value"] = round(readPower(wattChan, ADS1115Params))
        except:
            data["wattage"]["value"] = -1

        for i in range(params["thermoNum"]):
            try:
                Temperature.read_data(i)
                data["thermocouple no."]["value"][i] = round(Temperature.get_thermocouple_temp(params["returnFarenheit"]), 2)
            except:
                data["thermocouple no."]["value"][i] = -1
        data["tempAvg"]["value"] = round(np.mean(data["thermocouple no."]["value"][0:params["thermoNum"]]), 2)

        if len(data["thermocouple no."]["value"]) < 8:
            data["thermocouple no."]["value"].extend(["Unused"] * (8 - len(data["thermocouple no."]["value"])))

        with params["sensors"]["gas"]["tally"].get_lock(), params["sensors"]["gas"]["flowRate"].get_lock(), params["sensors"]["water"]["tally"].get_lock(), params["sensors"]["water"]["flowRate"].get_lock(), params["sensors"]["gas"]["totalTally"].get_lock(), params["sensors"]["water"]["totalTally"].get_lock(), params["clocks"]["cookTime"].get_lock(), params["clocks"]["totalTime"].get_lock():
            data["gasUsage"]["value"] = round(params["sensors"]["gas"]["tally"].value, params["significantFigures"])
            data["waterUsage"]["value"] = round(params["sensors"]["water"]["tally"].value, params["significantFigures"])
            data["gasFlow"]["value"] = round(params["sensors"]["gas"]["flowRate"].value, params["significantFigures"])
            data["waterFlow"]["value"] = round(params["sensors"]["water"]["flowRate"].value, params["significantFigures"])
            data["gasTotalUsage"]["value"] = round(params["sensors"]["gas"]["totalTally"].value, params["significantFigures"])
            data["CookTime"]["value"] = params["clocks"]["cookTime"].value
            data["totalTime"]["value"] = params["clocks"]["totalTime"].value

        queue.put(data)
        elapsedTime = time.time() - startTime
        if elapsedTime > DataCollectionFrequency:
            DataCollectionFrequency = elapsedTime
            print(f"DataCollectionFrequency adjusted to {DataCollectionFrequency}. Optimizations needed to reach requested rate.")
        time.sleep(DataCollectionFrequency)

def pulseCounter(sensorName, endDataCollect, dataCollectionFrequency):
    sensor = params["sensors"][sensorName]
    edge_count = 0
    last_state = GPIO.LOW

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(sensor["pin"], GPIO.IN)
    timeTracker = time.time()

    while not endDataCollect.is_set():
        current_state = GPIO.input(sensor["pin"])

        if current_state == GPIO.HIGH and last_state == GPIO.LOW:
            edge_count += 1

        if time.time() >= timeTracker + dataCollectionFrequency:
            instantaneous_flow = edge_count / sensor["pulses_per_unit"]

            with sensor["tally"].get_lock(), sensor["totalTally"].get_lock(), sensor["flowRate"].get_lock():
                sensor["tally"].value += instantaneous_flow
                sensor["totalTally"].value += instantaneous_flow
                sensor["flowRate"].value = instantaneous_flow / dataCollectionFrequency   

            timeTracker = time.time()
            edge_count = 0

        last_state = current_state

class programLoop(Gtk.Window):

    def __init__(self, queue):
        super().__init__(title="Looping App")
        self.endTestEvent = Event()
        self.endDataCollect = Event()
        self.testUnderWay = False
        self.set_default_size(*params["resolution"])
        self.set_resizable(False)
        self.set_border_width(8)

        self.dataProcess = None
        self.queue = queue

        GLib.timeout_add(100, self.checkQueue)

        self.dataList = []

        self.motor = digitalio.DigitalInOut(board.D7)
        self.motor.direction = digitalio.Direction.OUTPUT
        self.motor.value = 0

        self.gasTotal = 0
        self.fileName = params["defaultFileName"]

        self.stack = Gtk.Stack()
        self.add(self.stack)
        self.targetFlowRate = params["DS3502"]["targetFlowRateDefault"]

        self.text_userDataCheck = (
            f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
        )

        self.text_nameFile1label = (
            f"Welcome to the simulated ASTM F1361 test apparatus.\nPlease read the user manual prior to setting up this test.\nEnsure that the sensors are affixed to the frier being tested.\nEnter a file name for saving the test in the first box.\nIf the file already exists, an extension (#) will be added.\nSelect the second box for a list of flow speed options.\nPick the option corresponding to the frier you wish to test.\nPress Next or Enter to continue."
        )

        self.textMotorStartup3label = "The motors should be turning on.\nIf they do not, end the test and contact the VULCAN_FRY team."
        self.textMotorWindDown5Label = "The motors should be turning off.\nIf they do not, end the test and contact the VULCAN_FRY team."
        self.textSavingData8Label = "Saving Data..."
        self.textDataSave9Label = "Data Saved."

        self.textNameFile1LabelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_nameFile1label)}</span>"
        self.textUserDataCheckMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_userDataCheck)}</span>"
        self.textMotorStartup3labelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.textMotorStartup3label)}</span>"
        self.textMotorWindDown5LabelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.textMotorWindDown5Label)}</span>"
        self.textSavingData8LabelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.textSavingData8Label)}</span>"
        self.textDataSave9Label_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.textDataSave9Label)}</span>"

        # Screen 1: Naming the file and entering the target flow rate
        self.nameFile1 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)
        self.nameFile1.set_vexpand(True)
        self.nameFile1.set_valign(Gtk.Align.START)

        self.nameFile1label = Gtk.Label()
        self.nameFile1label.set_markup(self.textNameFile1LabelMarkup)
        self.nameFile1label.set_line_wrap(True)
        self.nameFile1label.set_xalign(0)
        self.nameFile1label.set_yalign(0)

        self.nameFile1Entry = Gtk.Entry()
        self.nameFile1Entry.connect("key-press-event", self.saveFileName1)

        self.nameFile1targetFlowRate = Gtk.Entry()
        self.nameFile1targetFlowRate.connect("key-press-event", self.saveFileName1)

        self.nameFile1targetFlowRatePopover = Gtk.Popover()
        self.nameFile1targetFlowRatePopover.set_relative_to(self.nameFile1targetFlowRate)
        self.nameFile1targetFlowRatePopover.set_position(Gtk.PositionType.BOTTOM)

        self.nameFile1targetFlowRateListBox = Gtk.ListBox()
        self.nameFile1targetFlowRatePopover.add(self.nameFile1targetFlowRateListBox)

        for optionLabel, optionValue in params["targetFlowRateOptions"].items():
            row = Gtk.ListBoxRow()
            button = Gtk.Button(label=f"{optionLabel} ({optionValue} gal/sec)")
            button.connect("clicked", lambda btn, value=optionValue: self.setTargetFlowRate(btn, value))
            row.add(button)
            self.nameFile1targetFlowRateListBox.add(row)

        self.nameFile1targetFlowRateListBox.show_all()

        self.nameFile1targetFlowRate.connect("focus-in-event", self.showPopover)

        self.nameFile1NextButton = Gtk.Button(label="Next")
        self.nameFile1NextButton.connect("clicked", lambda btn: self.stack.set_visible_child_name("waitToBegin2"))

        self.nameFile1.pack_start(self.nameFile1Entry, False, False, 10)
        self.nameFile1.pack_start(self.nameFile1targetFlowRate, False, False, 10)
        self.nameFile1.pack_start(self.nameFile1label, False, False, 10)
        self.nameFile1.pack_start(self.nameFile1NextButton, False, False, 10)

        self.stack.add_named(self.nameFile1, "nameFile1")

        # Screen 2: Waits for user input to verify inputs and begin test
        self.waitToBegin2 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.waitToBegin2label = Gtk.Label()
        self.waitToBegin2label.set_markup(self.textUserDataCheckMarkup)
        self.waitToBegin2label.set_line_wrap(True)

        self.waitToBegin2button = Gtk.Button(label="Begin Test")
        self.waitToBegin2button.connect("clicked", self.beginTest)

        self.waitToBegin2Cancel = Gtk.Button(label="Cancel")
        self.waitToBegin2Cancel.connect("clicked", self.resetProgram)

        self.waitToBegin2.pack_start(self.waitToBegin2label, True, True, 0)
        self.waitToBegin2.pack_start(self.waitToBegin2button, True, True, 0)
        self.waitToBegin2.pack_start(self.waitToBegin2Cancel, True, True, 0)
        self.stack.add_named(self.waitToBegin2, "waitToBegin2")

        # Screen 3: Waits for motors to turn on
        self.motorStartup3 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.motorStartup3label = Gtk.Label()
        self.motorStartup3label.set_markup(self.textMotorStartup3labelMarkup)
        self.motorStartup3label.set_line_wrap(True)

        self.motorStartup3.pack_start(self.motorStartup3label, True, True, 0)
        self.stack.add_named(self.motorStartup3, "motorStartup3")

        # Screen 4: Displays data in simple view
        self.dataCollection4Simple = Gtk.Grid()

        self.dataCollection4SimpleLabel = Gtk.Label(label="")
        self.dataCollection4SimpleLabel.set_line_wrap(True)

        self.dataCollection4SimpleEndTestButton = Gtk.Button(label="End Test")
        self.dataCollection4SimpleEndTestButton.connect("clicked", self.endTest)

        self.dataCollection4SimpleToDetailedToggle = Gtk.Button(label="Swap to detailed View")  # Simple symbol for now
        self.dataCollection4SimpleToDetailedToggle.connect("clicked", self.swapToDetailed)

        self.dataCollection4Simple.attach(self.dataCollection4SimpleLabel, 0, 1, 4, 2)
        self.dataCollection4Simple.attach(self.dataCollection4SimpleEndTestButton, 0, 3, 7, 1)
        self.dataCollection4Simple.attach(self.dataCollection4SimpleToDetailedToggle, 6, 0, 1, 1)
        self.dataCollection4Simple.set_column_spacing(96)
        self.dataCollection4Simple.set_row_spacing(48)
        self.stack.add_named(self.dataCollection4Simple, "dataCollection4Simple")

        # Screen 4 alt: Displays data in detailed view
        self.dataCollection4Detailed = Gtk.Grid()

        self.dataCollection4DetailedLabel = Gtk.Label(label="")
        self.dataCollection4DetailedLabel.set_line_wrap(True)

        self.dataCollection4DetailedTemperatureLabel = Gtk.Label(label="")
        self.dataCollection4DetailedTemperatureLabel.set_line_wrap(True)

        self.dataCollection4DetailedEndTestButton = Gtk.Button(label="End Test")
        self.dataCollection4DetailedEndTestButton.connect("clicked", self.endTest)

        self.dataCollection4DetailedToSimpleToggle = Gtk.Button(label="Swap to simple view")  # Simple symbol for now
        self.dataCollection4DetailedToSimpleToggle.connect("clicked", self.swapToSimple)

        self.dataCollection4Detailed.attach(self.dataCollection4DetailedLabel, 0, 1, 2, 2)
        self.dataCollection4Detailed.attach(self.dataCollection4DetailedTemperatureLabel, 6, 1, 2, 2)
        self.dataCollection4Detailed.attach(self.dataCollection4DetailedEndTestButton, 0, 3, 8, 1)
        self.dataCollection4Detailed.attach(self.dataCollection4DetailedToSimpleToggle, 7, 0, 1, 1)
        self.dataCollection4Detailed.set_column_spacing(64)
        self.stack.add_named(self.dataCollection4Detailed, "dataCollection4Detailed")

        # Screen 5: Waits for motors to turn off
        self.motorWindDown5 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.motorWindDown5Label = Gtk.Label()
        self.motorWindDown5Label.set_markup(self.textMotorWindDown5LabelMarkup)
        self.motorWindDown5Label.set_line_wrap(True)

        self.motorWindDown5.pack_start(self.motorWindDown5Label, True, True, 0)
        self.stack.add_named(self.motorWindDown5, "motorWindDown5")

        # Screen 6: Continue Testing Querry
        self.continueTestingQuerry6 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.continueTestingQuerry6NextTest = Gtk.Button(label="Click to begin the next test.")
        self.continueTestingQuerry6EndTesting = Gtk.Button(label="Click to end testing.")
        self.continueTestingQuerry6NextTest.connect("clicked", self.beginTest)
        self.continueTestingQuerry6EndTesting.connect("clicked", self.saveDataQuerry)

        self.continueTestingQuerry6.pack_start(self.continueTestingQuerry6NextTest, True, True, 0)
        self.continueTestingQuerry6.pack_start(self.continueTestingQuerry6EndTesting, True, True, 0)

        self.stack.add_named(self.continueTestingQuerry6, "continueTestingQuerry6")

        # Screen 7: Save Data to file Querry
        self.saveDataQuerry7 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.saveDataQuerry7Save = Gtk.Button(label="Click to pick a file directory to save the test. Program will restart.")
        self.saveDataQuerry7Reset = Gtk.Button(label="Click to restart program without saving.")
        self.saveDataQuerry7Save.connect("clicked", self.saveData)
        self.saveDataQuerry7Reset.connect("clicked", self.resetProgram)

        self.saveDataQuerry7.pack_start(self.saveDataQuerry7Save, True, True, 0)
        self.saveDataQuerry7.pack_start(self.saveDataQuerry7Reset, True, True, 0)

        self.stack.add_named(self.saveDataQuerry7, "saveDataQuerry7")

        # Screen 8: Saving data to file
        self.savingData8 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.savingData8label = Gtk.Label()
        self.savingData8label.set_markup(self.textSavingData8LabelMarkup)
        self.savingData8label.set_line_wrap(True)

        self.savingData8.pack_start(self.savingData8label, True, True, 0)
        self.stack.add_named(self.savingData8, "savingData8")

        # Screen 9: Data saved to file
        self.dataSaved9 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.dataSave9Label = Gtk.Label()
        self.dataSave9Label.set_markup(self.textDataSave9Label_markup)
        self.dataSave9Label.set_line_wrap(True)

        self.dataSaved9.pack_start(self.dataSave9Label, True, True, 0)
        self.stack.add_named(self.dataSaved9, "dataSaved9")

    def saveFileName1(self, widget, event):

        if event.keyval == Gdk.KEY_Return:
            if self.nameFile1Entry.get_text().strip():
                self.fileName = self.nameFile1Entry.get_text()

            try:
                self.targetFlowRate = float(self.nameFile1targetFlowRate.get_text())
            except ValueError:
                None
                
            self.text_userDataCheck = (
                f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
            )
            self.textUserDataCheckMarkup = f"<span size='large'>{GLib.markup_escape_text(self.text_userDataCheck)}</span>"

            try:
                self.I2C = busio.I2C(board.SCL, board.SDA)
                self.ads = ADS.ADS1115(i2c = self.I2C, address = params["ADS1115"]["ADSAddress"], gain = params["ADS1115"]["ADSGain"])
                self.wattChan = AnalogIn(self.ads, ADS.P0, ADS.P1)
                print("ADS1115 is connected")
            except:
                class WattChanFallback:
                    @property
                    def value(self):
                        return -1
                    def voltage(self):
                        return -1
                self.wattChan = WattChanFallback()
                print("ADS1115 is not connected")

            try:
                self.I2C = busio.I2C(board.SCL, board.SDA)
                self.ds3502 = adafruit_ds3502.DS3502(i2c_bus = self.I2C, address = params["DS3502"]["DSAddress"])
                print("DS3502 is connected")
            except:
                print("DS3502 is not connected")

            try:
                self.Temperature = MAX31855(*params["MAX31855Pinout"])
                print("MAX31855 is connected")
            except:
                self.Temperature = -1
                print("MAX31855 is not connected")

            self.stack.set_visible_child_name("waitToBegin2")
            self.waitToBegin2label.set_markup(self.textUserDataCheckMarkup)

    def showPopover(self, widget, event):
        self.nameFile1targetFlowRatePopover.popup()

    def setTargetFlowRate(self, widget, option):
        self.targetFlowRate = option
        self.nameFile1targetFlowRate.set_text(str(option))
        self.nameFile1targetFlowRatePopover.popdown()

    def beginTest(self, *args):
        self.stack.set_visible_child_name("motorStartup3")
        GPIO.output(params["motor"]["pin1"], GPIO.HIGH)
        GPIO.output(params["motor"]["pin2"], GPIO.HIGH)
        GLib.timeout_add(params["motor"]["windUpTime"], self.startDataCollection)

    def startDataCollection(self):
        with params["sensors"]["gas"]["tally"].get_lock(), params["sensors"]["water"]["tally"].get_lock():
            params["sensors"]["gas"]["tally"].value = 0.00
            params["sensors"]["water"]["tally"].value = 0.00

        if self.testUnderWay == False:
            self.endDataCollect.clear()
            self.dataProcess = multiprocessing.Process(
                target=getData, args=(self.queue, self.endDataCollect, self.wattChan, params["DataCollectionFrequency"], self.Temperature, params["ADS1115"]), daemon=True
            )
            self.GasProcess = multiprocessing.Process(
                target=pulseCounter, args=("gas", self.endDataCollect, params["DataCollectionFrequency"]), daemon=True
            )
            self.WaterProcess = multiprocessing.Process(
                target=pulseCounter, args=("water", self.endDataCollect, params["DataCollectionFrequency"]), daemon=True
            )
            self.totalTimeProcess = multiprocessing.Process(
                target=clockTracker, args=(self.endDataCollect, "totalTime"), daemon=True
            )
            self.dataProcess.start()
            self.GasProcess.start()
            self.WaterProcess.start()
            self.totalTimeProcess.start()
            self.testUnderWay = True
        
        self.endTestEvent.clear()
        self.cookTimeProcess = multiprocessing.Process(
            target=clockTracker, args=(self.endTestEvent, "cookTime"), daemon=True
        )
        try:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endTestEvent, self.ds3502, params["DS3502"]), daemon=True
            )
        except:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endTestEvent, -1, params["DS3502"]), daemon=True
            )

        self.ControlProcess.start()
        self.cookTimeProcess.start()
        
        self.stack.set_visible_child_name("dataCollection4Simple")
        return False

    def swapToDetailed(self, *args):
        self.stack.set_visible_child_name("dataCollection4Detailed")

    def swapToSimple(self, *args):
        self.stack.set_visible_child_name("dataCollection4Simple")

    def checkQueue(self):
        while not self.queue.empty():
            self.dataList.append(self.queue.get())
            print(len(self.dataList))
            if len(self.dataList) >= params["dataListMaxLength"]: 
                self.dataList.pop(0)

            dataUpdateDetailedValues = "\n".join(
                f"{key}: {self.dataList[-1][key]['value']} {self.dataList[-1][key]['unit']}"
                for key in self.dataList[-1] if key != "thermocouple no."
            )

            dataUpdateDetailedTemps = "\n".join(
                f"Thermocouple {i + 1}: {temp} {self.dataList[-1]['thermocouple no.']['unit']}"
                for i, temp in enumerate(self.dataList[-1]['thermocouple no.']['value'])
            )

            keys = ["tempAvg", "wattage", "CookTime", "totalTime", "gasUsage", "waterFlow"]
            dataUpdateSimple = "\n".join(
                f"{key.replace('tempAvg', 'Temperature Average').replace('CookTime', 'Cook Time').replace('totalTime', 'Total Time')}: "
                f"{round(self.dataList[-1][key]['value'], 0) if key in ['CookTime', 'totalTime'] else self.dataList[-1][key]['value']} "
                f"{self.dataList[-1][key]['unit']}"
                for key in keys
            )
            
            self.dataCollection4DetailedLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedValues)}</span>")
            self.dataCollection4DetailedTemperatureLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedTemps)}</span>")
            self.dataCollection4SimpleLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateSimple)}</span>")

        return True

    def endTest(self, *args):
        GPIO.output(params["motor"]["pin1"], GPIO.LOW)
        GPIO.output(params["motor"]["pin2"], GPIO.LOW)
        self.endTestEvent.set()
        self.ControlProcess.join()
        self.cookTimeProcess.join()
        self.stack.set_visible_child_name("motorWindDown5")
        self.motor.value = 0
        GLib.timeout_add(params["motor"]["windUpTime"], self.continueTestingQuerry)

    def continueTestingQuerry(self):
        self.stack.set_visible_child_name("continueTestingQuerry6")
        return False

    def saveDataQuerry(self, *args):
        self.endDataCollect.set()
        self.dataProcess.join()
        self.GasProcess.join()
        self.WaterProcess.join()
        self.totalTimeProcess.join()
        with params["sensors"]["gas"]["totalTally"].get_lock(), params["sensors"]["water"]["totalTally"].get_lock():
            params["sensors"]["gas"]["totalTally"].value = 0.00
            params["sensors"]["water"]["totalTally"].value = 0.00
        self.testUnderWay = False
        self.stack.set_visible_child_name("saveDataQuerry7")

    def saveData(self, *args):

        directory = filedialog.askdirectory(title="Save Test")

        if directory: None
        else: return None

        self.stack.set_visible_child_name("savingData8")

        initial_path = os.path.join(directory, self.fileName)
        file_path = duplicateLabeler(initial_path)
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
        ] + [f"Thermocouple {i+1}" for i in range(params["thermoNum"])]

        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)

            writer.writerow(header)

            for entry in self.dataList:
                temperatureReadings = entry["thermocouple no."]["value"]

                writer.writerow([
                    entry["gasFlow"]["value"],
                    entry["tempAvg"]["value"],
                    entry["wattage"]["value"],
                    entry["CookTime"]["value"],
                    entry["totalTime"]["value"],
                    entry["gasUsage"]["value"],
                    entry["waterUsage"]["value"],
                    entry["gasTotalUsage"]["value"],
                    entry["waterFlow"]["value"]
                ] + temperatureReadings)

        self.stack.set_visible_child_name("dataSaved9")
        GLib.timeout_add(5000, self.resetProgram)

    def resetProgram(self, *args):
        self.dataList = []
        self.stack.set_visible_child_name("nameFile1")
        return False


def main():
    GPIO.setmode(GPIO.BCM)

    # Sets up two relays to control two pumps
    # HIGH is closed and on. LOW is open and off
    GPIO.setup(params["motor"]["pin1"], GPIO.OUT)
    GPIO.setup(params["motor"]["pin2"], GPIO.OUT)
    GPIO.output(params["motor"]["pin1"], GPIO.LOW)
    GPIO.output(params["motor"]["pin2"], GPIO.LOW)

    queue = multiprocessing.Queue()
    app = programLoop(queue)
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
    GPIO.cleanup()

if __name__ == "__main__":
    main()
