"""
Modbus批量写入器，同时支持TCP和RTU协议
"""


class ModbusBatchWriter:
    """
    Modbus批量写入器，支持TCP和RTU协议，仅负责高效批量写入
    """

    def __init__(self, client_manager, max_retry=3):
        """
        初始化
        :param client_manager: TCP或RTU连接管理器
        :param max_retry: 失败重试次数
        """
        self.client_manager = client_manager
        self.max_retry = max_retry

    def write_registers(self, start_address: int, values: list[int], slave: int = 1):
        """
        批量写入保持寄存器
        :return: 错误信息或None
        """
        client = self.client_manager.get_client()
        if not client:
            return "ConnectionError"
        last_error = None
        for attempt in range(self.max_retry):
            try:
                result = client.write_registers(address=start_address, values=values, slave=slave)
                if result.isError():
                    continue
                return None
            except Exception as e:
                last_error = f"Error: {str(e)}"
        return last_error

    def write_coils(self, start_address: int, values: list[bool], slave: int = 1):
        """
        批量写入线圈
        :return: 错误信息或None
        """
        client = self.client_manager.get_client()
        if not client:
            return "ConnectionError"
        last_error = None
        for attempt in range(self.max_retry):
            try:
                result = client.write_coils(address=start_address, values=values, slave=slave)
                if result.isError():
                    continue
                return None
            except Exception as e:
                last_error = f"Error: {str(e)}"
        return last_error
