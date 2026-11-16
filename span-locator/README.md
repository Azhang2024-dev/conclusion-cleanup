# span-locator

规则不做判断：模型定位结论段、模型洗正文；规则只冻结原料、只做事后校验。

## 设计走哪条路

**直连 DeepSeek API，temperature 由调用方给。** 只有 HTTP 这条路能把 temperature 写进请求体 —— DSH 的 headless profile 不行，它的 provider 声明 `supportsTemperature: false`，参数根本不下发。所以：

| 路径 | temperature | 用途 |
|---|---|---|
| `--backend http`（默认） | 可控，写进请求体 | 全部生产与确定性测试 |
| `--backend dsh` | 不可控，服务器默认值 | 仅在拿不到 key 时兜底，结果不进正式统计 |

`run_doc.py --dry` 会把将要发出的请求体打出来（正文截断、key 不出现），先看再花钱：

```
{
 "model": "deepseek-chat",
 "temperature": 0.7,
 "max_tokens": 8000,
 "stream": false,
 "messages": [ ... ],
 "seed": 42
}
prompt_sha256=a119e1cb191141e3 chars=65876 lines=807
```

## 三个问题，一次测完

`tools/sweep.py` 同时回答：

1. **T=0 跑两次，起止行是否逐位相同** —— 模型能不能当可复算件
2. **换个温度，答案会不会动** —— 边界本身有没有歧义
3. **动的话动在哪一篇** —— 只有这些篇需要人看一眼

```bash
set DEEPSEEK_API_KEY=...
python tools/sweep.py --stage <语料根> --n 12 --temps 0 0.7 --runs 2
```

判读规则：

| 现象 | 结论 |
|---|---|
| T=0 内一致，T=0.7 也一致 | 单跑即可，不需要复核队列 |
| T=0 内一致，T=0.7 不同 | 这一篇的边界在原文里确实有歧义，进人工队列 |
| T=0 内就不一致 | 模型在这任务上不是可复算件，全部篇目跑 N 次取多数 |

## 三个文件各自的职责

| 文件 | 做什么 | 不做什么 |
|---|---|---|
| `prompt.md` | 固定 prompt：给行流，要起止行 + 洗好的正文 + 丢弃清单 | 不含任何正则、任何理由码表 |
| `tools/verify_output.py` | 闸门：行级覆盖 + 字符级残差，六类修复之外的改动一律 FAIL | 不修改模型输出、不替模型决定 |
| `tools/run_doc.py` | 单篇跑 N 次，落盘每次结果、请求指纹、token 用量、闸门结论 | 不做判断；失败写 .error.txt 不中断 |
| `tools/sweep.py` | 抽样跑多温度多轮，输出一致率表 | 不调参掩盖分歧 |

## 闸门判什么

1. **行级覆盖**：区间内每一行，要么在输出里还在，要么在 `dropped` 里申报过，要么本身是页眉页码题注这类明显杂物。三者都不满足 = 未申报删除。
2. **字符级残差**：把活下来的行拼起来，与模型输出逐字符对齐。允许的差异只有：删脚注号、删孤立字母、补破折号、破折号还原。其余任何字母变化 = 改写。

比较时忽略空白、忽略所有连字符、忽略 Word 校对标记 —— 接合劈词、删多余连字符都属合法清洗。字母本身不忽略。

## 已验证／未验证

**已测**：`verify_output.py` 四例离线测试（011be618）。

| 输入 | 结果 |
|---|---|
| 清洗正确 | PASS |
| 删 5 行但不申报 | FAIL，逐行点名 |
| 结尾截断 | FAIL，未申报删除 18 行 |
| 改一个短语（six→several） | FAIL，指出改写位置 |

**未测**：`run_doc.py` / `sweep.py` 没跑过真调用 —— 账户余额为零，`QUOTA: Insufficient Balance`。`--dry` 已确认请求体带 temperature；真跑的一致率数字手上还是空的。
