"""配置模板。首次运行 `python run.py` 时会自动复制成 config.py。

不需要手动复制：程序检测到没有 config.py 会自己生成，并在缺少 Key 时提示你粘贴。
config.py 已在 .gitignore 里，不会被提交。

也可以完全不建 config.py，用环境变量 DEEPSEEK_API_KEY 覆盖 Key，
其余字段直接用本文件的默认值。
"""

# ---------------------------------------------------------------- 必填

# https://platform.deepseek.com 申请。以 sk- 开头。
API_KEY = "sk-你的DeepSeekKey"


# ---------------------------------------------------------------- 可选

BASE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"      # 工具调用请用 deepseek-chat，deepseek-reasoner 不支持 tools

MAX_STEPS = 12       # 一次任务最多几轮循环，防止模型停不下来
MAX_OUTPUT = 4000    # 单次工具输出截断长度，防止一个文件把上下文撑爆
TEMPERATURE = 0      # 工具调用要的是稳定，不是文采
