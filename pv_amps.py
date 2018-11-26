
from pyepsolartracer.client import EPsolarTracerClient
from pyepsolartracer.registers import registers,coils
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pyepsolartracer.registers import registerByName

# configure the client logging
import logging
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

serialclient = ModbusClient(method='rtu', port='/dev/ttyXRUSB0', baudrate=115200, stopbits = 1, bytesize = 8, timeout = 0.05)

client = EPsolarTracerClient(serialclient = serialclient)
client.connect()

value = client.read_input("Charging equipment input current")
print float(value)

client.close()
