# ⚓ Harbormaster
> 别的 AI 抢着告诉你它找到了什么。Harbormaster 知道自己什么时候不该开口。

## 30 秒理解
[一张三色裁决卡片截图]

## 🎬 Demo
[60 秒 GIF：庭审 → 人工确认 → 队列缩短 → 砸场按钮]

## 为什么不一样
| 常见做法 | Harbormaster |
|---|---|
| 二态：一样/不一样 | 三态：放行/扣单/**引航** |
| LLM 直接判差异 | LLM 只读值，**确定性代码裁决** |
| 人工审核是死胡同 | 每次人工裁决 → **永久规则 + 自动回扫** |
| Demo 只演成功 | **现场砸自己的系统** |

## 快速开始
```bash
make setup && make demo
```

## 架构 / 设计决策 / 评测结果
- [架构说明](docs/architecture.md)
- [Demo 台词脚本](docs/demo_script.md)
- [字段风险依据](docs/field_risk_rationale.md)
- [ADR-001: LLM Never Judges](docs/decisions/ADR-001-llm-never-judges.md)
- [ADR-002: Three-State Verdict](docs/decisions/ADR-002-three-state-verdict.md)
- [ADR-003: OCR Confusion Guardrail](docs/decisions/ADR-003-ocr-confusion-guardrail.md)
