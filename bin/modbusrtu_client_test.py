"""
最小化 Modbus RTU 客户端
持续随机读取服务器端的线圈和寄存器
只使用功能码1和3
支持两种模式：快速连续读取和随机间隔读取
"""

import random
import time

from pymodbus.client import ModbusSerialClient


class RandomReadModbusClient:
    def __init__(self, port="COM10", baudrate=115200):
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=1
        )

    def start_reading(self, fast_mode=True):
        """开始持续读取

        Args:
            fast_mode: True为快速连续读取，False为随机间隔读取
        """
        print("Connecting to Modbus RTU server...")

        if not self.client.connect():
            print("Failed to connect to server")
            return

        print(f"Connected, starting {'FAST CONTINUOUS' if fast_mode else 'RANDOM INTERVAL'} read loop...")

        # 定义读取范围
        address_range = (0, 100)
        count_range = (1, 10)

        try:
            while True:
                function_code = random.choice([1, 3])

                address = random.randint(address_range[0], address_range[1])
                count = random.randint(count_range[0], count_range[1])

                print(f"Reading - FC:{function_code} Addr:{address} Count:{count}")

                if function_code == 1:
                    result = self.client.read_coils(
                        address=address,
                        count=count,
                        slave=1
                    )
                    if not result.isError():
                        print(f"Coils result: {result.bits}")
                    else:
                        print(f"Error reading coils: {result}")

                elif function_code == 3:
                    result = self.client.read_holding_registers(
                        address=address,
                        count=count,
                        slave=1
                    )
                    if not result.isError():
                        print(f"Registers result: {result.registers}")
                    else:
                        print(f"Error reading registers: {result}")

                print("---")

                # ========== 模式选择 ==========
                if fast_mode:
                    # 快速连续模式 - 最小延迟或直接连续读取
                    # 可以根据需要调整这个延迟，设为0则为无延迟连续读取
                    time.sleep(0.01)  # 10ms 最小延迟
                else:
                    # 随机间隔模式
                    delay = random.uniform(0.05, 0.3)
                    time.sleep(delay)

        except KeyboardInterrupt:
            print("\nStopping client...")
        finally:
            self.client.close()


if __name__ == "__main__":
    client = RandomReadModbusClient()

    # 选择读取模式：
    # True = 快速连续读取模式
    # False = 随机间隔读取模式
    USE_FAST_MODE = True  # 修改这个变量来切换模式

    client.start_reading(fast_mode=USE_FAST_MODE)
