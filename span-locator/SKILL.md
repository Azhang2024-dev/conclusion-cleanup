---
name: span-locator
description: 用模型定位并清洗语言学论文的结论段，规则只负责冻结行流和事后校验，不参与任何取舍。
---

# span-locator

把「结论段在哪、里面哪些行该扔、脏字怎么修」整个交给模型。规则不做判断，只做两件事：
**冻结原料**（PDF → 带绝对行号的行流），**事后校验**（模型输出必须能逐字符对回原料，
每一处改动必须落在允许的修复类别里，越界即失败）。

## 为什么

规则切文本、规则洗文本这条路已经跑过一遍，499 篇里 66 篇带伤：末句被整行删、引文被当脚注删、
破折号变成字母、词间空格丢失。这些都是「删掉这一行，句子还通不通」的问题，正则看不见。
模型看得见。

## 流程

1. `tools/freeze.py` 把 PDF 冻成 `{sha}.jsonl`，每行 `{i, text, page, x0, y0, size, bold}`。**不许在这一步做任何判断。**
2. `tools/build_input.py` 把行流渲染成 `L行号 | 文本` 的输入，整篇给模型，不做窗口裁剪。
3. `prompt.md` 是固定 prompt。同一 prompt、同一 key、同一输入，重复调用。
4. 模型输出一个 JSON：起始行、结束行、清洗后的结论段全文、被它扔掉的行及理由。
5. `tools/verify_output.py` 是闸门：把输出和原料做字符级对齐，逐条判定每处改动是不是允许的修复。
   出现改写、增句、删句未申报 → FAIL，附上越界位置。
6. `tools/words.py` 用唯一合法口径（`wcengine.count.count_words`）从输出文本现算词数，不采信模型自报。

## 允许的改动（就这六类）

| 类别 | 例 | 
|---|---|
| 丢行 | 页眉、页码、题注、脚注、致谢、CRediT、作者简介、参考文献、附录标题 |
| 行末连字符接合 | `cross-\nlinguistically` → `cross-linguistically` |
| 破折号还原 | `participantsdboth` → `participants—both` |
| 词间空格补回 | `wepresented` → `we presented` |
| 脚注号删除 | `challenge that remains standing.22` → `challenge that remains standing.` |
| 噪声字符删除 | `[37_TD$DIF]`、孤立多字母 |

除这六类，一个字都不许动。动了就是 FAIL。

## 用法

```bash
python tools/freeze.py --pdf-dir PDFS --out A_lines
python tools/build_input.py --stage PATH --sha SHA1 > input.txt
python tools/run_doc.py --stage PATH --sha SHA1 --runs 3
python tools/determinism.py --stage PATH --n 40 --runs 3
```

## 已知边界

- 模型自报词数不采信，一律脚本现算。
- 泡文本的正确率取决于模型是否老实；闸门只能挡住改写，挡不住「该删的没删干净」。
  所以最终仍要人读一遍，但读的是已校验过的文本，不是从零判。
