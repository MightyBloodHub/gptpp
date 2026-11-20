"""Original application fixtures for four documented changes in behavior.

Examples are ordered deliberately: the public evaluator first invokes an unchanged
consumer. The implementation snippets and application-level APIs are local reproductions.
"""
from textwrap import dedent, indent


def _function(name, params, py_body, braced_body):
    code = {}
    for lang, integer, boolean in (("python", "int", "bool"), ("rust", "i64", "bool"), ("gpp", "I64", "Bool")):
        args = ", ".join(f"{p}: {integer if typ == 'int' else boolean}" for p, typ in params)
        if lang == "python":
            code[lang] = f"def {name}({args}) -> int:\n" + indent(dedent(py_body).strip(), "    ") + "\n"
        else:
            result = "i64" if lang == "rust" else "I64 !{}"
            body = braced_body.replace("var ", "let mut ") if lang == "rust" else braced_body
            code[lang] = f"fn {name}({args}) -> {result} {{\n" + indent(dedent(body).strip(), "    ") + "\n}\n"
    return code


def _callers(*functions):
    return {lang: "\n".join(f[lang] for f in functions) for lang in ("gpp", "rust", "python")}


def _git():
    name = "push_includes"
    params = [(p, "bool") for p in ("current", "has_peer", "tracks_peer", "modern", "matching")]
    count, commits = "branches_in_plan", "commits_in_plan"
    return dict(
        id="git_push_default", kind="maintenance", form="expr", target=name, params=params,
        source_url="https://github.com/git/git/blob/v2.0.0/Documentation/RelNotes/2.0.0.txt",
        provenance="Application-style push preview based on Git 2.0's change of push.default from matching to simple. "
                   "This fixture considers existing same-name destinations on the fetch remote; no refspec or branch creation.",
        description="Our preview covers pushes to the fetch remote and existing destinations only. A branch without "
                    "a same-name remote peer is excluded. Git 2.0 (modern=true) changed the default from matching "
                    "all peers to including only the current branch when it tracks that same-name peer. The explicit "
                    "matching option overrides the new default. Preserve pre-2.0 matching behavior. Return 1 if this "
                    "branch belongs in the plan, else 0.",
        starter=_function(name, params, "return int(has_peer)", "return if has_peer { 1 } else { 0 };"),
        reference=_function(name, params,
                            "return int(has_peer and (matching or not modern or (current and tracks_peer)))",
                            "return if has_peer && (matching || !modern || (current && tracks_peer)) { 1 } else { 0 };"),
        callers=_callers(
            _function(count, [("others", "int"), *params[1:]], """
                active = push_includes(True, has_peer, tracks_peer, modern, matching)
                other = push_includes(False, True, False, modern, matching)
                return active + others * other
            """, """
                let active = push_includes(true, has_peer, tracks_peer, modern, matching);
                let other = push_includes(false, true, false, modern, matching);
                return active + others * other;
            """),
            _function(commits, [("ahead", "int"), *params],
                      "return ahead * push_includes(current, has_peer, tracks_peer, modern, matching)",
                      "return ahead * push_includes(current, has_peer, tracks_peer, modern, matching);"),
        ),
        public=[(count, (3, True, True, True, False), 1),
                (commits, (5, False, True, False, True, True), 5),
                (name, (True, True, False, True, False), 0)],
        heldout=[(name, (False, True, False, True, False), 0),
                 (name, (True, True, True, True, False), 1),
                 (name, (True, False, False, True, True), 0),
                 (name, (True, True, False, False, False), 1),
                 (name, (False, True, False, False, True), 1),
                 (count, (2, True, False, True, False), 0),
                 (count, (0, True, False, True, False), 0),
                 (count, (2, False, False, False, False), 2),
                 (count, (4, True, False, True, True), 5),
                 (count, (0, True, True, True, False), 1),
                 (commits, (6, True, True, False, True, False), 0),
                 (commits, (2, False, True, False, True, False), 0),
                 (commits, (8, True, True, True, True, False), 8),
                 (commits, (9, False, False, False, False, True), 0),
                 (commits, (4, False, True, False, False, False), 4)],
    )


def _mode():
    name = "modal_category"
    params = [("count_a", "int"), ("count_b", "int"), ("first_b", "bool")]
    freq, route = "modal_frequency", "panel_route"
    return dict(
        id="mode_tie_order", kind="maintenance", form="body", target=name, params=params,
        source_url="https://docs.python.org/3.8/library/statistics.html#statistics.mode",
        provenance="An authored two-category analytics dashboard reproduces the Python 3.8 statistics.mode "
                   "tie change. The dashboard maps StatisticsError to the existing code 0.",
        description="Our dashboard counts two observed categories, A (code 1) and B (code 2). The old mode helper "
                    "returns 0 on a tie. Adopt Python 3.8 mode semantics: on a nonempty tie return the first "
                    "category observed, identified by first_b. Keep code 0 for an empty dataset and the more frequent "
                    "category for a unique mode. Counts are nonnegative integers.",
        starter=_function(name, params, """
            if count_a > count_b:
                return 1
            if count_b > count_a:
                return 2
            return 0
        """, """
            if count_a > count_b { return 1; }
            if count_b > count_a { return 2; }
            return 0;
        """),
        reference=_function(name, params, """
            if count_a > count_b:
                return 1
            if count_b > count_a:
                return 2
            if count_a == 0:
                return 0
            return 2 if first_b else 1
        """, """
            if count_a > count_b { return 1; }
            if count_b > count_a { return 2; }
            if count_a == 0 { return 0; }
            return if first_b { 2 } else { 1 };
        """),
        callers=_callers(
            _function(freq, params, """
                category = modal_category(count_a, count_b, first_b)
                if category == 1:
                    return count_a
                if category == 2:
                    return count_b
                return 0
            """, """
                let category = modal_category(count_a, count_b, first_b);
                if category == 1 { return count_a; }
                if category == 2 { return count_b; }
                return 0;
            """),
            _function(route, [*params, ("fallback", "int")], """
                category = modal_category(count_a, count_b, first_b)
                return fallback if category == 0 else category
            """, """
                let category = modal_category(count_a, count_b, first_b);
                return if category == 0 { fallback } else { category };
            """),
        ),
        public=[(route, (3, 3, True, 1), 2), (freq, (4, 2, False), 4),
                (name, (1, 1, False), 1), (route, (0, 0, False, 2), 2)],
        heldout=[(name, (0, 0, False), 0), (name, (0, 0, True), 0),
                 (name, (0, 9, True), 2), (name, (7, 1, True), 1), (name, (8, 8, True), 2),
                 (name, (11, 11, False), 1), (freq, (0, 0, True), 0), (freq, (1, 1, False), 1),
                 (freq, (12, 12, True), 12), (freq, (2, 11, False), 11),
                 (route, (8, 8, False, 2), 1), (route, (2, 2, True, 1), 2),
                 (route, (3, 3, True, 2), 2), (route, (0, 0, True, 1), 1),
                 (route, (7, 8, False, 1), 2)],
    )


def _settlement():
    name = "settlement_lag"
    params = [("weekday", "int"), ("accelerated", "bool")]
    posting, available = "settlement_day_number", "available_cash"
    return dict(
        id="equity_settlement_cycle", kind="maintenance", form="body", target=name, params=params,
        source_url="https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/new-t1-settlement-cycle-what-investors-need-know-investor-bulletin",
        provenance="An authored brokerage ledger reproduces the US transition from T+2 to T+1 on May 28, 2024. "
                   "The fixtures cover regular-way stock trades and intervals without market holidays.",
        description="Our ledger receives regular-way US equity trades. accelerated is true for trades governed "
                    "by the new May 2024 T+1 rule; earlier trades settle after two business days. Return elapsed "
                    "calendar days from trade through settlement, excluding the trade day. weekday is 0=Monday "
                    "through 4=Friday, weekends are closed, and these intervals have no market holidays.",
        starter=_function(name, params, "return 4 if weekday >= 3 else 2",
                          "return if weekday >= 3 { 4 } else { 2 };"),
        reference=_function(name, params, """
            days = 1 if accelerated else 2
            if weekday + days >= 5:
                days += 2
            return days
        """, """
            var days = if accelerated { 1 } else { 2 };
            if weekday + days >= 5 { days = days + 2; }
            return days;
        """),
        callers=_callers(
            _function(posting, [("trade_day", "int"), *params],
                      "return trade_day + settlement_lag(weekday, accelerated)",
                      "return trade_day + settlement_lag(weekday, accelerated);"),
            _function(available, [("proceeds", "int"), ("elapsed", "int"), *params], """
                return proceeds if elapsed >= settlement_lag(weekday, accelerated) else 0
            """, """
                return if elapsed >= settlement_lag(weekday, accelerated) { proceeds } else { 0 };
            """),
        ),
        public=[(available, (200, 1, 0, True), 200), (posting, (10, 3, False), 14),
                (name, (4, True), 3), (available, (80, 2, 4, True), 0)],
        heldout=[(name, (0, True), 1), (name, (1, False), 2), (name, (2, True), 1),
                 (name, (3, True), 1), (name, (4, False), 4),
                 (posting, (42, 4, True), 45), (posting, (54, 3, True), 55),
                 (posting, (0, 0, False), 2), (posting, (12, 2, False), 14),
                 (available, (500, 3, 4, True), 500), (available, (500, 3, 4, False), 0),
                 (available, (14, 1, 3, True), 14), (available, (99, 0, 3, True), 0),
                 (available, (3, 2, 0, False), 3), (available, (7, 5, 4, True), 7)],
    )


def _accessibility():
    name = "passes_size"
    params = [("width", "int"), ("height", "int"), ("aaa", "bool"), ("wcag22", "bool")]
    violations, dialog = "violations_in_group", "dialog_sizes_ok"
    return dict(
        id="wcag22_target_size", kind="maintenance", form="body", target=name, params=params,
        source_url="https://www.w3.org/TR/2023/REC-WCAG22-20231005/#target-size-minimum",
        provenance="An authored audit tool follows the new WCAG 2.2 Level AA success criterion 2.5.8 "
                   "and existing AAA criterion 2.5.5. Inputs are rectangular authored targets with no applicable exceptions.",
        description="Our pointer-target checker covers solid axis-aligned rectangles measured in integer CSS pixels; "
                    "no WCAG target-size exceptions apply. Under the new WCAG 2.2 Level AA size criterion each "
                    "dimension must reach 24. Keep the 44-by-44 minimum at AAA under either version, and keep "
                    "WCAG 2.1 AA free of a size minimum. aaa=false means Level AA. Return 1 for pass or 0 for fail.",
        starter=_function(name, params, """
            if not aaa:
                return 1
            return int(width >= 44 and height >= 44)
        """, """
            if !aaa { return 1; }
            return if width >= 44 && height >= 44 { 1 } else { 0 };
        """),
        reference=_function(name, params, """
            if not aaa and not wcag22:
                return 1
            threshold = 44 if aaa else 24
            return int(width >= threshold and height >= threshold)
        """, """
            if !aaa && !wcag22 { return 1; }
            let threshold = if aaa { 44 } else { 24 };
            return if width >= threshold && height >= threshold { 1 } else { 0 };
        """),
        callers=_callers(
            _function(violations, [("count", "int"), *params],
                      "return count * (1 - passes_size(width, height, aaa, wcag22))",
                      "return count * (1 - passes_size(width, height, aaa, wcag22));"),
            _function(dialog, [(p, "int") for p in ("save_w", "save_h", "cancel_w", "cancel_h")] + params[2:],
                      "return passes_size(save_w, save_h, aaa, wcag22) * passes_size(cancel_w, cancel_h, aaa, wcag22)",
                      "return passes_size(save_w, save_h, aaa, wcag22) * passes_size(cancel_w, cancel_h, aaa, wcag22);"),
        ),
        public=[(violations, (3, 23, 40, False, True), 3),
                (dialog, (44, 44, 43, 44, True, False), 0),
                (name, (24, 24, False, True), 1), (dialog, (24, 24, 24, 23, False, True), 0)],
        heldout=[(name, (24, 23, False, True), 0), (name, (23, 24, False, True), 0),
                 (name, (1, 1, False, False), 1), (name, (44, 44, True, True), 1),
                 (name, (43, 45, True, True), 0), (violations, (7, 25, 23, False, True), 7),
                 (violations, (7, 25, 23, False, False), 0), (violations, (7, 24, 24, False, True), 0),
                 (violations, (0, 10, 10, False, True), 0), (violations, (2, 44, 43, True, False), 2),
                 (dialog, (23, 24, 45, 45, False, True), 0),
                 (dialog, (40, 40, 24, 22, False, True), 0),
                 (dialog, (30, 24, 24, 30, False, True), 1),
                 (dialog, (1, 2, 3, 4, False, False), 1), (dialog, (80, 45, 44, 44, True, True), 1)],
    )


TASKS = [_git(), _mode(), _settlement(), _accessibility()]
