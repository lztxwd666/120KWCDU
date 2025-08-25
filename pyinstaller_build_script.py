# 打包脚本：使用 PyInstaller 打包 Python 应用为单个.exe文件，并包含所有静态资源

import os
import shutil

import PyInstaller.__main__


def package_app():
    app_name = "redfish_v1.1"
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)

    print(f"当前目录: {root_dir}")

    # 清理旧文件
    for item in ['build', 'dist', f'{app_name}.spec']:
        if os.path.exists(item):
            shutil.rmtree(item) if os.path.isdir(item) else os.remove(item)
            print(f"清理: {item}")

    # 检查关键文件
    required_files = {
        '主程序': 'main.py',
        '配置文件': 'config/config.ini',
        '网页资源': 'static_resources/index.html',
    }
    missing = [f"{name} ({path})" for name, path in required_files.items() if not os.path.exists(path)]
    if missing:
        print("缺失以下关键文件：")
        for item in missing:
            print(f"  - {item}")
        return

    pyinstaller_cmd = [
        'main.py',
        '--name', app_name,
        '--onefile',
        '--add-data', f'config{os.pathsep}config',
        '--add-data', f'static_resources{os.pathsep}static_resources',
        '--add-data', f'cache_manager{os.pathsep}cache_manager',
        '--add-data', f'modbustcp_manager{os.pathsep}modbustcp_manager',
        '--add-data', f'server{os.pathsep}server',
        '--add-data', f'utilities{os.pathsep}utilities',
        '--clean',
        '--noconfirm',
        '--distpath', '.',
        '--workpath', 'build',
        '--hidden-import', 'waitress',
        '--hidden-import', 'pymodbus',
        '--hidden-import', 'configparser',
        '--hidden-import', 'server.controllers.routes',
        '--hidden-import', 'server.controllers.web_routes',
        '--hidden-import', 'server.controllers.chassis.chassis_controller',
        '--hidden-import', 'server.controllers.fan_controllers.fan_control',
        '--hidden-import', 'server.controllers.pump_conrollers.pump_control',
        '--hidden-import', 'server.controllers.thermal.thermal_controller',
        '--hidden-import', 'server.controllers.temp_states.temperature_state',
        '--hidden-import', 'server.modbus_control.fan.read_fan',
        '--hidden-import', 'server.modbus_control.fan.write_fan',
        '--hidden-import', 'server.modbus_control.pump.read_pump',
        '--hidden-import', 'server.modbus_control.pump.write_pump',
        '--hidden-import', 'server.modbus_control.system_state.read_pressure',
        '--hidden-import', 'server.modbus_control.system_state.read_temperature',
        '--hidden-import', 'server.modbus_control.system_state.read_flow',
        '--hidden-import', 'server.controllers.keep_connect.keep_connect_controller',
    ]

    print("开始打包:")
    print(" ".join(pyinstaller_cmd))

    try:
        PyInstaller.__main__.run(pyinstaller_cmd)
    except Exception as e:
        print(f"\n打包失败: {e}")
        return

    print("\n 清理构建缓存...")
    for item in ['build', f'{app_name}.spec']:
        if os.path.exists(item):
            shutil.rmtree(item) if os.path.isdir(item) else os.remove(item)
            print(f"删除: {item}")

    exe_path = os.path.join(root_dir, f"{app_name}.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"\n打包完成: {exe_path}")
        print(f"文件大小: {size_mb:.2f} MB")
    else:
        print("\n未生成可执行文件")


if __name__ == "__main__":
    package_app()

# 打包脚本：使用 PyInstaller 打包 Python 应用为：.exe + /static_resources

# import os
# import shutil
#
# import PyInstaller.__main__
#
#
# def package_app():
#     app_name = "redfish_v1.1"
#     root_dir = os.path.dirname(os.path.abspath(__file__))
#     output_dir = os.path.join(root_dir, "program")
#
#     # 清理旧文件
#     print(f"📁 项目根目录: {root_dir}")
#     print(f"📁 输出目录: {output_dir}")
#
#     # 清理输出目录
#     if os.path.exists(output_dir):
#         shutil.rmtree(output_dir)
#         print(f"🧹 清理输出目录: {output_dir}")
#
#     # 创建输出目录
#     os.makedirs(output_dir, exist_ok=True)
#
#     # 检查关键文件
#     required_files = {
#         '主程序': 'main.py',
#         '图标': 'coolermaster.ico',
#         '配置文件': 'config/config.ini',
#         '字体': 'font/LXGWWenKai-Regular.ttf',
#         '网页资源': 'static_resources/index.html',
#     }
#
#     missing = [f"{name} ({path})" for name, path in required_files.items() if not os.path.exists(path)]
#     if missing:
#         print("❌ 缺失以下关键文件：")
#         for item in missing:
#             print(f"  - {item}")
#         return
#
#     # PyInstaller 打包命令 - 将所有资源打包进 EXE
#     pyinstaller_cmd = [
#         'main.py',
#         '--name', app_name,
#         '--onefile',  # 单文件模式
#         '--windowed',
#         '--icon', 'coolermaster.ico',
#         '--add-data', f'coolermaster.ico{os.pathsep}.',
#         '--clean',
#         '--noconfirm',
#         '--distpath', output_dir,  # EXE 直接b输出到 program 目录
#         '--workpath', os.path.join(root_dir, 'uild'),  # 临时文件在项目根目录
#         '--add-data', f'config{os.pathsep}config',
#         '--add-data', f'font{os.pathsep}font',
#         '--add-data', f'cache_manager{os.pathsep}cache_manager',
#         '--add-data', f'modbustcp_manager{os.pathsep}modbustcp_manager',
#         '--add-data', f'redfish_ui{os.pathsep}redfish_ui',
#         '--add-data', f'server{os.pathsep}server',
#         '--add-data', f'utilities{os.pathsep}utilities',
#
#         '--hidden-import', 'waitress',
#         '--hidden-import', 'pymodbus',
#         '--hidden-import', 'PyQt5.sip',
#         '--hidden-import', 'configparser',
#         '--hidden-import', 'server.controllers.routes',
#         '--hidden-import', 'server.controllers.web_routes',
#         '--hidden-import', 'server.controllers.chassis.chassis_controller',
#         '--hidden-import', 'server.controllers.fan_controllers.fan_control',
#         '--hidden-import', 'server.controllers.pump_conrollers.pump_control',
#         '--hidden-import', 'server.controllers.thermal.thermal_controller',
#         '--hidden-import', 'server.controllers.temp_states.temperature_state',
#         '--hidden-import', 'server.modbus_control.fan.read_fan',
#         '--hidden-import', 'server.modbus_control.fan.write_fan',
#         '--hidden-import', 'server.modbus_control.pump.read_pump',
#         '--hidden-import', 'server.modbus_control.pump.write_pump',
#         '--hidden-import', 'server.modbus_control.system_state.read_pressure',
#         '--hidden-import', 'server.modbus_control.system_state.read_temperature',
#         '--hidden-import', 'server.modbus_control.system_state.read_flow',
#         '--hidden-import', 'server.controllers.keep_connect.keep_connect_controller',
#     ]
#
#     print("🚀 开始打包:")
#     print(" ".join(pyinstaller_cmd))
#
#     try:
#         PyInstaller.__main__.run(pyinstaller_cmd)
#     except Exception as e:
#         print(f"\n❌ 打包失败: {e}")
#         return
#
#     # 复制静态资源到输出目录
#     static_src = os.path.join(root_dir, 'static_resources')
#     static_dest = os.path.join(output_dir, 'static_resources')
#
#     if os.path.exists(static_src):
#         print(f"\n📂 复制静态资源文件夹: static_resources")
#         if os.path.exists(static_dest):
#             shutil.rmtree(static_dest)
#         shutil.copytree(static_src, static_dest)
#     else:
#         print("\n⚠️ 警告: static_resources 文件夹不存在")
#
#     # 清理构建缓存
#     print("\n🧼 清理构建缓存...")
#     build_dir = os.path.join(root_dir, 'build')
#     spec_file = os.path.join(root_dir, f'{app_name}.spec')
#
#     for item in [build_dir, spec_file]:
#         if os.path.exists(item):
#             if os.path.isdir(item):
#                 shutil.rmtree(item)
#             else:
#                 os.remove(item)
#             print(f"  ✅ 删除: {item}")
#
#     # 最终输出信息
#     exe_path = os.path.join(output_dir, f"{app_name}.exe")
#     if os.path.exists(exe_path):
#         size_mb = os.path.getsize(exe_path) / 1024 / 1024
#         print(f"\n✅ 打包完成! 输出目录: {output_dir}")
#         print(f"📦 可执行文件: {exe_path}")
#         print(f"📦 文件大小: {size_mb:.2f} MB")
#
#         # 检查输出目录内容
#         output_items = os.listdir(output_dir)
#         print("\n📁 输出目录内容:")
#         for item in output_items:
#             item_path = os.path.join(output_dir, item)
#             if os.path.isdir(item_path):
#                 print(f"  📂 {item}/")
#             else:
#                 print(f"  📄 {item}")
#
#         # 添加运行说明
#         print("\n🚀 运行说明:")
#         print(f"1. 转到目录: {output_dir}")
#         print(f"2. 运行: {app_name}.exe")
#         print(f"3. 静态资源位置: {static_dest}")
#     else:
#         print("\n❌ 未生成可执行文件")
#
#
# if __name__ == "__main__":
#     package_app()
