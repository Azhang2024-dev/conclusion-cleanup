# tools — 六件工具

判据在 `docs/判据表.md`，阈值在 `rules.yaml`。这里只做执行。

| 工具 | 关 | 做什么 |
|---|---|---|
| `detect.py` | 1 定位 | 扫结论文本，出候选行号与理由码（不动文本） |
| `mark.py` | 2 标红 | 按候选在副本上标红，产台账 CSV；正文字符零改动 |
| `splice_check.py` | 3 拼接 | 逐处读「前一行结尾 + 后一行开头」，报断句风险 |
| `apply.py` | 4 删除 | 按台账删；保留项移到段末；每处先验证片段还在 |
| `verify.py` | 5 核验 | 格式、词数、词序子序列、窗口、查重 |
| `compare.py` | 回归 | 新候选 vs 历史台账，报 found / missed / extra |

## 用法

```bash
# 1 定位
python tools/detect.py --stage PATH --out E_reports/candidates.csv

# 2 标红（在副本上，原件不动）
python tools/mark.py --stage PATH --candidates E_reports/candidates.csv \
                     --texts DIR --out DIR_marked --ledger E_reports/marks.csv

# 3 拼接核查
python tools/splice_check.py --stage PATH --ledger E_reports/marks.csv

# 4 应用删除
python tools/apply.py --stage PATH --ledger E_reports/marks.csv \
                      --texts DIR --out DIR_clean

# 5 核验
python tools/verify.py --stage PATH --texts DIR_clean \
                       --manifest 清单.csv --out E_reports/verify.json

# 回归：与历史台账比对
python tools/compare.py --candidates E_reports/candidates.csv \
                        --reference E_reports/01_标红清单_待删位置.csv \
                        --manifest 清单.csv
```

## 依赖

Python 3.9+，`pyyaml`（读 rules.yaml）。词数一律走
`D:\conclusion-wordcount\src\wcengine\count.py::count_words`；
该路径不在时退回等价正则，并在日志里标注。

## 设计约束

- **工具之间只通过 CSV / txt 传递**，不共享内存状态。
- **每个工具都可单独重跑**，输出目录必须显式给定，不覆盖输入。
- **不删原文**：`apply.py` 只读 `--texts`，写 `--out`。
