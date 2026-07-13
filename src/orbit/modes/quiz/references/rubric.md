# 测验出题规范 (rubric.md)

## 出题原则

1. **每题验证一个关键理解点**——不考细节（文件行号/变量名），考 WHY（为什么改/影响什么）
2. **正选+反选混合**——至少 2 道正选题（True），至少 2 道反选题（False）
3. **反选题用常见误解**——"这个改动修复了 X 性能瓶颈"（实际修复的是 Y）→ False
4. **归因题优先**——"X 改动的目的是 Y"（最有效的理解验证）
5. **每题必须给出解释**——不只说对错，说清为什么

## 题目格式

```json
{
  "id": 1,
  "statement": "新增的 deviation_log 字段会导致 checkpoint 写入时额外查询一次 PG",
  "answer": false,
  "explanation": "deviation_log 是 CheckpointData 的 JSON 字段，序列化在同一个 orjson.dumps() 调用中。不增加额外查询。",
  "source_files": ["checkpoint/manager.py"],
  "category": "归因"  // 正选 | 反选 | 归因
}
```

## 质量红线

- 答案不能从 diff 中直接找到（那叫视力测试，不是理解测试）
- 解释必须引用具体代码路径（"见 X 函数 Y 行"）
- 5 道题必须覆盖本次改动的至少 3 个不同文件
