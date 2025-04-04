import multiprocessing
from multiprocessing import Event, Queue, Value, Process, Lock
import gpiozero
import board
import digitalio
import busio
import adafruit_ads1x15.ads1115 as ADS
import adafruit_ds3502
import adafruit_max31855 # sudo pip3 install adafruit-circuitpython-max31855 --break-system-packages
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
import RPi.GPIO as GPIO
from time import sleep

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# Code Parameters. These control various aspects of the program.
# When modifying pins, unplug all wires connecting to the gpio pins.
# Never wire output pins to ground or other output pins.
# Pin # refers to the physical location of the pin.
# GPIO # refers to the Broadcom pin number. Use these for the code parameters. Using the physical pin numbers erroneously can cause shorts and damage to the pi.

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
ADC_GAIN = 1
VOLTAGE_REF = 4.096 #V
BIT_RESOLUTION = 32768.0 #16-Bit ADC
BURDEN_RESISTOR = 10.0 #Ohms
SCT_RATIO = 100.0 #100A:50mA
VOLTAGE_SUPPLY = 120.0

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

thermoNum = 7
return_farenheit = True

# Collects data every DataCollectFrequency seconds.
# Note: getData is unoptimized and slow, lower values may be auto adjusted to the speed of getData.

DataCollectFrequency = 1

pulsesPerGallon = 1588  
pulsesPerCubicFoot = 1
targetFlowRateDefault = 6
setValveDefault = 127 # 127 Closed, 0    Open

gasTally = Value(c_double, 0.00)
gasTallyTotal = Value(c_double, 0.00)
gasFlowRate = Value('d', 0.00)
gasFlowRateLock = Lock()
waterTally = Value(c_double, 0.00)
waterTallyTotal = Value(c_double, 0.00)
waterFlowRate = Value('d', 0.00)
waterFlowRateLock = Lock()

# Flags for determining if devices are connected properly

flagADS1115 = False
flagMAX31855 = False
flagDS3502 = False
flagAutoFlowCtrl = True

resolution = 800, 480

def flowControl(target, endDataCollect, ds3502):
    setValve = setValveDefault  # 0 Open, 127 Closed
    try:
        ds3502.wiper = setValve
        flagDS3502 = True
        print(flagDS3502)
    except:
        flagDS3502 = False
        print(flagDS3502)
    errorMargin = target * 0.05
    while not endDataCollect.is_set():
        with waterFlowRate.get_lock():
            waterFlow = waterFlowRate.value
        if abs(target - waterFlow) > errorMargin:
            setValve = max(0, min(127, setValve + (1 if target < waterFlow else -1)))
            try:
                ds3502.wiper = setValve
                flagDS3502 = True
            except:
                flagDS3502 = False
        sleep(0.05)
    setValve = setValveDefault
    try:
        ds3502.wiper = setValve * 100
        flagDS3502 = True
    except:
        flagDS3502 = False

def read_power(chan):
    raw_vrms = 0.0
    samples = 500  # Number of samples for averaging
    for _ in range(samples):
        voltage = chan.voltage
        raw_vrms += voltage ** 2
    
    vrms = (raw_vrms / samples) ** 0.5  # Calculate RMS voltage
    current = (vrms / BURDEN_RESISTOR) * SCT_RATIO  # Convert to current
    power = VOLTAGE_SUPPLY * current/17.8
    return power


def getData(queue, totalTime, endDataCollect, wattChan, DataCollectFrequency):
    try:
        Temperature = adafruit_max31855.MAX31855(SCK, CS, S0, T0, T1, T2)
        flagMAX31855 = True
    except:
        flagMAX31855 = False

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
        start_time = time.time()

        if len(gasFlow) >= 1000000:
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
        wattage.append(round(read_power(wattChan))) # Requires ADS1115 to run


        temperatureReadings = []
        for i in range(thermoNum):
            try:
                Temperature.read_data(i)
                temperatureReadings.append(round(Temperature.get_thermocouple_temp(return_farenheit), 2))
            except:
                temperatureReadings.append(round(5, 2))
        allTemperatureReadings.append(temperatureReadings)
        tempAvg.append(round(sum(allTemperatureReadings[-1])/len(allTemperatureReadings[-1]), 2))

        if len(allTemperatureReadings[-1]) < 8:
                for i in range(8 - len(allTemperatureReadings[-1])):
                   allTemperatureReadings[-1].append("Unused")
        with gasTally.get_lock(), gasFlowRate.get_lock(), waterTally.get_lock(), waterFlowRate.get_lock(), gasTallyTotal.get_lock():
            gasUsage.append(round(gasTally.value, 2))
            gasFlow.append(round(gasFlowRate.value, 2))
            waterUsage.append(round(waterTally.value, 2))
            waterFlow.append(round(waterFlowRate.value, 2))
            gasTotalUsage.append(round(gasTallyTotal.value, 2))


        CookTime.append(round(CookTime[-1] + DataCollectFrequency, 2))
        totalTime.append(round(totalTime[-1] + DataCollectFrequency, 2))

        queue.put(gasFlow[-1])
        queue.put(allTemperatureReadings[-1])
        queue.put(tempAvg[-1])
        queue.put(wattage[-1])
        queue.put(CookTime[-1])
        queue.put(totalTime[-1])
        queue.put(gasUsage[-1])
        queue.put(waterUsage[-1])
        queue.put(waterFlow[-1])
        queue.put(gasTotalUsage[-1])

        elapsed_time = time.time() - start_time
        sleep_time = max(0, DataCollectFrequency - elapsed_time)
        if elapsed_time > DataCollectFrequency:
            DataCollectFrequency = elapsed_time
            print(f"DataCollectFrequency adjusted to {DataCollectFrequency}. Optimizations needed to reach requested rate.")
        time.sleep(sleep_time)

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
        self.set_default_size(*resolution)
        self.set_resizable(False)
        self.set_border_width(8)

        self.dataProcess = None
        self.queue = queue

        GLib.timeout_add(100, self.check_queue)

        self.gasFlow = [0]
        self.allTemperatureReadings = [[]]
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


        self.text_userDataCheck = (
            f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
        )
        self.text_userDataCheck_nowattmeter = (
            f"Warning: Wattmeter is not connected correctly. Please check the wiring and hit cancel if this is unintentional.\n\nPress \"Begin Test\" to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.targetFlowRate}"
        )
        self.text_nameFilelabel1 = (
            f"Welcome to the simulated ASTM F1361 test apparatus.\nPlease read the user manual prior to setting up this test.\nEnsure that the sensors are affixed to the frier being tested.\nEnter a file name for saving the test in the first box.\nIf the file already exists, it will be overwritten.\nEnter a file directory in the second box.\nIf none is given, the default will be attempted\nEnter the target flow rate in the third box.\nPress Enter to continue."
        )

        self.text_motorStartuplabel = "The motors should be turning on.\nIf they do not, end the test and contact the VULCAN_FRY team."
        self.text_motorWindDownlabel = "The motors should be turning off.\nIf they do not, end the test and contact the VULCAN_FRY team."
        self.text_savingDatalabel = "Saving Data..."
        self.text_dataSavelabel = "Data Saved."

        self.text_nameFilelabel1_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_nameFilelabel1)}</span>"
        self.text_userDataCheck_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_userDataCheck)}</span>"
        self.text_userDataCheck_nowattmeter_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_userDataCheck_nowattmeter)}</span>"
        self.text_motorStartuplabel_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_motorStartuplabel)}</span>"
        self.text_motorWindDownlabel_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_motorWindDownlabel)}</span>"
        self.text_savingDatalabel_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_savingDatalabel)}</span>"
        self.text_dataSavelabel_markup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_dataSavelabel)}</span>"

        # Screen 1: Naming the file
        self.nameFile1 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)
        self.nameFile1.set_vexpand(True)
        self.nameFile1.set_valign(Gtk.Align.START)

        self.nameFilelabel1 = Gtk.Label()
        self.nameFilelabel1.set_markup(self.text_nameFilelabel1_markup)
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

        self.waitToBeginlabel = Gtk.Label()
        self.waitToBeginlabel.set_markup(self.text_userDataCheck_markup)
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

        self.motorStartuplabel = Gtk.Label()
        self.motorStartuplabel.set_markup(self.text_motorStartuplabel_markup)
        self.motorStartuplabel.set_line_wrap(True)

        self.motorStartup3.pack_start(self.motorStartuplabel, True, True, 0)
        self.stack.add_named(self.motorStartup3, "motorStartup3")

        # Screen 4: Displays Data until user Input
        self.dataCollection4 = Gtk.Grid()

        self.dataCollectionlabelSimple = Gtk.Label(label="")
        self.dataCollectionlabelSimple.set_line_wrap(True)

        self.dataCollectionbutton = Gtk.Button(label="End Test")
        self.dataCollectionbutton.connect("clicked", self.endTest)

        self.topRightButton = Gtk.Button(label="Swap to detailed View")  # Simple symbol for now
        self.topRightButton.connect("clicked", self.swapToDetailed)

        self.dataCollection4.attach(self.dataCollectionlabelSimple, 0, 1, 4, 2)
        self.dataCollection4.attach(self.dataCollectionbutton, 0, 3, 7, 1)
        self.dataCollection4.attach(self.topRightButton, 6, 0, 1, 1)
        self.dataCollection4.set_column_spacing(96)
        self.dataCollection4.set_row_spacing(48)
        self.stack.add_named(self.dataCollection4, "dataCollection4")

        # Screen 4_2: Displays Data until user Input
        self.dataCollection4_2 = Gtk.Grid()

        self.dataCollectionlabelDetailedValues = Gtk.Label(label="")
        self.dataCollectionlabelDetailedValues.set_line_wrap(True)

        self.dataCollectionlabelDetailedTemps = Gtk.Label(label="")
        self.dataCollectionlabelDetailedTemps.set_line_wrap(True)

        self.dataCollectionbutton_2 = Gtk.Button(label="End Test")
        self.dataCollectionbutton_2.connect("clicked", self.endTest)

        self.topRightButton_2 = Gtk.Button(label="Swap to simple view")  # Simple symbol for now
        self.topRightButton_2.connect("clicked", self.swapToSimple)

        self.dataCollection4_2.attach(self.dataCollectionlabelDetailedValues, 0, 1, 2, 2)
        self.dataCollection4_2.attach(self.dataCollectionlabelDetailedTemps, 6, 1, 2, 2)
        self.dataCollection4_2.attach(self.dataCollectionbutton_2, 0, 3, 8, 1)
        self.dataCollection4_2.attach(self.topRightButton_2, 7, 0, 1, 1)
        self.dataCollection4_2.set_column_spacing(64)
        self.stack.add_named(self.dataCollection4_2, "dataCollection4_2")

        # Screen 5: Waits for motors to turn off
        self.motorWindDown5 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.motorWindDownlabel = Gtk.Label()
        self.motorWindDownlabel.set_markup(self.text_motorWindDownlabel_markup)
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

        self.DQbuttonSave = Gtk.Button(label="Click to pick a file directory to save the test. Program will restart.")
        self.DQbuttonReset = Gtk.Button(label="Click to restart program without saving.")
        self.DQbuttonSave.connect("clicked", self.saveData)
        self.DQbuttonReset.connect("clicked", self.resetProgram)

        self.saveDataQuerry7.pack_start(self.DQbuttonSave, True, True, 0)
        self.saveDataQuerry7.pack_start(self.DQbuttonReset, True, True, 0)

        self.stack.add_named(self.saveDataQuerry7, "saveDataQuerry7")

        # Screen 8: Saving data to file
        self.savingData8 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.savingDatalabel = Gtk.Label()
        self.savingDatalabel.set_markup(self.text_savingDatalabel_markup)
        self.savingDatalabel.set_line_wrap(True)

        self.savingData8.pack_start(self.savingDatalabel, True, True, 0)
        self.stack.add_named(self.savingData8, "savingData8")

        # Screen 9: Data saved to file
        self.dataSaved9 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.dataSavelabel = Gtk.Label()
        self.dataSavelabel.set_markup(self.text_dataSavelabel_markup)
        self.dataSavelabel.set_line_wrap(True)

        self.dataSaved9.pack_start(self.dataSavelabel, True, True, 0)
        self.stack.add_named(self.dataSaved9, "dataSaved9")

    def saveFileName1(self, widget, event):

        self.targetFlowRate = targetFlowRateDefault
        self.fileName = "Test"
        #try:
        self.I2C = busio.I2C(board.SCL, board.SDA)   # Set up the Wattage Sensor
        self.ads = ADS.ADS1115(i2c = self.I2C, address = 0x48, gain = 1) # Requires ADS11 to run
        self.wattChan = AnalogIn(self.ads, ADS.P0, ADS.P1) # Requires ADS1115 to run
        flagADS1115 = True
        print(self.I2C)
        """
        except:
            class WattChanFallback:
                @property
                def value(self):
                    return -1
            flagADS1115 = False
            self.wattChan = WattChanFallback()
            self.detectWattSensor = False
            print(flagADS1115)
        """
        try:
            self.I2C = busio.I2C(board.SCL, board.SDA)   # Set up the Wattage Sensor
            print(self.I2C)
            self.ds3502 = adafruit_ds3502.DS3502(i2c_bus = self.I2C, address = 0x28)
            flagDS3502 = True
            print(flagDS3502)
        except:
            flagDS3502 = False
        with gasTallyTotal.get_lock():
            gasTallyTotal.value = 0.00
        with waterTallyTotal.get_lock():
            waterTallyTotal.value = 0.00
        if event.keyval == Gdk.KEY_Return:
            if self.nameFileEntry1.get_text().strip():
                self.fileName = self.nameFileEntry1.get_text()
            target_flow_rate_input = self.targetFlowRate1.get_text()
            try:
                self.targetFlowRate = float(target_flow_rate_input)
            except ValueError:
                self.targetFlowRate = self.targetFlowRate
            self.stack.set_visible_child_name("waitToBegin2")
            if detectWattSensor:
                self.waitToBeginlabel.set_markup(self.text_userDataCheck_markup)
            else:
                self.waitToBeginlabel.set_markup(self.text_userDataCheck_nowattmeter_markup)

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
            target=getData, args=(self.queue, totalTime, self.endDataCollect, self.wattChan, DataCollectFrequency), daemon=True
        )
        self.GasProcess = multiprocessing.Process(
            target=gasCounter, args=(self.endDataCollect, ), daemon=True
        )
        self.WaterProcess = multiprocessing.Process(
            target=waterCounter, args=(self.endDataCollect, ), daemon=True
        )
        try:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endDataCollect, self.ds3502), daemon=True
            )
        except:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.targetFlowRate, self.endDataCollect, -1), daemon=True
            )

        self.dataProcess.start()
        self.GasProcess.start()
        self.WaterProcess.start()
        self.ControlProcess.start()
        self.stack.set_visible_child_name("dataCollection4")
        return False

    def swapToDetailed(self, *args):
        self.stack.set_visible_child_name("dataCollection4_2")

    def swapToSimple(self, *args):
        self.stack.set_visible_child_name("dataCollection4")

    def check_queue(self):
        while not self.queue.empty():
            self.gasFlow.append(self.queue.get())
            self.allTemperatureReadings.append(self.queue.get())
            self.tempAvg.append(self.queue.get())
            self.wattage.append(self.queue.get())
            self.CookTime.append(self.queue.get())
            self.totalTime.append(self.queue.get())
            self.gasUsage.append(self.queue.get())
            self.waterUsage.append(self.queue.get())
            self.waterFlow.append(self.queue.get())
            self.gasTotalUsage.append(self.queue.get())

            dataUpdateDetailedValues = (
                f"gasFlow: {self.gasFlow[-1]}\n"
                f"tempAvg: {self.tempAvg[-1]}\n"
                f"wattage: {self.wattage[-1]}\n"
                f"CookTime: {self.CookTime[-1]}\n"
                f"totalTime: {self.totalTime[-1]}\n"
                f"gasUsage: {self.gasUsage[-1]}\n"
                f"waterUsage: {self.waterUsage[-1]}\n"
                f"waterFlow: {self.waterFlow[-1]}\n"
                f"gasTotalUsage: {self.gasTotalUsage[-1]}\n"
            )
            dataUpdateDetailedTemps = (
                f"Thermocouple 1: {self.allTemperatureReadings[-1][0]}\n"
                f"Thermocouple 2: {self.allTemperatureReadings[-1][1]}\n"
                f"Thermocouple 3: {self.allTemperatureReadings[-1][2]}\n"
                f"Thermocouple 4: {self.allTemperatureReadings[-1][3]}\n"
                f"Thermocouple 5: {self.allTemperatureReadings[-1][4]}\n"
                f"Thermocouple 6: {self.allTemperatureReadings[-1][5]}\n"
                f"Thermocouple 7: {self.allTemperatureReadings[-1][6]}\n"
                f"Thermocouple 8: {self.allTemperatureReadings[-1][7]}\n"
            )
            dataUpdateSimple = (
                f"Temperature Average: {self.tempAvg[-1]}\n"
                f"Wattage: {self.wattage[-1]}\n"
                f"Cook Time: {self.CookTime[-1]}\n"
                f"Total Time: {self.totalTime[-1]}\n"
                f"Gas Usage: {self.gasUsage[-1]}\n"
                f"Water Flow: {self.waterFlow[-1]}\n"
            )
            self.dataCollectionlabelDetailedValues.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedValues)}</span>")
            self.dataCollectionlabelDetailedTemps.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedTemps)}</span>")
            self.dataCollectionlabelSimple.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateSimple)}</span>")

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

            for i in range(len(self.gasFlow)):
                temp_readings = self.allTemperatureReadings[i] if i < len(self.allTemperatureReadings) else [None] * thermoNum

                writer.writerow([
                    self.gasFlow[i],
                    self.tempAvg[i],
                    self.wattage[i],
                    self.CookTime[i],
                    self.totalTime[i],
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
        self.allTemperatureReadings = [[]]
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
    try:
        spi = board.SPI()   # Set up the Thermocoupler
        cs = digitalio.DigitalInOut(board.D5)
        max31855 = adafruit_max31855.MAX31855(spi, cs)

    except:
        None

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
