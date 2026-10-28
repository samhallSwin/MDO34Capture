import pyvisa

rm = pyvisa.ResourceManager('@py')

print(rm.list_resources())

scope = rm.open_resource(
    "TCPIP::169.254.169.91::INSTR"
)

scope.timeout = 5000

print(scope.query("*IDN?"))