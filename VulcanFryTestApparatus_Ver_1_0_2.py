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
from contextlib import ExitStack
import RPi.GPIO as GPIO
from time import sleep
from max31855 import MAX31855

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

thermoNum = 6

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
        "TargetTemperatureDefault": 350,
        "setValveDefault": 127,
        "valveAdjustmentFrequency": 0.05,
        "margin": 0.05 # The allowed variance in temperature once target is reached before the valve attempts to correct to target again.
    },
    "TargetTemperatureOptions": { # The target average temperature to reach. The flow control valve will read tempAvg and then open the valve untill 
        "Option A": 310,
        "Option B": 320,
        "Option C": 330,
        "Option D": 340,
        "Option E": 350
    },
    "sensors": {
        "gas": {"pin": 6, "pulses_per_unit": 1, "tally": Value('d', 0.00), "totalTally": Value('d', 0.00), "flowRate": Value('d', 0.00)},
        "water": {"pin": 25, "pulses_per_unit": 1588, "tally": Value('d', 0.00), "totalTally": Value('d', 0.00), "flowRate": Value('d', 0.00)},
        "temperature": {"thermocouple no.": [Value('d', 0.00) for _ in range(thermoNum)], "tempAvg": Value('d', 0.00), "thermocouple name": {0: "Water Out", 1: "Water In", 2: "HX In", 3: "HX Out", 4: "Fryer HX Out", 5: "Fryer HX In", 6: "Spare 1", 7: "Spare 2"}},
        "power" : Value('d', 0.00),
        "BTU": Value('d', 0.00)
    },
    "motor": {
        "pin1": 12,
        "pin2": 13,
        "windUpTime": 500
    },
    "thermoNum": thermoNum,
    "DataCollectionFrequency": 1, # Reading the MAX31855, the fastest this can go is ~0.88.
    "clocks": {
        "cookTime": Value(c_double, 0.00),
        "totalTime": Value(c_double, 0.00)
    },
    "dataListMaxLength": 2147483647,
    "resolution": (800, 428),
    "defaultFileName": "Test",
    "significantFigures": 2,
    "returnFarenheit": True,  # Set to True to return Farenheit, False for Celsius
    "windUpTime": 10000 # Time in miliseconds untill temperature target is checked. Idle Oil in apparatus is expected to be cool before a test starts untill hot oil begins flowing from the fryer?
}

def readPower(chan, endDataCollect):
    rawVrms = 0.0
    samples = params['ADS1115']['ADSSamples']
    supply = params['ADS1115']['voltageSupply']
    while not endDataCollect.is_set():
        for _ in range(samples):
            voltage = chan.voltage
            rawVrms += voltage ** 2
    
        vrms = (rawVrms / samples) ** 0.5
        current = (vrms / params['ADS1115']["burdenResistor"]) * params['ADS1115']["SCTRatio"] / params['ADS1115']["currentCorrection"] # Note: currentCorrection is a bandaid fix for adjusting read current to expected value. May need fixed in the future.
        with params['sensors']['power'].get_lock():
            params['sensors']['power'].value = round(supply * current, params['significantFigures'])
        rawVrms = 0.0
            
    with params['sensors']['power'].get_lock():
            params['sensors']['power'].value = 0

def readTemperature(endDataCollect):
    try:
        Temperature = MAX31855(*params["MAX31855Pinout"])
        print("MAX31855 is connected")
    except:
        print("MAX31855 is not connected")

    if len(params["sensors"]["temperature"]["thermocouple no."]) < 8:
            params["sensors"]["temperature"]["thermocouple no."].extend(["Unused"] * (8 - len(params["sensors"]["temperature"]["thermocouple no."])))

    try:
        while not endDataCollect.is_set():
            for i in range(params["thermoNum"]):
                Temperature.read_data(i)
                with params["sensors"]["temperature"]["thermocouple no."][i].get_lock():
                    if params["returnFarenheit"]:
                        params["sensors"]["temperature"]["thermocouple no."][i].value = round((Temperature.get_thermocouple_temp() * (9/5)) + 32, params["significantFigures"])
                    else:
                        params["sensors"]["temperature"]["thermocouple no."][i].value = Temperature.get_thermocouple_temp()

            with params["sensors"]["temperature"]["tempAvg"].get_lock():
               params["sensors"]["temperature"]["tempAvg"].value = round(
                    np.mean([
                        params["sensors"]["temperature"]["thermocouple no."][i].value
                        for i in range(params["thermoNum"])
                    ]),
                    params["significantFigures"]
                )
    except:
        while not endDataCollect.is_set():
            for i in range(params["thermoNum"]):
                with params["sensors"]["temperature"]["thermocouple no."][i].get_lock():
                    params["sensors"]["temperature"]["thermocouple no."][i].value = -1

            with params["sensors"]["temperature"]["tempAvg"].get_lock():
                params["sensors"]["temperature"]["tempAvg"].value = round(
                    np.mean([
                        params["sensors"]["temperature"]["thermocouple no."][i].value
                        for i in range(params["thermoNum"])
                    ]),
                    params["significantFigures"]
                )    

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
    setValve = 0  # 0 Open, 127 Closed

    try:
        ds3502.wiper = setValve
        print("DS3502 is connected")
    except:
        print("DS3502 is not connected")

    errorMargin = target * DS3502Params["margin"]
    targetReached = False
    sleep(params["windUpTime"]/1000)

    while not endDataCollect.is_set():
        with params["sensors"]["temperature"]["tempAvg"].get_lock():
            tempAvg = params["sensors"]["temperature"]["tempAvg"].value
        if abs(target - tempAvg) > errorMargin or targetReached == False:
            setValve = max(0, min(127, setValve + (1 if target > tempAvg else -1)))
            if targetReached == True:
                 targetReached = False
            if abs(target - tempAvg) < errorMargin:
                 targetReached = True
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

    data = {
        "gasFlow": {"value": 0, "unit": "cu ft / sec"},
        "thermocouple no.": {"value" : [0 for _ in range(params["thermoNum"])], "unit": "F"},
        "tempAvg": {"value": 0, "unit": "F"},
        "wattage": {"value": 0, "unit": "W"},
        "CookTime": {"value": 0, "unit": "sec"},
        "totalTime": {"value": 0, "unit": "sec"},
        "gasUsage": {"value": 0, "unit": "cu ft"},
        "waterUsage": {"value": 0, "unit": "gal"},
        "waterFlow": {"value": 0, "unit": "gal / min"},
        "gasTotalUsage": {"value": 0, "unit": "cu ft"},
        "BTU": {"value": 0, "unit": "BTU"}
    }


    while not endDataCollect.is_set():
        startTime = time.time()
        with params['sensors']['power'].get_lock():
            data["wattage"]["value"] = params['sensors']['power'].value

        if len(data["thermocouple no."]["value"]) < 8:
            data["thermocouple no."]["value"].extend(["Unused"] * (8 - len(data["thermocouple no."]["value"])))

        with ExitStack() as stack:
            stack.enter_context(params["sensors"]["gas"]["tally"].get_lock())
            stack.enter_context(params["sensors"]["gas"]["flowRate"].get_lock())
            stack.enter_context(params["sensors"]["water"]["tally"].get_lock())
            stack.enter_context(params["sensors"]["water"]["flowRate"].get_lock())
            stack.enter_context(params["sensors"]["gas"]["totalTally"].get_lock())
            stack.enter_context(params["sensors"]["water"]["totalTally"].get_lock())
            stack.enter_context(params["clocks"]["cookTime"].get_lock())
            stack.enter_context(params["clocks"]["totalTime"].get_lock())

            for tc in params["sensors"]["temperature"]["thermocouple no."]:
                stack.enter_context(tc.get_lock())

            data["gasUsage"]["value"] = round(params["sensors"]["gas"]["tally"].value, params["significantFigures"])
            data["waterUsage"]["value"] = round(params["sensors"]["water"]["tally"].value, params["significantFigures"])
            data["gasFlow"]["value"] = round(params["sensors"]["gas"]["flowRate"].value, params["significantFigures"])
            data["waterFlow"]["value"] = round(params["sensors"]["water"]["flowRate"].value, params["significantFigures"])*60
            data["gasTotalUsage"]["value"] = round(params["sensors"]["gas"]["totalTally"].value, params["significantFigures"])
            data["CookTime"]["value"] = params["clocks"]["cookTime"].value
            data["totalTime"]["value"] = params["clocks"]["totalTime"].value
            data["thermocouple no."]["value"] = [tc.value for tc in params["sensors"]["temperature"]["thermocouple no."]]
            data["tempAvg"]["value"] = params["sensors"]["temperature"]["tempAvg"].value
            data["BTU"] = data["waterFlow"]["value"] * (data["thermocouple no."]["value"][0] - data["thermocouple no."]["value"][1]) * 500.4

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
        self.TargetTemperature = params["DS3502"]["TargetTemperatureDefault"]

        self.text_userDataCheck = (
            f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\npress the physical e-stop button to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.TargetTemperature}"
        )

        self.text_nameFile1label = (
            f"Welcome to the simulated ASTM F1361 test apparatus.\nPlease read the user manual prior to setting up this test.\nEnsure that the sensors are affixed to the fryer being tested.\nEnter a file name for saving the test in the first box.\nIf the file already exists, an extension (#) will be added.\nSelect the second box for a list of flow speed options.\nPick the option corresponding to the fryer you wish to test.\nPress Next or Enter to continue."
        )

        self.textwaitForTempTarget3label = "The motors should be turning on.\nIf they do not, end the test and contact the VULCAN_FRY team.\nAttempting to reach target temperature..."
        self.textMotorWindDown5Label = "The motors should be turning off.\nIf they do not, end the test and contact the VULCAN_FRY team."
        self.textSavingData8Label = "Saving Data..."
        self.textDataSave9Label = "Data Saved."

        self.textNameFile1LabelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_nameFile1label)}</span>"
        self.textUserDataCheckMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.text_userDataCheck)}</span>"
        self.textwaitForTempTarget3labelMarkup = f"<span size='x-large'>{GLib.markup_escape_text(self.textwaitForTempTarget3label)}</span>"
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

        self.nameFile1TargetTemperature = Gtk.Entry()
        self.nameFile1TargetTemperature.connect("key-press-event", self.saveFileName1)

        self.nameFile1TargetTemperaturePopover = Gtk.Popover()
        self.nameFile1TargetTemperaturePopover.set_relative_to(self.nameFile1TargetTemperature)
        self.nameFile1TargetTemperaturePopover.set_position(Gtk.PositionType.BOTTOM)

        self.nameFile1TargetTemperatureListBox = Gtk.ListBox()
        self.nameFile1TargetTemperaturePopover.add(self.nameFile1TargetTemperatureListBox)

        for optionLabel, optionValue in params["TargetTemperatureOptions"].items():
            row = Gtk.ListBoxRow()
            button = Gtk.Button(label=f"{optionLabel} ({optionValue} F)")
            button.connect("clicked", lambda btn, value=optionValue: self.setTargetTemperature(btn, value))
            row.add(button)
            self.nameFile1TargetTemperatureListBox.add(row)

        self.nameFile1TargetTemperatureListBox.show_all()

        self.nameFile1TargetTemperature.connect("focus-in-event", self.showPopover)

        self.nameFile1NextButton = Gtk.Button(label="Next")
        self.nameFile1NextButton.connect("clicked", self.saveFileName1)

        self.nameFile1.pack_start(self.nameFile1Entry, False, False, 10)
        self.nameFile1.pack_start(self.nameFile1TargetTemperature, False, False, 10)
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

        # Screen 3: Waits for target temperature to be reached.
        self.waitForTempTarget3 = Gtk.Box(spacing=10, orientation=Gtk.Orientation.VERTICAL)

        self.waitForTempTarget3label = Gtk.Label()
        self.waitForTempTarget3label.set_markup(self.textwaitForTempTarget3labelMarkup)
        self.waitForTempTarget3label.set_line_wrap(True)

        self.waitForTempTarget3Skip = Gtk.Button(label="Skip to data collection")
        self.waitForTempTarget3Skip.connect("clicked", self.startDataCollection)

        self.waitForTempTarget3Cancel = Gtk.Button(label="Cancel")
        self.waitForTempTarget3Cancel.connect("clicked", self.resetProgram)

        self.waitForTempTarget3.pack_start(self.waitForTempTarget3label, True, True, 0)
        self.waitForTempTarget3.pack_start(self.waitForTempTarget3Skip, True, True, 0)
        self.waitForTempTarget3.pack_start(self.waitForTempTarget3Cancel, True, True, 0)
        self.stack.add_named(self.waitForTempTarget3, "waitForTempTarget3")

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
    
    def saveFileName1(self, widget, event = None):

        if event == None or event.keyval == Gdk.KEY_Return:
            if self.nameFile1Entry.get_text().strip():
                self.fileName = self.nameFile1Entry.get_text()

            try:
                self.TargetTemperature = float(self.nameFile1TargetTemperature.get_text())
            except ValueError:
                None
                
            self.text_userDataCheck = (
                f"Press the button to begin the test.\nThis should start and run the motors for the duration of the test.\nIf the motors are running outside of the test,\nuse the switches in the electrical cabinet to turn them off.\nDo not attempt another test and contact the VULCAN_FRY team for assistance.\nFile Name: {self.fileName}\nTarget Flow Rate: {self.TargetTemperature}"
            )
            self.textUserDataCheckMarkup = f"<span size='large'>{GLib.markup_escape_text(self.text_userDataCheck)}</span>"

        
            self.I2C = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c = self.I2C, address = params["ADS1115"]["ADSAddress"], gain = params["ADS1115"]["ADSGain"])
            self.wattChan = AnalogIn(self.ads, ADS.P0, ADS.P1)
            print("ADS1115 is connected")
            """
            except:
                class WattChanFallback:
                    @property
                    def value(self):
                        return -1
                    def voltage(self):
                        return -1
                self.wattChan = WattChanFallback()
                print("ADS1115 is not connected")
            """
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
        self.nameFile1TargetTemperaturePopover.popup()

    def setTargetTemperature(self, widget, option):
        self.TargetTemperature = option
        self.nameFile1TargetTemperature.set_text(str(option))
        self.nameFile1TargetTemperaturePopover.popdown()

    def beginTest(self, *args):
        self.stack.set_visible_child_name("waitForTempTarget3")
        
        GPIO.output(params["motor"]["pin1"], GPIO.HIGH)
        GPIO.output(params["motor"]["pin2"], GPIO.HIGH)
        if self.testUnderWay == False:
            self.endDataCollect.clear()
            self.temperatureProcess = multiprocessing.Process(
                target=readTemperature, args=(self.endDataCollect,), daemon=True
            )

        self.endTestEvent.clear()
        
        try:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.TargetTemperature, self.endTestEvent, self.ds3502, params["DS3502"]), daemon=True
            )
        except:
            self.ControlProcess = multiprocessing.Process(
                target=flowControl, args=(self.TargetTemperature, self.endTestEvent, -1, params["DS3502"]), daemon=True
            )
        self.temperatureProcess.start()
        
        self.windUpTimeStart = time.time()
        
        def check_conditions():
            elapsed_time = time.time() - self.windUpTimeStart
            with params["sensors"]["temperature"]["tempAvg"].get_lock():
                self.tempCheck = params["sensors"]["temperature"]["tempAvg"].value
            
            if self.tempCheck >= self.TargetTemperature and elapsed_time >= (params["motor"]["windUpTime"] / 1000):
                self.startDataCollection()
                return False  # Stop calling this function
            return True  # Keep checking
    
        # Check every 200 ms (adjust if needed)
        GLib.timeout_add(200, check_conditions)


    def startDataCollection(self, *args):
        with params["sensors"]["gas"]["tally"].get_lock(), params["sensors"]["water"]["tally"].get_lock():
            params["sensors"]["gas"]["tally"].value = 0.00
            params["sensors"]["water"]["tally"].value = 0.00

        if self.testUnderWay == False:
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
            self.powerProcess = multiprocessing.Process(
                target=readPower, args=(self.wattChan, self.endDataCollect), daemon=True
            )
            self.dataProcess.start()
            self.GasProcess.start()
            self.WaterProcess.start()
            self.totalTimeProcess.start()
            self.powerProcess.start()
            self.testUnderWay = True
        
        
        self.cookTimeProcess = multiprocessing.Process(
            target=clockTracker, args=(self.endTestEvent, "cookTime"), daemon=True
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
            print("Data count:")
            print(len(self.dataList))
            if len(self.dataList) >= params["dataListMaxLength"]: 
                self.dataList.pop(0)
            dataUpdateDetailedValues = "\n".join(
                f"{key}: {self.dataList[-1][key]['value']} {self.dataList[-1][key]['unit']}"
                for key in self.dataList[-1] if key != "thermocouple no."
            )

            dataUpdateDetailedTemps = "\n".join(
                f"{params['sensors']['temperature']['thermocouple name'][i]}: {temp} {self.dataList[-1]['thermocouple no.']['unit']}"
                for i, temp in enumerate(self.dataList[-1]['thermocouple no.']['value'])
            )

            keys = ["gasUsage", "waterFlow", "BTU"]
            dataUpdateSimple = "\n".join(
                f"{key}: "
                f"{self.dataList[-1][key]['value']} "
                f"{self.dataList[-1][key]['unit']}"
                for key in keys
            )
            
            self.dataCollection4DetailedLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedValues)}</span>")
            self.dataCollection4DetailedTemperatureLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateDetailedTemps)}</span>")
            self.dataCollection4SimpleLabel.set_markup(f"<span size='x-large'>{GLib.markup_escape_text(dataUpdateSimple)}</span>")

        return True

    def endTest(self, *args):
        print("endTestRan")
        GPIO.output(params["motor"]["pin1"], GPIO.LOW)
        GPIO.output(params["motor"]["pin2"], GPIO.LOW)
        print("Relays Set")
        self.endTestEvent.set()
        print("endTestEvent set. Waiting for Control Process to join")
        self.ControlProcess.join()
        print("endTestEvent set. Waiting for cook time Process to join")
        self.cookTimeProcess.join()
        print("setting window")
        self.stack.set_visible_child_name("motorWindDown5")
        self.motor.value = 0
        print(params["motor"]["windUpTime"])
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
        self.temperatureProcess.join()
        self.powerProcess.join()
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

        initial_path = os.path.join(directory, f"{self.fileName}.csv")
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
            "Water Total Usage",
            "BTU"
        ] + [f"{params['sensors']['temperature']['thermocouple name'][i]}" for i in range(params["thermoNum"])]

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
                    entry["waterFlow"]["value"],
                    entry["BTU"]["value"]
                ] + temperatureReadings)

        self.stack.set_visible_child_name("dataSaved9")
        GLib.timeout_add(5000, self.resetProgram)

    def resetProgram(self, *args):
        self.dataList = []
        GPIO.output(params["motor"]["pin1"], GPIO.LOW)
        GPIO.output(params["motor"]["pin2"], GPIO.LOW)
        self.endDataCollect.set()
        self.temperatureProcess.join()
        self.stack.set_visible_child_name("nameFile1")
        return False

    def on_destroy(self, *args):
        GPIO.output(params["motor"]["pin1"], GPIO.LOW)
        GPIO.output(params["motor"]["pin2"], GPIO.LOW)

        self.endDataCollect.set()
        if hasattr(self, "temperatureProcess") and self.temperatureProcess.is_alive():
            self.temperatureProcess.terminate()
        if hasattr(self, "dataProcess") and self.dataProcess.is_alive():
            self.dataProcess.terminate()
        if hasattr(self, "ControlProcess") and self.ControlProcess.is_alive():
            self.ControlProcess.terminate()
        GPIO.cleanup()

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
    app.connect("destroy", app.on_destroy)  # Connect the destroy signal to the cleanup method
    app.show_all()
    Gtk.main()
    GPIO.cleanup()

if __name__ == "__main__":
    main()
