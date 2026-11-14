"""配置加载：示例值作默认，config.py 覆盖，环境变量最高优先。

单独一个模块，是为了让工具层（tools/）能拿到 WORKROOT、MAX_OUTPUT 这类运行参数，
而不必反过来 import agent——那会形成循环依赖。
"""

import importlib.util
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.py"
EXAMPLE_PATH = HERE / "config.example.py"

# 首次配置的占位符，run.py 和 agent.main() 用它判断 Key 是否还没填
KEY_PLACEHOLDER = "你的DeepSeekKey"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load():
    """返回 (配置对象, 实际使用的文件名)。

    示例文件先当默认值，config.py 里的同名字段覆盖它——
    用户只写想改的那几行，漏掉的自动回退。
    """
    if not EXAMPLE_PATH.exists():
        raise SystemExit("找不到 config.example.py，安装不完整？")

    cfg = _load_module(EXAMPLE_PATH, "_agent_config_default")
    if CONFIG_PATH.exists():
        override = _load_module(CONFIG_PATH, "_agent_config")
        for field in dir(override):
            if field.isupper():
                setattr(cfg, field, getattr(override, field))
        return cfg, "config.py"
    return cfg, "config.example.py"


CFG, CONFIG_FILE = load()

# 环境变量优先，方便临时覆盖和 CI
API_KEY = os.getenv("DEEPSEEK_API_KEY") or CFG.API_KEY
BASE_URL = CFG.BASE_URL
MODEL = CFG.MODEL
TEMPERATURE = CFG.TEMPERATURE
MAX_STEPS = CFG.MAX_STEPS
MAX_OUTPUT = CFG.MAX_OUTPUT

# 工具只能碰这个目录以内的东西。取启动时的工作目录。
WORKROOT = Path.cwd().resolve()
