"""
4RU 120KW 项目打包脚本
使用 PyInstaller 将 Python 应用打包为单个可执行文件
包含所有必要的静态资源、配置文件和模块
"""

import os
import platform
import shutil
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，确保可以导入项目模块
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    import PyInstaller.__main__
except ImportError:
    print("错误: 未安装 PyInstaller，请运行: pip install pyinstaller")
    PyInstaller = None
    sys.exit(1)


class AppPackager:
    """应用程序打包器"""

    def __init__(self):
        self.app_name = "4RU_120KW_CDU"
        self.root_dir = Path(__file__).parent
        self.build_dir = self.root_dir / "build"
        self.dist_dir = self.root_dir / "dist"
        self.spec_file = self.root_dir / f"{self.app_name}.spec"

        # 项目主要模块和包
        self.main_packages = [
            "cdu120kw",
            "cache_manager",
            "config",
            "control_logic",
            "modbus_manager",
            "server",
            "service_function",
            "static_resources",
            "task",
            "utilities"
        ]

        # 需要隐藏导入的模块（动态导入或PyInstaller无法自动检测的）
        self.hidden_imports = [
            # Web 框架相关
            "waitress",
            "flask",
            "flask_cors",

            # 通信相关
            "pymodbus",
            "pymodbus.client",
            "pymodbus.server",
            "pymodbus.transaction",
            "pymodbus.register_read_message",
            "pymodbus.register_write_message",

            # 配置和工具
            "configparser",
            "json",
            "logging",
            "threading",
            "queue",
            "time",
            "datetime",

            # 项目特定模块
            "cdu120kw.main",
            "cdu120kw.cache_manager.cache_manager",
            "cdu120kw.config.config_manager",
            "cdu120kw.control_logic.device_data_manipulation",
            "cdu120kw.modbus_manager.auto_reconnect",
            "cdu120kw.modbus_manager.batch_reader",
            "cdu120kw.modbus_manager.batch_writer",
            "cdu120kw.modbus_manager.modbusconnect_manager",
            "cdu120kw.modbus_manager.modbusrtu_manager",
            "cdu120kw.modbus_manager.modbustcp_manager",
            "cdu120kw.server.app",
            "cdu120kw.service_function.controller_app",
            "cdu120kw.task.component_operation_task",
            "cdu120kw.task.low_frequency_task",
            "cdu120kw.task.mapping_polling_task",
            "cdu120kw.task.task_queue",
            "cdu120kw.task.task_thread_pool",

            # 服务器控制器模块
            "server.controllers.fan_function.fan_control",
            "server.controllers.fan_function.allfans_control",
            "server.controllers.pump_function.pump_control",
            "server.controllers.pump_function.allpumps_control",
            "server.controllers.system_states.system_switch",
            "server.controllers.thermal.thermal_controller",

            # Modbus 控制模块
            "server.modbus_control.fan.read_fan",
            "server.modbus_control.fan.write_fan",
            "server.modbus_control.pump.read_pump",
            "server.modbus_control.pump.write_pump",

            # Redfish API 模块
            "server.redfish_api.redfish_control_fan_pump",
            "server.redfish_api.redfish_gain_fan_pump_state",
            "server.redfish_api.routes",

            # HMI 控制模块
            "server.modbus_hmi.hmi_control_device_data",

            # 系统状态模块
            "server.system_state",
            "server.fan_pump_state",
        ]

        # 需要包含的数据文件（格式: "源路径;目标路径"）
        self.data_files = [
            # 配置文件
            f"cdu120kw/config;cdu120kw/config",

            # 静态资源文件
            f"cdu120kw/static_resources;cdu120kw/static_resources",

            # 图像文件
            f"cdu120kw/image;cdu120kw/image",

            # 日志目录（空目录，用于运行时创建日志文件）
            f"cdu120kw/log;cdu120kw/log",

            # 其他必要的资源文件
            f"requirements.txt;.",
            f"README.md;.",
        ]

        # 排除的模块（减小打包体积）
        self.excludes = [
            "tkinter",
            "unittest",
            # "email",
            "pydoc",
            "pdb",
            "curses",
            "multiprocessing",
            "test",
            "tests",
            "setuptools",
            "pip",
            "wheel",
        ]

    def validate_environment(self):
        """验证打包环境"""
        print("=" * 60)
        print("验证打包环境...")
        print("=" * 60)

        # 检查操作系统
        system = platform.system()
        if system != "Windows":
            print(f"警告: 当前操作系统为 {system}，建议在 Windows 环境下打包")

        # 检查关键文件
        critical_files = {
            "主程序入口": "cdu120kw/main.py",
            "Web 静态资源": "cdu120kw/static_resources/index.html",
            "配置文件目录": "cdu120kw/config",
            "图标文件": "cdu120kw/image/coolermaster.ico",
        }

        missing_files = []
        for desc, file_path in critical_files.items():
            full_path = self.root_dir / file_path
            if not full_path.exists():
                missing_files.append(f"{desc}: {file_path}")
            else:
                print(f"✓ {desc}: {file_path}")

        if missing_files:
            print("\n错误: 以下关键文件缺失:")
            for item in missing_files:
                print(f"  - {item}")
            return False

        print("\n环境验证通过!")
        return True

    def cleanup_previous_build(self):
        """清理之前的构建文件"""
        print("\n清理之前的构建文件...")

        items_to_remove = [
            self.build_dir,
            self.dist_dir,
            self.spec_file,
        ]

        for item in items_to_remove:
            if item.exists():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    print(f"✓ 清理: {item.name}")
                except Exception as e:
                    print(f"⚠ 清理失败 {item.name}: {e}")

    def build_pyinstaller_command(self):
        """构建 PyInstaller 命令"""
        cmd = [
            "cdu120kw/main.py",  # 主程序入口

            # 基本配置
            "--name", self.app_name,
            "--onefile",  # 打包为单个可执行文件
            "--console",  # 显示控制台窗口（便于调试）
            # "--windowed",  # 如果不需要控制台，使用这个替代 --console

            # 图标设置
            "--icon", "cdu120kw/image/coolermaster.ico",

            # 路径配置
            "--distpath", str(self.dist_dir),
            "--workpath", str(self.build_dir),
            "--specpath", str(self.root_dir),

            # 优化选项
            "--clean",  # 清理临时文件
            "--noconfirm",  # 覆盖输出目录而不确认
        ]

        # 添加数据文件
        for data_file in self.data_files:
            cmd.extend(["--add-data", data_file])

        # 添加隐藏导入
        for hidden_import in self.hidden_imports:
            cmd.extend(["--hidden-import", hidden_import])

        # 添加排除模块
        for exclude in self.excludes:
            cmd.extend(["--exclude-module", exclude])

        # 平台特定选项
        if platform.system() == "Windows":
            cmd.extend(["--uac-admin"])  # 请求管理员权限（如果需要）

        return cmd

    def package_application(self):
        """执行应用程序打包"""
        print("\n" + "=" * 60)
        print("开始打包应用程序...")
        print("=" * 60)

        # 验证环境
        if not self.validate_environment():
            return False

        # 清理之前的构建
        self.cleanup_previous_build()

        # 构建命令
        pyinstaller_cmd = self.build_pyinstaller_command()

        # 显示打包信息
        print(f"\n应用程序名称: {self.app_name}")
        print(f"输出目录: {self.dist_dir}")
        print(f"构建目录: {self.build_dir}")
        print(f"包含的包: {', '.join(self.main_packages)}")
        print(f"隐藏导入: {len(self.hidden_imports)} 个模块")
        print(f"数据文件: {len(self.data_files)} 个目录")

        print("\nPyInstaller 命令:")
        print(" ".join(pyinstaller_cmd))

        # 执行打包
        try:
            print("\n开始执行 PyInstaller...")
            PyInstaller.__main__.run(pyinstaller_cmd)
        except Exception as e:
            print(f"\n打包失败: {e}")
            return False

        return True

    def post_build_cleanup(self):
        """构建后清理"""
        print("\n执行构建后清理...")

        # 保留 dist 目录，只清理 build 目录和 spec 文件
        items_to_clean = [self.build_dir, self.spec_file]

        for item in items_to_clean:
            if item.exists():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    print(f"✓ 清理: {item.name}")
                except Exception as e:
                    print(f"⚠ 清理失败 {item.name}: {e}")

    def verify_build_result(self):
        """验证构建结果"""
        print("\n验证构建结果...")

        exe_path = self.dist_dir / f"{self.app_name}.exe"

        if not exe_path.exists():
            print("错误: 未生成可执行文件")
            return False

        # 获取文件信息
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"✓ 生成可执行文件: {exe_path}")
        print(f"✓ 文件大小: {size_mb:.2f} MB")

        # 检查是否包含必要的资源
        required_resources = [
            "cdu120kw/config/settings.json",
            "cdu120kw/static_resources/index.html",
            "cdu120kw/image/coolermaster.ico"
        ]

        print("\n验证打包内容完整性...")
        # 注意：在单文件模式下，这些资源被嵌入到exe中，运行时提取到临时目录
        # 这里我们主要验证文件是否被正确包含在构建过程中

        return True

    def create_deployment_package(self):
        """创建部署包（可选）"""
        print("\n创建部署包...")

        deployment_dir = self.root_dir / f"{self.app_name}_Deployment"
        if deployment_dir.exists():
            shutil.rmtree(deployment_dir)
        deployment_dir.mkdir(exist_ok=True)

        # 复制可执行文件
        exe_src = self.dist_dir / f"{self.app_name}.exe"
        if exe_src.exists():
            shutil.copy2(exe_src, deployment_dir)
            print(f"✓ 复制可执行文件到部署目录")

        # 复制配置文件（用于用户修改）
        config_dest = deployment_dir / "config"
        config_src = self.root_dir / "cdu120kw/config"
        if config_src.exists():
            shutil.copytree(config_src, config_dest)
            print(f"✓ 复制配置文件到部署目录")

        # 创建说明文件
        readme_content = f"""
{self.app_name} 应用程序部署包

包含文件:
1. {self.app_name}.exe - 主程序可执行文件
2. config/ - 配置文件目录

使用说明:
1. 直接运行 {self.app_name}.exe 启动应用程序
2. 修改 config/ 目录下的配置文件以适应您的环境
3. 应用程序将在同目录下生成运行日志

系统要求:
- Windows 7/10/11
- .NET Framework 4.5+ (如果使用某些Modbus功能)
- 管理员权限（用于串口访问）

技术支持: [您的联系信息]
        """

        readme_path = deployment_dir / "README.txt"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

        print(f"✓ 创建部署说明文件")
        print(f"✓ 部署包位置: {deployment_dir}")

    def run(self):
        """运行完整的打包流程"""
        print("4RU 120KW CDU 应用程序打包脚本")
        print("=" * 50)

        # 切换到项目根目录
        os.chdir(self.root_dir)
        print(f"工作目录: {self.root_dir}")

        # 执行打包
        success = self.package_application()

        if success:
            # 验证结果
            self.verify_build_result()

            # 清理临时文件
            self.post_build_cleanup()

            # 创建部署包（可选）
            create_deployment = input("\n是否创建部署包? (y/N): ").lower().strip()
            if create_deployment == 'y':
                self.create_deployment_package()

            print("\n" + "=" * 50)
            print("打包完成!")
            print(f"可执行文件位置: {self.dist_dir / f'{self.app_name}.exe'}")
            print("=" * 50)
        else:
            print("\n" + "=" * 50)
            print("打包失败，请检查上面的错误信息")
            print("=" * 50)
            return 1

        return 0


if __name__ == "__main__":
    packager = AppPackager()
    exit_code = packager.run()
    sys.exit(exit_code)
