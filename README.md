# mini-agent

一个单文件的 agent，零依赖（只用 Python 标准库），直连 DeepSeek 的
`/chat/completions` 接口。没有框架、没有多 agent、没有 RAG。

> **这是一个AI生成的README，所以AI八股味有点重，我尽量在每一个PR上做人工审查**

## 跑起来

Windows 上用启动脚本，首次运行会自动生成 `config.py` 并让你粘贴 Key：

```bash
run.cmd --mock                            # 先验证循环，不联网、不要 Key
run.cmd                                   # 真跑
run.cmd "在当前目录建个 hello.py 然后运行它"
```

在其他平台或想手动控制，用 Python 直接跑：

```bash
python agent.py --mock
python agent.py "任务"
```

`--mock` 用一个回放脚本冒充模型，不联网、不耗 token，但**真的执行工具**。
用来确认消息拼装、工具分发、终止条件这几块没问题，再去怀疑 API。

## 配置

只有 `config.py` 一个文件，`config.example.py` 是它的模板：

| 字段 | 说明 |
|---|---|
| `API_KEY` | 必填，DeepSeek 的 Key |
| `BASE_URL` / `MODEL` | 接口地址和模型，默认 `deepseek-chat` |
| `MAX_STEPS` | 循环上限，默认 12 |
| `MAX_OUTPUT` | 单次工具输出截断，默认 4000 字符 |
| `TEMPERATURE` | 默认 0 |

`config.py` 在 `.gitignore` 里，不会进仓库。手写时**只需要写想改的字段**，
漏掉的会自动回退到 `config.example.py` 里的默认值。环境变量
`DEEPSEEK_API_KEY` 优先级高于配置文件，适合临时覆盖或 CI。

## 它只有一个循环

```python
for step in range(MAX_STEPS):
    msg = chat(messages)          # 模型看着上下文决定下一步
    messages.append(msg)
    if not msg["tool_calls"]:     # 不调工具 = 说完了
        return msg["content"]
    for call in msg["tool_calls"]:  # 可能一次多个
        result = execute(...)     # 执行权在宿主这里
        messages.append({"role": "tool", ...})
```

模型每一轮只做一件事：输出「工具名 + JSON 参数」，或者给答案。
它不知道工具真的会被执行，也不知道执行结果长什么样——**那是循环喂给它的**。

## 四个工具

| 工具 | 用途 |
|---|---|
| `list_dir` | 看目录结构 |
| `read_file` | 读文件（带行号，可翻页） |
| `write_file` | 写文件 |
| `run_shell` | 执行命令（跑测试、查环境） |

只给四个是有意的：工具越多选择越乱。真要扩，先问「能不能合并进已有的四个」。

## 代码里藏着的几个边界

这些不是「最佳实践」，是这个循环不写就会出事的地方：

- **`MAX_STEPS`** —— 模型不会自己停。没有上限它会一直调下去。
- **`_clip(…, 4000)`** —— 一次 `cat` 一个大文件就能把上下文撑爆、请求直接超时报错。
- **`_resolve()`** —— 工具只允许碰工作目录以内。模型输出的路径是**用户数据**，
  不是命令；`../../` 这种必须在这里拦。
- **`execute()` 里的 `except`** —— 工具报错不崩程序，把错误文本回传给模型，
  它下一轮通常会自己改。用报错纠正行为比用提示词纠正可靠得多。
- **`required` 字段 + 参数说明** —— 描述是给模型看的接口文档，
  它决定模型填不填得对。
- **`temperature: 0`** —— 工具调用场景要的是稳定，不是文采。

## 下一步可以往里加什么

按性价比排序，一次只加一样，每加一样都重跑 `--mock`：

1. **阶段化工具集**：探索阶段只给前两个工具，编辑阶段只给后两个。
   改 `run()` 里传给 `chat()` 的 `tools` 即可。
2. **`tool_choice` 钉死关键步骤**：某个工具必须调用时，
   在 payload 里加 `"tool_choice": {"type": "function", "function": {"name": "read_file"}}`。
3. **写前必读的硬校验**：在 `write_file` 里记录哪些文件读过，
   没读过就返回错误。这是宿主裁决，不是提示词。
4. **上下文压缩**：步数多了以后，把早期的工具输出换成摘要。
5. 到这里再考虑第二个 agent——而且要拿「独立可并行 / 需要隔离权限 /
   有明确输入输出契约」这三条去卡，不是任务多就拆。

## 关于提交署名

这个仓库的提交有两个作者：

| 作者 | 来源 |
|---|---|
| `Miraclever0` | 手写的部分 |
| `FatBlueFish-DS` | AI agent 生成的部分 |

分开署名不是为了装成两个人，是为了让「这段代码是谁写的」可追溯。
看历史时，署名是 `FatBlueFish-DS` 的提交，说明改动出自某次对话，
排查问题该去翻当时的对话记录，而不是翻自己的记忆。

