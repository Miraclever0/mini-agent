"""配置示例 —— 复制成 config.py 后填上真实值。

    copy config.example.py config.py     # Windows
    cp config.example.py config.py       # macOS / Linux

config.py 已在 .gitignore 里，不会被提交。
不建 config.py 也能跑：设置环境变量 DEEPSEEK_API_KEY 即可覆盖 Key。
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
