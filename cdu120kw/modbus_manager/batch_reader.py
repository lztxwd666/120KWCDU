"""
Modbus批量读取器，同时支持TCP和RTU协议
"""


class ModbusBatchReader:
    """
    Modbus批量读取器，支持TCP和RTU协议，仅负责高效批量读取
    """

    def __init__(self, client_manager, max_retry=3):
        """
        初始化
        :param client_manager: TCP或RTU连接管理器
        :param max_retry: 失败重试次数
        """
        self.client_manager = client_manager
        self.max_retry = max_retry

    def read_holding_registers(self, start_address: int, count: int, slave: int = 1):
        """
        批量读取保持寄存器
        :return: (数据, 错误信息)
        """
        client = self.client_manager.get_client()
        if not client:
            return None, "ConnectionError"
        last_error = None
        for attempt in range(self.max_retry):
            try:
                result = client.read_holding_registers(address=start_address, count=count, slave=slave)
                if result.isError():
                    continue
                return result.registers, None
            except Exception as e:
                last_error = f"Error: {str(e)}"
        return None, last_error

    def read_coils(self, start_address: int, count: int, slave: int = 1):
        """
        批量读取线圈
        :return: (数据, 错误信息)
        """
        client = self.client_manager.get_client()
        if not client:
            return None, "ConnectionError"
        last_error = None
        for attempt in range(self.max_retry):
            try:
                result = client.read_coils(address=start_address, count=count, slave=slave)
                if result.isError():
                    continue
                return result.bits, None
            except Exception as e:
                last_error = f"Error: {str(e)}"
        return None, last_error
