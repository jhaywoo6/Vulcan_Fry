import board
import digitalio
import adafruit_max31855

spi = board.SPI()
cs = digitalio.DigitalInOut(board.D17)  # Use your CS pin
sensor = adafruit_max31855.MAX31855(spi, cs)

print("Temperature:", sensor.temperature)
