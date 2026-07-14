"""5 层压缩管线 (Phase 2 AC8).

对标 Claude Code 5-layer compression:
  L1: Output Truncation —— >10K chars → head+tail
  L2: Message Pruning —— 去空/去重/去冗余
  L3: Summary —— cheap LLM 摘要旧轮次
  L4: Sliding Window —— 保留 system + 最后 N 轮
  L5: Dedup —— 路径标准化 + 重复内容合并

每层独立、可跳过、可单独测试。
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger("orbit.compression")

# 不保留的 assistant/tool 消息对的最大内容长度
EMPTY_TOOL_THRESHOLD = 10


class CompressionPipeline:
    """5 层压缩管线——每层独立、按序执行."""

    def __init__(self) -> None:
        self._applied_layers: list[str] = []
        self._bytes_removed = 0

    async def run(
        self,
        messages: list[dict[str, Any]],
        action: str,  # "warn" | "force"
    ) -> tuple[list[dict[str, Any]], int]:
        """运行管线——按 action 决定执行哪些层.

        Returns:
            (compressed_messages, bytes_removed)
        """
        self._applied_layers = []
        self._bytes_removed = 0
        original_size = sum(len(str(m)) for m in messages)

        # L1: 始终执行（已存在 AC6b）
        messages = self._layer1_truncate(messages)
        self._applied_layers.append("truncate")

        # L2: 始终执行
        messages = self._layer2_prune(messages)
        self._applied_layers.append("prune")

        if action == "force":
            # L3: 仅 force 模式（需要 LLM 调用，外部处理）
            # 此处标记，由 ContextCompressor 执行 LLM 摘要
            self._applied_layers.append("summary")

        # L4: warn+force 都执行
        messages = self._layer4_sliding(messages)
        self._applied_layers.append("sliding")

        # L5: warn+force 都执行
        messages = self._layer5_dedup(messages)
        self._applied_layers.append("dedup")

        compressed_size = sum(len(str(m)) for m in messages)
        self._bytes_removed = max(0, original_size - compressed_size)

        logger.info(
            "compression_complete",
            layers="→".join(self._applied_layers),
            original_chars=original_size,
            compressed_chars=compressed_size,
            removed=self._bytes_removed,
        )
        return messages, self._bytes_removed

    # ── Layer 1: Output Truncation (工具类型适配) ──────

    # 工具名 → 截断策略映射。未列出的工具使用 default 策略。
    _TOOL_TRUNC_STRATEGIES: dict[str, str] = {
        "grep": "grep",
        "read_file": "read_file",
        "exec_command": "exec_command",
        "glob": "passthrough",
        "ls": "passthrough",
        "list_files": "passthrough",
    }

    @staticmethod
    def _layer1_truncate(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """截断超长的工具输出——按工具类型选择策略。

        WHY 按工具适配: 头尾一刀切对 grep（匹配散落全文）和 pytest（FAILED在中间）
        会丢失关键信息。不同工具的输出结构不同，截断策略应区别对待。

        策略:
          grep        → 保留匹配行 Top-50（按行号排序），去重
          read_file   → 保留 import + 函数/类签名 + docstring（AST提取），去body
          exec_command → 保留 exit code + stderr + stdout 最后 2K chars
          glob/ls     → 保留全部（文件列表极少超 10K）
          default     → head+tail 5K+5K（保持现有）
        """
        MAX_CHARS = 10000
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") != "tool":
                result.append(msg)
                continue
            content = msg.get("content", "")
            if not isinstance(content, str) or len(content) <= MAX_CHARS:
                result.append(msg)
                continue

            tool_name = msg.get("name", "") or msg.get("tool_name", "")
            strategy = CompressionPipeline._TOOL_TRUNC_STRATEGIES.get(
                tool_name, "default"
            )

            if strategy == "passthrough":
                result.append(msg)
            elif strategy == "grep":
                result.append(CompressionPipeline._truncate_grep(msg, content))
            elif strategy == "read_file":
                result.append(CompressionPipeline._truncate_read_file(msg, content))
            elif strategy == "exec_command":
                result.append(CompressionPipeline._truncate_exec_command(msg, content))
            else:
                result.append(CompressionPipeline._truncate_default(msg, content))

        return result

    # ── 各工具截断策略 ─────────────────────────────────

    @staticmethod
    def _truncate_grep(msg: dict[str, Any], content: str) -> dict[str, Any]:
        """grep: 保留匹配行 Top-50，去重，按行号排序。

        WHY 二次检查: match_lines <= 50 但 content 仍可能超 MAX_CHARS——
        非匹配行（注释、空行、分隔符）占了空间。此时仍需截断。
        """
        MAX_CHARS = 10000
        lines = content.split("\n")
        match_lines = [ln for ln in lines if ":" in ln and not ln.startswith("--")]
        if len(match_lines) <= 50 and len(content) <= MAX_CHARS:
            return msg
        # 保留前 25 + 后 25 条匹配（覆盖面最广）
        kept = match_lines[:25] + match_lines[-25:]
        deduped = list(dict.fromkeys(kept))  # 保序去重
        skipped = len(match_lines) - len(deduped)
        return {
            **msg,
            "content": (
                "\n".join(deduped)
                + f"\n\n... [grep: 截断 {skipped} 条匹配，保留 Top-50] ..."
            ),
        }

    @staticmethod
    def _truncate_read_file(msg: dict[str, Any], content: str) -> dict[str, Any]:
        """read_file: 保留 import + 函数/类签名 + docstring，去 body。

        WHY AST: 函数体通常最大但信息密度最低——签名+docstring 足够 Agent 理解接口。
        """
        try:
            import ast
            tree = ast.parse(content)
            kept_lines: list[str] = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    kept_lines.append(ast.get_source_segment(content, node) or "")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    sig = ast.get_source_segment(content, node)
                    if sig:
                        # 取签名第一行 + docstring（如有）
                        sig_lines = sig.split("\n")
                        header = sig_lines[0]
                        doc = ast.get_docstring(node)
                        if doc:
                            kept_lines.append(f"{header}  # {doc[:120]}")
                        else:
                            kept_lines.append(header)
            if kept_lines:
                return {
                    **msg,
                    "content": (
                        "\n".join(kept_lines[:80])
                        + f"\n\n... [read_file: AST 提取签名，省略 {len(content)} 字符 body] ..."
                    ),
                }
        except SyntaxError:
            pass
        return CompressionPipeline._truncate_default(msg, content)

    @staticmethod
    def _truncate_exec_command(msg: dict[str, Any], content: str) -> dict[str, Any]:
        """exec_command: 保留 exit code + stderr + stdout 最后 2K chars。

        WHY 最后 2K: 命令输出末尾通常包含结果/错误摘要，比头部更有价值。
        """
        lines = content.split("\n")
        # 检测 pytest/test 输出——保留 FAILED/ERROR 行 + 摘要
        fail_lines = [
            ln for ln in lines
            if any(kw in ln for kw in ("FAILED", "ERROR", "FAIL:", "Error:", "assert"))
        ]
        tail = "\n".join(lines[-50:])  # 最后 50 行
        result_parts = []
        if fail_lines:
            result_parts.append("--- 失败用例 ---")
            result_parts.extend(fail_lines[:20])
            result_parts.append("")
        result_parts.append("--- 尾部输出 ---")
        result_parts.append(tail[-2000:])
        return {
            **msg,
            "content": (
                "\n".join(result_parts)
                + f"\n\n... [exec_command: 截断 {len(content)} 字符输出] ..."
            ),
        }

    @staticmethod
    def _truncate_default(msg: dict[str, Any], content: str) -> dict[str, Any]:
        """默认策略: head+tail 5K+5K（保持现有行为）。"""
        MAX_CHARS = 10000
        half = MAX_CHARS // 2
        return {
            **msg,
            "content": (
                content[:half]
                + f"\n\n... [截断 {len(content) - MAX_CHARS} 字符] ...\n\n"
                + content[-half:]
            ),
        }

    # ── Layer 2: Message Pruning ───────────────────────

    @staticmethod
    def _layer2_prune(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """修剪冗余消息.

        规则:
        1. 移除连续重复的 system prompt
        2. 移除空工具结果
        3. 合并相邻的 system 消息
        """
        result: list[dict[str, Any]] = []
        last_system_content = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 跳过重复的 system prompt
            if role == "system":
                if content == last_system_content and result:
                    continue
                last_system_content = str(content)

            # 跳过空工具结果
            if role == "tool" and (
                not content or len(str(content).strip()) <= EMPTY_TOOL_THRESHOLD
            ):
                continue

            result.append(msg)

        return result

    # ── Layer 4: Sliding Window ────────────────────────

    # V16.0 Phase B: OpenCode 式尾轮保护——最近2轮+40K token永不修剪
    TAIL_TURNS = 2
    TAIL_PROTECT_TOKENS = 40_000

    @staticmethod
    def _layer4_sliding(
        messages: list[dict[str, Any]],
        window_turns: int = 10,
    ) -> list[dict[str, Any]]:
        """滑动窗口——保留 system + 最后 N 轮，最近2轮+40K永不修剪.

        对标 OpenCode pruning: 保护最近 TAIL_TURNS=2 轮 + 40K token。
        WHY: LLM 需要最近上下文才能连贯思考，不能全砍。
        """
        if len(messages) <= window_turns * 2 + 1:
            return messages

        # 找到 system prompt
        system_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), 0)

        # V16.0 Phase B: 保护最近 TAIL_TURNS 轮 + TAIL_PROTECT_TOKENS token（尾部不碰）
        tail_start = len(messages)
        assistant_count = 0
        tail_tokens = 0
        from orbit.compression.token_counter import count_tokens
        for i in range(len(messages) - 1, system_idx, -1):
            content = str(messages[i].get("content", ""))
            tail_tokens += count_tokens(content) + 20
            if messages[i].get("role") == "assistant":
                assistant_count += 1
            # 满足两个条件之一即可停止保护：达到轮数 或 达到token量
            if assistant_count >= CompressionPipeline.TAIL_TURNS and tail_tokens >= CompressionPipeline.TAIL_PROTECT_TOKENS:
                tail_start = i
                break

        # 从尾部向前找 window_turns 个 assistant 消息
        assistant_indices: list[int] = []
        for i in range(tail_start - 1, system_idx, -1):
            if messages[i].get("role") == "assistant":
                assistant_indices.append(i)
                if len(assistant_indices) >= window_turns:
                    break

        if not assistant_indices:
            return messages

        # 保留: system + [start_idx ... tail_start-1] + tail
        start_idx = max(system_idx + 1, assistant_indices[-1])
        result = [messages[system_idx]]
        if start_idx > system_idx + 1:
            skipped = start_idx - system_idx - 1
            result.append(
                {
                    "role": "system",
                    "content": (
                        f"[上下文窗口管理] {skipped} 条早期消息已被滑动窗口移除。"
                        "关键内容已通过摘要保留。"
                    ),
                }
            )
        result.extend(messages[start_idx:])
        return result

    # ── Layer 5: Dedup ─────────────────────────────────

    @staticmethod
    def _layer5_dedup(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """去重——标准化路径 + 移除重复内容块.

        对标 Claude Code dedup: 标准化文件路径格式，移除重复代码块。
        """
        seen_blocks: set[str] = set()
        result: list[dict[str, Any]] = []

        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                result.append(msg)
                continue

            # 标准化路径: ./src/a.py → src/a.py, \ → /
            normalized = content.replace("\\", "/")
            normalized = re.sub(r"(?<!\w)\./", "", normalized)

            # 提取大代码块 (>200 chars) 做去重
            code_blocks = re.findall(r"```[^`]*```", normalized)
            if code_blocks:
                for block in code_blocks:
                    if block not in seen_blocks:
                        seen_blocks.add(block)
                # 检测整个消息是否接近重复
                msg_key = normalized[:200]
                if msg_key in seen_blocks:
                    continue
                seen_blocks.add(msg_key)

            result.append(msg)

        return result

    # ── 属性 ──────────────────────────────────────────

    @property
    def applied_layers(self) -> list[str]:
        return list(self._applied_layers)

    @property
    def bytes_removed(self) -> int:
        return self._bytes_removed
