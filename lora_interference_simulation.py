import serial
import serial.tools.list_ports
import threading
import queue, time


class SerialCommunication:
    def __init__(self):
        self.serial_port = self.select_serial_port()
        self.baud_rate = 115200
        self.ser = serial.Serial(self.serial_port, self.baud_rate)
        self.recv_queue = queue.Queue()

    def get_available_ports(self):
        ports = serial.tools.list_ports.comports()
        ports_list = []
        for i in range(len(ports)):
            comport = list(ports[i])
            ports_list.append([i, comport[0], comport[1]])
        return ports_list

    def print_available_ports(self):
        ports = self.get_available_ports()
        if ports:
            print("Available ports:")
            print("%-10s %-10s %-50s" % ("num", "number", "name"))
            for port in ports:
                print("%-10s %-10s %-50s" % (port[0], port[1], port[2]))
        else:
            print("No available ports found.")

    def select_serial_port(self):
        self.print_available_ports()
        while True:
            selected_port = input("Enter the serial port (e.g., COM1) or 'exit' to quit: ")
            if selected_port.lower() == 'exit':
                exit()

            ports = self.get_available_ports()
            for port in ports:
                if str(port[0]) == selected_port:
                    print("Selected port: %s" % port[1])
                    return port[1]

            print("Invalid serial port. Please try again.")

    def crc16(self, data: bytes) -> int:
        # 初始化crc为0xFFFF
        crc = 0xFFFF
        # 循环处理每个数据字节
        for byte in data:
            # 将每个数据字节与crc进行异或操作
            crc ^= byte
            # 对crc的每一位进行处理
            for _ in range(8):
                # 如果最低位为1，则右移一位并执行异或0xA001操作(即0x8005按位颠倒后的结果)
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                # 如果最低位为0，则仅将crc右移一位
                else:
                    crc = crc >> 1
        # 返回最终的crc值
        return crc

    def receive_data(self):
        while True:
            cnt = self.ser.in_waiting
            if cnt <= 0:
                time.sleep(0.01)
                continue
            
            received_data = self.ser.read(cnt)
            if received_data[0] == 0xff:
                # print(received_data.hex())
                hex_str = ""
                recv_hex_str = received_data.hex()
                for i in range(0, len(recv_hex_str), 2):
                    hex_str += recv_hex_str[i:i+2].upper() + " "
                print("recv: [%d] %s" % (len(hex_str) / 3, hex_str))

                # crc 校验
                crc = self.crc16(received_data[0:cnt - 2]).to_bytes(2, 'little')
                if not (crc[0] == received_data[cnt - 2]
                        and crc[1] == received_data[cnt - 1]):
                    print("crc check fail")
                    break

                self.recv_queue.put(received_data)
            else:
                pass
                # print(received_data.decode())

    def get_lora_freq(self):
        self.send_byte_data("FF 03 00 D3 00 01 60 2D")
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取当前信道
                if (hex_str[2] == 0x02) and (hex_str[3] == 0x00):
                    print("get freq: %d" % hex_str[4])
                    self.freq = hex_str[4]
            except:
                print("timeout")
            break

    def set_lora_freq(self, freq):
        hex_str = hex(int(freq))[2:].zfill(2)
        data = "FF 10 00 D3 00 01 02 00 " + str(hex_str).upper() + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 扫描信道设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x00) and (hex_str[3] == 0xD3):
                    print("set freq success: %s" % freq)
                else:
                    print("set freq failed: %s" % freq)
            except:
                print("timeout")
            break

    def get_lora_netwk_id(self):
        self.send_byte_data("FF 03 00 D8 00 02 51 EE")
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取网络标识
                if (hex_str[2] == 0x04) and (hex_str[3] == 0x00):
                    self.netwk_id = hex_str[5] << 8 | hex_str[6]
                    print("get netwk_id: %d" % self.netwk_id)
            except:
                print("timeout")
            break

    def set_lora_netwk_id(self, net_id):
        hex_str = hex(int(net_id))[2:].zfill(2)
        net_id_str = str(hex_str).upper()
        data = "FF 10 00 D8 00 02 04 00 00 " + net_id_str[0:2] + " " + net_id_str[2:4] + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        # print(data)
        self.send_byte_data(data)

        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 网络标识设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x00) and (hex_str[3] == 0xD8):
                    print("set netwk_id success: %s" % net_id)
                else:
                    print("set netwk_id failed: %s" % net_id)
            except:
                print("timeout")
            break

    def get_lora_netwk_addr(self):
        self.send_byte_data("FF 03 01 2D 00 02 40 20")
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取网络地址
                if (hex_str[1] == 0x03) and (hex_str[2] == 0x04):                    
                    self.netwk_addr = hex_str[3] << 24 | hex_str[4] << 16 | hex_str[5] << 8 | hex_str[6]
                    print("get netwk_addr: %d" % self.netwk_addr)
            except:
                print("timeout")
            break

    def set_lora_netwk_addr(self, addr):
        hex_str = hex(int(addr))[2:].zfill(2)
        addr_str = str(hex_str).upper()
        data = "FF 10 EB 3C 00 04 08 A5 AD A5 AD " + addr_str[0:2] + " " + addr_str[2:4] + " " + addr_str[4:6] + " " + addr_str[6:8] + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        # print(data)

        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 网络标识设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0xEB) and (hex_str[3] == 0x3C):
                    print("set netwk_addr success: %s" % addr)
                else:
                    print("set netwk_addr failed: %s" % addr)
            except:
                print("timeout")
            break

    def get_lora_rf_speed(self):
        self.send_byte_data("FF 03 00 D4 00 01 D1 EC ")
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取无线速率
                if (hex_str[2] == 0x02) and (hex_str[3] == 0x00):
                    print("get rf speed id: %d" % hex_str[4])
                    self.rf_speed_id = hex_str[4]
            except:
                print("timeout")
            break

    def get_lora_scan_channel(self):
        self.send_byte_data("FF 03 01 CD 00 07 81 D5")
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取扫描信道
                if (hex_str[1] == 0x03) and (hex_str[2] == 0x0e):
                    print("get start scan ch: %d" % hex_str[3])
                    self.start_freq = hex_str[3]
            except:
                print("timeout")
            break

    def set_lora_scan_channel(self, ch):
        hex_str = hex(int(ch))[2:].zfill(2)
        data = "FF 10 01 CD 00 07 0E " + str(hex_str).upper() + " 00 FF FF FF FF FF FF FF FF FF FF 00 00 "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 扫描信道设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x01) and (hex_str[3] == 0xCD):
                    print("set scan ch success: %s" % ch)
                else:
                    print("set scan ch failed: %s" % ch)
            except:
                print("timeout")
            break

    def lora_interference_simulation(self, addr):
        hex_str = hex(int(addr))[2:].zfill(2)
        addr_str = str(hex_str).upper()
        data = "FF 10 01 F4 00 03 06 " + addr_str[0:2] + " " + addr_str[2:4] + " " + addr_str[4:6] + " " + addr_str[6:8] + " 00 00 "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        # print(data)
        # self.send_byte_data("FF 10 01 F4 00 03 06 C0 B9 C4 D0 00 00 40 07")
        self.send_byte_data(data)

        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 触发干扰命令
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x01):
                    print("simulation success")
                else:
                    print("simulation fail or not support")
            except:
                print("timeout")
            break
        self.send_byte_data("FF 03 02 26 00 05 70 64")

    def send_str_data(self, data):
        self.ser.write((data + "\n").encode("utf-8"))
        print(f"Sent: {data}")

    def send_byte_data(self, data):
        if len(data) == 0:
            return
        print("send: [%d] %s" % ((len(data) + 1) / 3, data))
        write_len = self.ser.write(bytearray.fromhex(data))
        # print("串口发出{}个字节".format(write_len))

    def start_serial_threads(self):
        receive_thread = threading.Thread(target=self.receive_data)
        receive_thread.daemon = True
        receive_thread.start()

    def main(self):
        self.start_serial_threads()

        try:
            while True:
                data_to_send = input("Enter data to send (or 'exit' to quit): ")
                if data_to_send.lower() == "exit":
                    break
                # self.send_byte_data(data_to_send)
                if data_to_send == '1':
                    self.get_lora_freq()
                elif data_to_send == '2':
                    self.get_lora_netwk_id()
                elif data_to_send == '3':
                    self.get_lora_rf_speed()
                elif data_to_send == '4':
                    self.get_lora_scan_channel()
                elif data_to_send == '5':
                    ch = input("Enter start ch: ")
                    self.set_lora_scan_channel(ch)
                elif data_to_send == '6':
                    addr = input("Enter dest addr: ")
                    self.lora_interference_simulation(addr)
                elif data_to_send == '7':
                    net_id = input("Enter net id: ")
                    self.set_lora_netwk_id(net_id)

        except KeyboardInterrupt:
            pass

        finally:
            self.ser.close()


if __name__ == "__main__":
    main_serial_cm = SerialCommunication()
    # serial_communication.main()
    sub_serial_cm = SerialCommunication()

    main_serial_cm.start_serial_threads()
    sub_serial_cm.start_serial_threads()

    try:
        main_serial_cm.get_lora_freq()
        main_serial_cm.get_lora_netwk_id()
        main_serial_cm.get_lora_netwk_addr()

        sub_serial_cm.set_lora_freq(main_serial_cm.freq)
        sub_serial_cm.set_lora_netwk_id(main_serial_cm.netwk_id - 1)

        while True:
            sub_serial_cm.lora_interference_simulation(main_serial_cm.netwk_addr)
            time.sleep(0.2)

    except KeyboardInterrupt:
        pass
    finally:
        main_serial_cm.ser.close()
        sub_serial_cm.ser.close()

