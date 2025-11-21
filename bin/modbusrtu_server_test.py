"""
最小化 Modbus RTU 服务器
只响应功能码1和3的读取请求
"""

from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.server import StartSerialServer


class ReadOnlySlaveContext(ModbusSlaveContext):

    def __init__(self):
        super().__init__()

    def getValues(self, fx, address, count=1):

        print(f"Request - FC:{fx} Addr:{address} Count:{count}")

        if fx == 1:
            return [1] * count
        elif fx == 3:
            return [4660] * count

        return [0] * count

    def setValues(self, fx, address, values):
        pass

    def validate(self, fx, address, count=1):
        """允许所有地址"""
        return True

# 启动服务器
store = ReadOnlySlaveContext()
context = ModbusServerContext(slaves=store, single=True)

StartSerialServer(
    context=context,
    port="/dev/com4",
    baudrate=115200,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=0.1
)
