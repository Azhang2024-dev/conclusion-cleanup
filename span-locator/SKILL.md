---
name: span-locator
description: 用模型定位并清洗语言学论文的结论段；规则只冻结行流、只做事后校验，不参与任何取舍。temperature 由调用方控制，走直连 API。
---

# span-locator

把「结论段在哪、哪些行该扔、脏字怎么修」整个交给模型。规则不做判断，只做两件事：
**冻结原料**（PDF → 带绝对行号的行流），**事后校验**（模型输出必须能逐字符对回原料，
每一处改动必须落在允许的修复类别里，越界即失败）。

## 为什么

规则切文本、规则洗文本这条路跑过一遍，499 篇里 66 篇带伤：末句被整行删、引文被当脚注删、
破折号变成字母、词间空格丢失。这些都是「删掉这一行，句子还通不通」的问题，正则看不见。

## 流程

1. `freeze`：PDF → `{sha}.jsonl`，每行 `{i, text, page, x0, y0, size, bold}`。这一步不许做任何判断。
2. `run_doc.py`：把整篇行流渲染成 `L行号 | 文本` 喂给模型，直连 API，temperature 由参数决定。
3. 模型输出 JSON：起始行、结束行、洗好的正文、被扔掉的每一行及理由。
4. `verify_output.py` 闸门：行级覆盖 + 字符级残差。未申报删除、改写、凭空增句 → FAIL。
5. 词数用唯一合法口径 `wcengine.count.count_words` 从输出文本现算，不采信模型自报。
6. `sweep.py` 抽测 T=0 重复一致率与跨温度稳定性，决定要不要多跑。

## 允许的改动（就这六类）

| 类别 | 例 |
|---|---|
| 丢行 | 页眉、页码、题注、脚注、致谢、CRediT、作者简介、参考文献、附录标题 |
| 行末连字符接合 | `cross-` + 第二行 `linguistically` → `cross-linguistically` |
| 破折号还原 | `participantsdboth` → `participants—both` |
| 词间空格补回 | `wepresented` → `we presented` |
| 脚注号删除 | `challenge that remains standing.22` → `challenge that remains standing.` |
| 噪声字符删除 | `[37_TD$DIF]`、孤立多字母 |

除这六类，一个字都不许动。动了就是 FAIL。

## 已知边界

- 模型自报词数不采信。
- 闸门挡得住改写，挡不住「该删的没删干净」；所以最终仍要人读一遍，但读的是已校验文本。
- 一致性未测：余额为零，一次真调用都没跑成。
