def _apply_edit(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> tuple[str, str | None]:
    """搜尋 old_string 並替換為 new_string，回傳 (new_content, error)。
    仿照 Claude Code FileEditTool 設計：
    - 層 1：精確匹配
    - 層 2：quote 正規化後從原始 content 取出實際子字串，再用 preserveQuoteStyle 套用相同 quote 風格到 new_string
    - 層 3：行尾空白正規化（fallback）
    - new_string='' 時若 old_string 後緊跟換行，連帶刪除該換行
    """
    if old_string == new_string:
        return content, "old_string 與 new_string 完全相同，無需替換。"

    CURLY = {
        "‘": "'", "’": "'",   # '' → ''
        "“": '"', "”": '"',   # "" → ""
    }

    def _norm_quotes(s: str) -> str:
        for k, v in CURLY.items():
            s = s.replace(k, v)
        return s

    def _preserve_quote_style(actual_old: str, new: str) -> str:
        has_double = any(c in actual_old for c in "“”")
        has_single = any(c in actual_old for c in "‘’")
        if not has_double and not has_single:
            return new
        result = new
        if has_double:
            out, toggle = [], True
            for ch in result:
                if ch == '"':
                    out.append("“" if toggle else "”")
                    toggle = not toggle
                else:
                    out.append(ch)
            result = "".join(out)
        if has_single:
            out, toggle = [], True
            for ch in result:
                if ch == "'":
                    out.append("‘" if toggle else "’")
                    toggle = not toggle
                else:
                    out.append(ch)
            result = "".join(out)
        return result

    def _norm_ws(s: str) -> str:
        return "\n".join(line.rstrip() for line in s.splitlines())

    def _count(haystack: str, needle: str) -> int:
        n, i = 0, 0
        while (p := haystack.find(needle, i)) != -1:
            n += 1
            i = p + len(needle)
        return n

    def _do_replace(src: str, needle: str, replacement: str) -> str:
        if replacement != "":
            return src.replace(needle, replacement) if replace_all else src.replace(needle, replacement, 1)
        # 刪除模式：若 needle 不以 \n 結尾但後面緊跟 \n，連帶刪除（仿 CC applyEditToFile）
        strip_nl = not needle.endswith("\n") and (needle + "\n") in src
        target = needle + "\n" if strip_nl else needle
        return src.replace(target, replacement) if replace_all else src.replace(target, replacement, 1)

    # 層 1：精確匹配
    if old_string in content:
        actual_old = old_string
        actual_new = new_string
    else:
        # 層 2：quote 正規化——從原始 content 取出實際子字串（仿 CC findActualString）
        nq_search = _norm_quotes(old_string)
        nq_content = _norm_quotes(content)
        idx = nq_content.find(nq_search)
        if idx != -1:
            actual_old = content[idx: idx + len(old_string)]
            actual_new = _preserve_quote_style(actual_old, new_string)
        else:
            # 層 3：行尾空白正規化（fallback）
            ws_old = _norm_ws(old_string)
            ws_content = _norm_ws(content)
            if ws_old in ws_content:
                actual_old = ws_old
                actual_new = new_string
                content = ws_content
            else:
                return content, (
                    f"找不到 old_string，請確認文字完全一致（含空白與縮排）。\n"
                    f"old_string 前 50 字元：{old_string[:50]!r}"
                )

    count = _count(content, actual_old)
    if not replace_all and count > 1:
        return content, (
            f"old_string 在檔案中出現 {count} 次，無法確定替換哪一個。\n"
            f"請提供更多上下文讓 old_string 唯一，或設 replace_all=true 全部替換。"
        )

    return _do_replace(content, actual_old, actual_new), None
