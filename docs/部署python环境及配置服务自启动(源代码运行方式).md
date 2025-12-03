# **1.树莓派安装依赖环境**

### 更新系统

|          命令           |    说明     |   注意项    |
|:---------------------:|:---------:|:--------:|
|   `sudo apt update`   |  更新软件包列表  |    无     |
| `sudo apt upgrade -y` | 升级已安装的软件包 | 可能需要较长时间 |

### 安装 Git、Python、pip、venv

|                             命令                             |             说明             | 注意项 |
|:----------------------------------------------------------:|:--------------------------:|:---:|
| `sudo apt install -y git python3 python3-pip python3-venv` | 安装 Git、Python3、pip3 和 venv |  无  |

---

# **2.从 GitHub 拉取项目**

### 仓库地址：

https://github.com/lztxwd666/120KWCDU.git

|                          命令                           |     说明      | 注意项 |
|:-----------------------------------------------------:|:-----------:|:---:|
|                    `cdu /homme/pi`                    | 进入 pi 用户主目录 |  无  |
| `git clone https://github.com/lztxwd666/120KWCDU.git` |   克隆项目到本地   |  无  |

克隆成功后pi目录下会出现该项目的文件夹

---

# **3.创建 Python 虚拟环境**

|             命令              |      说明      | 注意项 |
|:---------------------------:|:------------:|:---:|
|   `cd /home/pi/120KWCDU`    |   进入项目文件夹    |  无  |
|   `python3 -m venv .venv`   | 创建虚拟环境 .venv |  无  |
| `source .venv/bin/activate` |    激活虚拟环境    |  无  |

---

# **4.安装依赖**

如果有依赖文件 requirements.txt，那么直接安装(只建议创建依赖文件，使用依赖文件方式安装)

|                命令                 |  说明   | 注意项  |
|:---------------------------------:|:-----:|:----:|
| `pip install -r requirements.txt` | 安装依赖包 | 标准方式 |

如果没有，请手动安装所需依赖，例如：

|                   命令                   |    说明     |     注意项     |
|:--------------------------------------:|:---------:|:-----------:|
| `pip install pymodbus flask waitress ` | 手动安装所需依赖包 | 只建议使用依赖文件安装 |

---

# **5.手动启动程序**

|             命令             |   说明    |        注意项        |
|:--------------------------:|:-------:|:-----------------:|
|     `python3 main.py`      |  启动主程序  |         无         |
| `python3 -m cdu120kw.main` | 另一种启动方式 | 如果代码使用相对导入，则使用该方式 |

如果可以成功运行，说明环境正常

---

# **6.项目更新**

当你更新 GitHub 代码后

|                命令                 |       说明       |     注意项      |
|:---------------------------------:|:--------------:|:------------:|
|      `cd /home/pi/120KWCDU`       |    进入项目文件夹     |      无       |
|            `git pull`             | 从github上拉取最新代码 |      无       |
|    `source .venv/bin/activate`    |     激活虚拟环境     |      无       |
| `pip install -r requirements.txt` |     安装最新依赖     | 如果依赖没更新，可以省略 |

---

# **7.创建服务，让程序能够开机自启，使用源代码运行+systemd管理**

|                        命令                        |   说明   | 注意项 |
|:------------------------------------------------:|:------:|:---:|
| `sudo nano /etc/systemd/system/cdu120kw.service` | 创建服务文件 |  无  |

在打开的编辑器中，粘贴以下内容：

````ini
[Unit]
Description = CDU120KW Control Service
After = network-online.target
Wants = network-online.target

[Service]
Type = simple

WorkingDirectory = /home/raspberry/120KWCDU
Environment = "PYTHONPATH=/home/raspberry/120KWCDU"

ExecStart = /home/raspberry/120KWCDU/.venv/bin/python \
/home/raspberry/120KWCDU/cdu120kw/main.py

Restart = always
RestartSec = 5

User = root
Group = root

RuntimeDirectory = cdu120kw
RuntimeDirectoryMode = 0755

StandardOutput = journal
StandardError = journal

[Install]
WantedBy = multi-user.target
````

---

按 `CTRL+X`，然后按 `Y` 保存并退出编辑器。

！！！注意，以上配置实际应用时，= 前后不能有空格，因编辑器显示问题，这里为了美观加了空格，请自行删除！！！

---

以下为配置文件说明：

|                                                配置项                                                |                 说明                  |                           注意项                           |
|:-------------------------------------------------------------------------------------------------:|:-----------------------------------:|:-------------------------------------------------------:|
|                              `Description=CDU120KW Control Service`                               |     systemctl status 时显示的服务说明文字     |                            无                            |
|                                   `After=network-online.target`                                   |              指定该服务启动时机              |        等网络真正 "连通完成" 后再启动，避免依赖网络的程序在网络尚未准备好时启动失败         |
|                                   `Wants=network-online.target`                                   | 声明本服务“依赖并希望拉起”network-online.target |             如果该 target 未运行，systemd 会主动将其启动              |
|                                           `Type=simple`                                           |               服务启动类型                | simple 表示：systemd 在 ExecStart 命令启动后，不再等额外通知，直接认为服务已启动成功 |
|                            `WorkingDirectory=/home/raspberry/120KWCDU`                            | 设置程序运行时的默认目录：相当于 cd 到该目录再执行 Python  |                            无                            |
|                        `Environment="PYTHONPATH=/home/raspberry/120KWCDU"`                        |          设置 Python 模块搜索路径           |       强制加入项目根目录到 PYTHONPATH，让 Python 可以正确 import        |
| `ExecStart=/home/raspberry/120KWCDU/.venv/bin/python \ /home/raspberry/120KWCDU/cdu120kw/main.py` |              服务真实启动命令               |          直接调用虚拟环境中的 Python 解释器，明确指定主程序 main.py          |
|                                         `Restart=always`                                          |     进程退出或异常崩溃时，systemd 自动重新拉起服务     |                            无                            |
|                                          `RestartSec=5`                                           |         每次重启之间的延时，避免形成病毒式程序         |                            无                            |
|                                      `User=root、Group=root`                                       |               服务运行用户                |                            无                            | 
|                                    `RuntimeDirectory=cdu120kw`                                    |              指定运行时目录名称              |            systemd 会在 /run 目录下创建该目录，供服务运行时使用            |
|                                    `RuntimeDirectoryMode=0755`                                    |        设置运行时目录的权限，确保服务有读写权限         |                            无                            |
|                         `StandardOutput=journal`、`StandardError=journal`                          |      将标准输出和错误输出重定向到 systemd 日志      |                            无                            |
|                                      `StandardError=journal`                                      |      将标准输出和错误输出重定向到 systemd 日志      |                            无                            |
|                                   `WantedBy=multi-user.target`                                    |           指定服务在哪个运行级别下启动            |            multi-user.target 是常用的多用户图形界面运行级别            |

---

# **8.使用 systemd 管理服务相关指令**

|                    命令                     |         说明          | 注意项 |   
|:-----------------------------------------:|:-------------------:|:---:|
|      `sudo systemctl daemon-reexec`       | 重新加载 systemd 管理器配置  |  无  |
|      `sudo systemctl daemon-reload`       |      重新加载服务文件       |  无  |
|  `sudo systemctl start cdu120kw.service`  |        启动服务         |  无  |
| `sudo systemctl restart cdu120kw.service` |        重启服务         |  无  |
| `sudo systemctl enable cdu120kw.service`  |      设置开机自启服务       |  无  |
| `sudo systemctl status cdu120kw.service`  |       查看服务状态        |  无  |
|          `ls -ld /run/cdu120kw`           | 验证 RuntimeDirectory |  无  |
|          `ls -l /run/cdu120kw/`           |        验证锁文件        |  无  |
| `sudo journalctl -u cdu120kw.service -f`  |     实时查看服务日志输出      |  无  |
|               `sudo reboot`               |    重启树莓派，验证开机自启     |  无  | 



