import multiprocessing
from multiprocessing import Event, Queue, Value, Process, Lock
import gpiozero
import board
import digitalio
import busio
import adafruit_ads1x15.ads1115 as ADS # sudo pip3 install adafruit-circuitpython-ads1x15 --break-system-packages
import adafruit_ds3502 # sudo pip3 install adafruit-circuitpython-ds3502 --break-system-packages
import adafruit_max31855 # sudo pip3 install adafruit-circuitpython-max31855 --break-system-packages
import RPi.GPIO as GPIO
from adafruit_ads1x15.analog_in import AnalogIn
from time import sleep
import os
from ctypes import c_double
import csv
import gi
import time
from tkinter import filedialog
import RPi.GPIO as GPIO
from time import sleep
import numpy as np

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# Code Parameters. These control various aspects of the program.
# When modifying pins, unplug all wires connecting to the gpio pins.
# Never wire output pins to ground or other output pins.
# Pin # refers to the physical location of the pin. Refer to these values when wiring.
# GPIO # refers to the Broadcom pin number. Use these for the code parameters. Using the physical pin numbers erroneously can cause shorts and damage to the pi.
# For more information, refer to the 40-pin header diagram in the raspberry pi documentaton.
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html

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

# ADS1115 & DS3502
# Pin # 3 5
# GPIO # 2 3
# SDA1, SCL1
# Do not connect the touch screen i2c pins to the pi. Ribbon cable is sufficient and program does not handle this case.

ADSAddress = 0x48
ADSGain = 1 # Gain for the ADS1115 chip. 
ADSSamples = 500 #Number of samples to take for the RMS calculation.
burdenResistor = 10.0 # Ohms
SCTRatio = 100.0 # 100A:50mA
voltageSupply = 120.0 # Change this value to match voltage running through wire.
currentCorrection = 17.8 # Adjustment value to correct current calculation. Our readPower function likely has an error in the current calculation, may need investigation.

DSAddress = 0x28
targetFlowRateDefault = 6 # Default target flow rate if user does not enter a value.
setValveDefault = 127 # 127 Closed, 0 Open
valveAdjustmentFrequency = 0.05 # How often the valve is adjusted in seconds.

# Gas Input
# Pin # 31 (Pin 29 might be busted, check later. I made Gas and Water Identical for the next time this is checked)
# GPIO # 6

gasPin = 6
pulsesPerCubicFoot = 1

# Water Input (Needs to be changed to better match expected flow)
# Pin # 22
# GPIO # 25

waterPin = 25
pulsesPerGallon = 1588

# Relay Control
# Pin # 32 33
# GPIO # 12, 13
# Motor 1 and 2

motorPin1 = 12
motorPin2 = 13
motorWindUpTime = 5000 # Time in milliseconds to wait for the motors to turn on.

# Number of active Thermocouples. Wire these in numerical order starting from 0 on the MAX31855.

thermoNum = 7
returnFarenheit = True # Returns Celsius

# Collects data every DataCollectionFrequency seconds.
# Note: getData is unoptimized and slow, lower values may be auto adjusted to the speed of getData.

DataCollectionFrequency = 1

# Tracks totals and rates for gas and water usage

gasTally = Value(c_double, 0.00)
gasTallyTotal = Value(c_double, 0.00)
gasFlowRate = Value('d', 0.00)
gasFlowRateLock = Lock()
waterTally = Value(c_double, 0.00)
waterTallyTotal = Value(c_double, 0.00)
waterFlowRate = Value('d', 0.00)
waterFlowRateLock = Lock()
cookTime = Value(c_double, 0.00)
cookTimeLock = Lock()
totalTime = Value(c_double, 0.00)
totalTimeLock = Lock()

dataListMaxLength = 1000000 # Attempts to prevent ram overflow by limiting list size. Ram overflow can freeze the program, resulting in test data loss. 100000 is equivalent to 277 hours of data at default DataCollectionFrequency = 1. Modify with care, or modify program to check for avalible ram.
resolution = 800, 480
defaultFileName = "Test"

def readPower(chan):
    rawVrms = 0.0
    samples = ADSSamples
    for _ in range(samples):
        voltage = chan.voltage
        rawVrms += voltage ** 2
    
    vrms = (rawVrms / samples) ** 0.5
    current = (vrms / burdenResistor) * SCTRatio / currentCorrection # Note: currentCorrection is a bandaid fix for adjusting read current to expected value. May need fixed in the future.
    power = voltageSupply * current
    return power

# Adds a number to the end of the file name if it already exists.

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
# Between tests CurrentTimeTracker is stopped and set to 0
# Between tests flowControl is set to close the valve
# All other functions run and collect data during and between tests until self.continueTestingQuerry6EndTesting = Gtk.Button(label="Click to end testing.") is pressed.

def flowControl(target, endDataCollect, ds3502):
    setValve = setValveDefault  # 0 Open, 127 Closed

    try:
        ds3502.wiper = setValve
        print("DS3502 is connected")
    except:
        print("DS3502 is not connected")

    errorMargin = target * 0.05

    while not endDataCollect.is_set():
        with waterFlowRate.get_lock():
            waterFlow = waterFlowRate.value
        if abs(target - waterFlow) > errorMargin:
            setValve = max(0, min(127, setValve + (1 if target < waterFlow else -1)))
            try:
                ds3502.wiper = setValve
            except:
                None
        sleep(valveAdjustmentFrequency)

    setValve = setValveDefault

    try:
        ds3502.wiper = setValve
    except:
        None

def currentTimeTracker(endDataCollect):
    startTime = time.time()
    while not endDataCollect.is_set():
        currentTime = time.time()
        with cookTimeLock:
            cookTime.value = round(currentTime - startTime, 2)

    with cookTime.get_lock():
        cookTime.value = 0

def totalTimeTracker(endDataCollect):
    startTime = time.time()
    while not endDataCollect.is_set():
        currentTime = time.time()
        with totalTimeLock:
            totalTime.value = round(currentTime - startTime, 2)

    with totalTime.get_lock():
        totalTime.value = 0   

def getData(queue, endDataCollect, wattChan, DataCollectionFrequency, Temperature):
    try:
        Temperature = adafruit_max31855.MAX31855(SCK, CS, S0, T0, T1, T2)
        print("MAX31855 is connected")
    except:
        print("MAX31855 is not connected")

    data = {
        "gasFlow": 0,
        "thermocouple no.": [0 for _ in range(thermoNum)],
        "tempAvg": 0,
        "wattage": 0,
        "CookTime": 0,
        "totalTime": 0,
        "gasUsage": 0,
        "waterUsage": 0,
        "waterFlow": 0,
        "gasTotalUsage": 0
    }

    startTime = time.time()

    while not endDataCollect.is_set():
        data["wattage"] = round(readPower(wattChan))

        for i in range(thermoNum):
            try:
                Temperature.read_data(i)
                data("thermocouple no.")(i) = round(Temperature.get_thermocouple_temp(returnFarenheit), 2)
            except:
                data("thermocouple no.")(i) = round(-1, 2)

        data("tempAvg") = round(np.mean(data("thermocouple no.")), 2)

        if len(data("thermocouple no.")) < 8:
            data("thermocouple no.").extend(["Unused"] * (8 - len(data("thermocouple no."))))

        with gasTally.get_lock(), gasFlowRate.get_lock(), waterTally.get_lock(), waterFlowRate.get_lock(), gasTallyTotal.get_lock(), cookTime.get_lock(), totalTime.get_lock():
            data("gasUsage") = round(gasTally.value, 2)
            data("gasFlow") = round(gasFlowRate.value, 2)
            data("waterUsage") = round(waterTally.value, 2)
            data("waterFlow") = round(waterFlowRate.value, 2)
            data("gasTotalUsage") = round(gasTallyTotal.value, 2)
            data("CookTime") = round(cookTime.value, 2)
            data("totalTime") = round(totalTime.value, 2)

        queue.put(data)
        elapsedTime = time.time() - startTime
        sleepTime = max(0, DataCollectionFrequency - elapsedTime)
        if elapsedTime > DataCollectionFrequency:
            DataCollectionFrequency = elapsedTime
            print(f"DataCollectionFrequency adjusted to {DataCollectionFrequency}. Optimizations needed to reach requested rate.")
        time.sleep(sleepTime)

def gasCounter(endDataCollect):
    edgeCount = 0
    lastState = GPIO.LOW
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gasPin, GPIO.IN)
    secondTracker = time.time()

    while  not endDataCollect.is_set():
        currentState = GPIO.input(gasPin)

        if currentState == GPIO.HIGH and lastState == GPIO.LOW:
            edgeCount += 1

        if time.time() >= secondTracker + DataCollectionFrequency:
            instantaneousFlow = edgeCount / pulsesPerCubicFoot
            with gasTally.get_lock():
                gasTally.value += instantaneousFlow
            with gasTallyTotal.get_lock():
                gasTallyTotal.value += instantaneousFlow
            with gasFlowRateLock:
                gasFlowRate.value = instantaneousFlow / DataCollectionFrequency

            secondTracker = time.time()
            edgeCount = 0

        lastState = currentState

def waterCounter(endDataCollect):
    edgeCount = 0
    lastState = GPIO.LOW
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(waterPin, GPIO.IN)
    secondTracker = time.time()

    while  not endDataCollect.is_set():
        currentState = GPIO.input(waterPin)

        if currentState == GPIO.HIGH and lastState == GPIO.LOW:
            edgeCount += 1

        if time.time() >= secondTracker + DataCollectionFrequency:
            instantaneousFlow = edgeCount / pulsesPerGallon
            with waterTally.get_lock():
                waterTally.value += instantaneousFlow
            with waterTallyTotal.get_lock():
                waterTallyTotal.value += instantaneousFlow
            with waterFlowRateLock:
                waterFlowRate.value = instantaneousFlow / DataCollectionFrequency

            secondTracker = time.time()
            edgeCount = 0

        lastState = currentState

class programLoop(Gtk.Window):

    def __init__(self, queue):
        super().__init__(title="Looping App")
        self.endTestEvent = Event()
        self.endDataCollect = Event()
        self.testUnderWay = False
        self.set_default_size(*resolution)
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

        self.stack = Gtk.Stack()
        self.add(self.stack)
        self.targetFlowRate = targetFlowRateDefault

        self.text_userDataCheck = (
            f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
        )

        self.text_nameFile1label = (
            f"Welcome to the simulated ASTM F1361 test apparatus.\nPlease read the user manual prior to setting up this test.\nEnsure that the sensors are affixed to the frier being tested.\nEnter a file name for saving the test in the first box.\nIf the file already exists, an extension (#) will be added.\nEnter a file directory in the second box.\nIf none is given, the default will be attempted\nEnter the target flow rate in the third box.\nPress Enter to continue."
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

        self.targetFlowRate = Gtk.Entry()
        self.targetFlowRate.connect("key-press-event", self.saveFileName1)

        self.nameFile1.pack_start(self.nameFile1Entry, False, False, 10)
        self.nameFile1.pack_start(self.targetFlowRate, False, False, 10)
        self.nameFile1.pack_start(self.nameFile1label, False, False, 10)

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
        self.targetFlowRate = targetFlowRateDefault
        self.fileName = defaultFileName

        try:
            self.I2C = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c = self.I2C, address = ADSAddress, gain = ADSGain)
            self.wattChan = AnalogIn(self.ads, ADS.P0, ADS.P1)
            print("ADS1115 is connected")
        except:
            class WattChanFallback:
                @property
                def value(self):
                    return -1
            self.wattChan = WattChanFallback()
            print("ADS1115 is not connected")

        try:
            self.I2C = busio.I2C(board.SCL, board.SDA)
            self.ds3502 = adafruit_ds3502.DS3502(i2c_bus = self.I2C, address = DSAddress)
            print("DS3502 is connected")
        except:
            print("DS3502 is not connected")

        try:
            self.Temperature = adafruit_max31855.MAX31855(SCK, CS, S0, T0, T1, T2)
            print("MAX31855 is connected")
        except:
            print("MAX31855 is not connected")

        if event.keyval == Gdk.KEY_Return:
            if self.nameFile1Entry.get_text().strip():
                self.fileName = self.nameFile1Entry.get_text()

            try:
                self.targetFlowRate = float(self.targetFlowRate.get_text())
            except ValueError:
                self.targetFlowRate = self.targetFlowRate

            self.stack.set_visible_child_name("waitToBegin2")
            self.waitToBegin2label.set_markup(self.textUserDataCheckMarkup)

    def beginTest(self, *args):
        self.stack.set_visible_child_name("motorStartup3")
        GPIO.output(motorPin1, GPIO.HIGH)
        GPIO.output(motorPin2, GPIO.HIGH)
        GLib.timeout_add(motorWindUpTime, self.startDataCollection)

    def startDataCollection(self):
        with gasTally.get_lock():
            gasTally.value = 0.00
        with waterTally.get_lock():
            waterTally.value = 0.00

        if self.testUnderWay == False:
            self.endDataCollect.clear()
            self.dataProcess = multiprocessing.Process(
                target=getData, args=(self.queue, self.endDataCollect, self.wattChan, DataCollectionFrequency, self.Temperature), daemon=True
            )
            self.GasProcess = multiprocessing.Process(
                target=gasCounter, args=(self.endDataCollect, ), daemon=True
            )
            self.WaterProcess = multiprocessing.Process(
                target=waterCounter, args=(self.endDataCollect, ), daemon=True
            )
            self.totalTimeProcess = multiprocessing.Process(
                target=totalTimeTracker, args=(self.endDataCollect,), daemon=True
            )
            self.dataProcess.start()
            self.GasProcess.start()
            self.WaterProcess.start()
            self.totalTimeProcess.start()
            self.testUnderWay = True
        
        self.endTestEvent.clear()
        self.cookTimeProcess = multiprocessing.Process(
            target=currentTimeTracker, args=(self.endTestEvent,), daemon=True
        )
        try:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endTestEvent, self.ds3502), daemon=True
            )
        except:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endTestEvent, -1), daemon=True
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

            if len(self.dataList) >= dataListMaxLength: 
                self.dataList.pop(0)

            dataUpdateDetailedValues = (
                f"gasFlow: {self.dataList[-1]["gasFlow"]} cu ft / sec\n"
                f"tempAvg: {self.dataList[-1]["tempAvg"]} F\n"
                f"wattage: {self.dataList[-1]["wattage"]} W\n"
                f"CookTime: {self.dataList[-1]["CookTime"]} sec\n"
                f"totalTime: {self.dataList[-1]["totalTime"]} sec\n"
                f"gasUsage: {self.dataList[-1]["gasUsage"]} cu ft\n"
                f"waterUsage: {self.dataList[-1]["waterUsage"]} gal\n"
                f"waterFlow: {self.dataList[-1]["waterFlow"]} gal / sec\n"
                f"gasTotalUsage: {self.dataList[-1]["gasTotalUsage"]} cu ft\n"
            )
            dataUpdateDetailedTemps = (
                f"Thermocouple 1: {self.dataList[-1]["thermocouple no."][0]} F\n"
                f"Thermocouple 2: {self.dataList[-1]["thermocouple no."][1]} F\n"
                f"Thermocouple 3: {self.dataList[-1]["thermocouple no."][2]} F\n"
                f"Thermocouple 4: {self.dataList[-1]["thermocouple no."][3]} F\n"
                f"Thermocouple 5: {self.dataList[-1]["thermocouple no."][4]} F\n"
                f"Thermocouple 6: {self.dataList[-1]["thermocouple no."][5]} F\n"
                f"Thermocouple 7: {self.dataList[-1]["thermocouple no."][6]} F\n"
                f"Thermocouple 8: {self.dataList[-1]["thermocouple no."][7]} F\n"
            )
            dataUpdateSimple = (
                f"Temperature Average: {self.dataList[-1]["tempAvg"]} F\n"
                f"Wattage: {self.dataList[-1]["wattage"]} W\n"
                f"Cook Time: {self.dataList[-1]["CookTime"]} sec\n"
                f"Total Time: {self.dataList[-1]["totalTime"]} sec\n"
                f"Gas Usage: {self.dataList[-1]["gasUsage"]} cu ft\n"
                f"Water Flow: {self.dataList[-1]["waterFlow"]} gal/sec\n"
            )
            self.dataCollection4DetailedLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedValues)}</span>")
            self.dataCollection4DetailedTemperatureLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedTemps)}</span>")
            self.dataCollection4SimpleLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateSimple)}</span>")

        return True

    def endTest(self, *args):
        GPIO.output(motorPin1, GPIO.LOW)
        GPIO.output(motorPin2, GPIO.LOW)
        self.endTestEvent.set()
        self.ControlProcess.join()
        self.cookTimeProcess.join()
        self.stack.set_visible_child_name("motorWindDown5")
        self.motor.value = 0
        GLib.timeout_add(motorWindUpTime, self.continueTestingQuerry)

    def continueTestingQuerry(self):
        self.stack.set_visible_child_name("continueTestingQuerry6")
        return False

    def saveDataQuerry(self, *args):
        self.endDataCollect.set()
        self.dataProcess.join()
        self.GasProcess.join()
        self.WaterProcess.join()
        self.totalTimeProcess.join()
        with gasTallyTotal.get_lock():
            gasTallyTotal.value = 0.00
        with waterTallyTotal.get_lock():
            waterTallyTotal.value = 0.00
        self.testUnderWay = False
        self.stack.set_visible_child_name("saveDataQuerry7")

    def saveData(self, *args):

        directory = filedialog.askdirectory(title="Save Test")

        if directory:
            None
        else:
            return None

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
        ] + [f"Thermocouple {i+1}" for i in range(thermoNum)]

        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)

            writer.writerow(header)

            for i in range(len(self.dataList)):
                temperatureReadings = self.dataList[i]["thermocouple no."] if i < len(self.dataList[i]["thermocouple no."]) else [None] * thermoNum

                writer.writerow([
                    self.dataList[i]["gasFlow"],
                    self.dataList[i]["tempAvg"],
                    self.dataList[i]["wattage"],
                    self.dataList[i]["CookTime"],
                    self.dataList[i]["totalTime"],
                    self.dataList[i]["gasUsage"],
                    self.dataList[i]["waterUsage"],
                    self.dataList[i]["gasTotalUsage"],
                    self.dataList[i]["waterFlow"]
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
    GPIO.setup(motorPin1, GPIO.OUT)
    GPIO.setup(motorPin2, GPIO.OUT)
    GPIO.output(motorPin1, GPIO.LOW)
    GPIO.output(motorPin2, GPIO.LOW)

    queue = multiprocessing.Queue()
    app = programLoop(queue)
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
    GPIO.cleanup()

if __name__ == "__main__":
    main()
