"""Application-style change requests derived from documented public rules.

The targets, callers and regression expectations were written for this corpus.
They are small integrations, not extracts from the organizations' production code.
"""
from textwrap import dedent, indent


def _function(name, params, python, scalar):
    types = {"python": {"int": "int", "bool": "bool"},
             "rust": {"int": "i64", "bool": "bool"},
             "gpp": {"int": "I64", "bool": "Bool"}}
    result = {}
    for language, names in types.items():
        signature = ", ".join(f"{key}: {names[t]}" for key, t in params)
        if language == "python":
            result[language] = f"def {name}({signature}) -> int:\n" + indent(dedent(python).strip(), "    ") + "\n"
        else:
            output = "I64 !{}" if language == "gpp" else "i64"
            body = scalar.replace("var ", "let mut ") if language == "rust" else scalar
            result[language] = f"fn {name}({signature}) -> {output} {{\n" + indent(dedent(body).strip(), "    ") + "\n}\n"
    return result


def _callers(*functions):
    return {lang: "\n".join(f[lang] for f in functions) for lang in ("python", "rust", "gpp")}


def _postage():
    target = "postage_cents"
    params = [("card", "bool"), ("metered", "bool"), ("july_2024", "bool")]
    batch = "mailing_total"
    shortfall = "postage_shortfall"
    return dict(
        id="usps_retail_tariff", kind="maintenance", form="body", target=target, params=params,
        source_url="https://pe.usps.com/Archive/NHTML/DMMArchive20240714/Notice123.htm",
        provenance="Application-style mailroom fixture derived from the July 14, 2024 USPS Notice 123 retail rate table. "
                   "The date flag, mixed-mail batch and postage-due calculation are local application code.",
        description="Our mailroom stores a tariff flag with each dispatch so historical quotes can be reproduced. "
                    "For july_2024=true apply the July 14 domestic retail rates in cents: postcard 56, metered "
                    "one-ounce letter 69, stamped one-ounce letter 73. For false retain 53, 64 and 68 respectively. "
                    "A postcard's price is independent of metering. Update the shared quote used for billing and "
                    "checking postage already affixed.",
        starter=_function(target, params, """
            if card:
                return 53
            if metered:
                return 64
            return 68
        """, """
            if card { return 53; }
            if metered { return 64; }
            return 68;
        """),
        reference=_function(target, params, """
            if card:
                return 56 if july_2024 else 53
            if metered:
                return 69 if july_2024 else 64
            return 73 if july_2024 else 68
        """, """
            if card { return if july_2024 { 56 } else { 53 }; }
            if metered { return if july_2024 { 69 } else { 64 }; }
            return if july_2024 { 73 } else { 68 };
        """),
        callers=_callers(
            _function(batch, [("letters", "int"), ("cards", "int"), ("metered", "bool"), ("july_2024", "bool")], """
                return letters * postage_cents(False, metered, july_2024) + cards * postage_cents(True, metered, july_2024)
            """, """
                return letters * postage_cents(false, metered, july_2024) + cards * postage_cents(true, metered, july_2024);
            """),
            _function(shortfall, [("affixed", "int"), *params], """
                due = postage_cents(card, metered, july_2024) - affixed
                return max(0, due)
            """, """
                let due = postage_cents(card, metered, july_2024) - affixed;
                if due < 0 { return 0; }
                return due;
            """),
        ),
        public=[(target, (True, False, True), 56),
                (batch, (2, 1, True, True), 194),
                (shortfall, (68, False, False, True), 5)],
        heldout=[(target, (True, True, True), 56), (target, (False, True, True), 69),
                 (target, (False, False, True), 73), (target, (True, True, False), 53),
                 (target, (False, True, False), 64), (target, (False, False, False), 68),
                 (batch, (3, 2, False, True), 331), (batch, (3, 2, False, False), 310),
                 (batch, (0, 4, True, True), 224), (batch, (1, 0, True, False), 64),
                 (batch, (0, 0, True, True), 0), (shortfall, (60, False, True, True), 9),
                 (shortfall, (53, True, True, True), 3), (shortfall, (80, False, False, True), 0),
                 (shortfall, (53, True, False, False), 0), (shortfall, (42, False, True, False), 22)],
    )


def _storage():
    target = "transition_eligible"
    params = [("size_kb", "int"), ("archive", "bool"), ("legacy", "bool")]
    plan = "planned_volume_kb"
    audit = "lost_on_policy_update"
    return dict(
        id="s3_small_object_default", kind="maintenance", form="expr", target=target, params=params,
        source_url="https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html",
        provenance="Application-style S3 lifecycle planner reproducing the September 2024 change to the default "
                   "minimum transition size and the documented behavior of grandfathered configurations.",
        description="Update our size-eligibility helper for the September 2024 S3 Lifecycle default. Return "
                    "1 if eligible, else 0. Objects of 128 KB or more remain eligible. Smaller objects are eligible "
                    "only when legacy is true AND archive is true. Legacy means an unchanged pre-update configuration; "
                    "archive means Glacier Flexible Retrieval or Deep Archive. The fixtures use whole nonnegative KB, "
                    "otherwise eligible objects and no size-filter overrides.",
        starter=_function(target, params, "return int(size_kb >= 128 or archive)",
                          "return if size_kb >= 128 || archive { 1 } else { 0 };"),
        reference=_function(target, params, "return int(size_kb >= 128 or (archive and legacy))",
                            "return if size_kb >= 128 || (archive && legacy) { 1 } else { 0 };"),
        callers=_callers(
            _function(plan, [("objects", "int"), *params],
                      "return objects * size_kb * transition_eligible(size_kb, archive, legacy)",
                      "return objects * size_kb * transition_eligible(size_kb, archive, legacy);"),
            _function(audit, [("size_kb", "int"), ("archive", "bool")],
                      "return transition_eligible(size_kb, archive, True) - transition_eligible(size_kb, archive, False)",
                      "return transition_eligible(size_kb, archive, true) - transition_eligible(size_kb, archive, false);"),
        ),
        public=[(target, (127, True, False), 0), (plan, (3, 127, True, True), 381),
                (audit, (32, True), 1)],
        heldout=[(target, (0, True, False), 0), (target, (0, True, True), 1),
                 (target, (127, False, True), 0), (target, (128, False, False), 1),
                 (target, (128, True, True), 1), (target, (1, False, False), 0),
                 (plan, (2, 127, True, False), 0), (plan, (2, 128, True, False), 256),
                 (plan, (5, 25, True, True), 125), (plan, (5, 25, False, True), 0),
                 (plan, (0, 200, False, True), 0), (audit, (1, True), 1),
                 (audit, (127, True), 1), (audit, (128, True), 0), (audit, (12, False), 0),
                 (audit, (1024, False), 0)],
    )


def _restarts():
    target = "retry_delay"
    params = [("index", "int"), ("reduced", "bool")]
    schedule = "next_retry_at"
    wait = "cumulative_wait"
    return dict(
        id="kube_backoff_gate", kind="maintenance", form="body", target=target, params=params,
        source_url="https://v1-33.docs.kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/",
        provenance="Application-style restart scheduler and incident timeline. The two delay sequences reproduce "
                   "Kubernetes v1.33's ReduceDefaultCrashLoopBackOffDecay feature gate, with no node-level overrides.",
        description="Our incident dashboard needs Kubernetes v1.33's reduced container restart backoff. "
                    "index=0 is the first delayed retry after entering backoff and each later delay doubles. "
                    "With reduced enabled start at 1 second and cap at 60. Otherwise preserve 10 seconds initially "
                    "and the 300-second cap. index is 0..9. The same helper must power the displayed next retry "
                    "and accumulated waiting time. No overrides or backoff resets occur in these traces.",
        starter=_function(target, params, """
            seconds = 10
            for _ in range(index):
                seconds = min(300, 2 * seconds)
            return seconds
        """, """
            var seconds = 10;
            var i = 0;
            while i < index {
                seconds = seconds * 2;
                if seconds > 300 { seconds = 300; }
                i = i + 1;
            }
            return seconds;
        """),
        reference=_function(target, params, """
            seconds = 1 if reduced else 10
            cap = 60 if reduced else 300
            for _ in range(index):
                seconds = min(cap, 2 * seconds)
            return seconds
        """, """
            var seconds = if reduced { 1 } else { 10 };
            let cap = if reduced { 60 } else { 300 };
            var i = 0;
            while i < index {
                seconds = seconds * 2;
                if seconds > cap { seconds = cap; }
                i = i + 1;
            }
            return seconds;
        """),
        callers=_callers(
            _function(schedule, [("exit_time", "int"), *params],
                      "return exit_time + retry_delay(index, reduced)",
                      "return exit_time + retry_delay(index, reduced);"),
            _function(wait, [("delays", "int"), ("reduced", "bool")], """
                total = 0
                for i in range(delays):
                    total += retry_delay(i, reduced)
                return total
            """, """
                var total = 0;
                var i = 0;
                while i < delays {
                    total = total + retry_delay(i, reduced);
                    i = i + 1;
                }
                return total;
            """),
        ),
        public=[(target, (0, True), 1), (schedule, (100, 2, False), 140), (wait, (3, True), 7)],
        heldout=[(target, (1, True), 2), (target, (5, True), 32), (target, (6, True), 60),
                 (target, (9, True), 60), (target, (0, False), 10), (target, (4, False), 160),
                 (target, (5, False), 300), (schedule, (1000, 0, True), 1001),
                 (schedule, (90, 6, True), 150), (schedule, (90, 9, False), 390),
                 (schedule, (0, 4, False), 160), (wait, (0, True), 0),
                 (wait, (1, False), 10), (wait, (6, False), 610),
                 (wait, (7, True), 123), (wait, (8, True), 183)],
    )


def _lineup():
    target = "changes_available"
    params = [("used", "int"), ("windows", "int"), ("half_time", "bool"), ("five_rule", "bool")]
    approve = "change_authorized"
    listable = "bench_places"
    return dict(
        id="ifab_substitution_windows", kind="maintenance", form="body", target=target, params=params,
        source_url="https://www.theifab.com/news/the-ifab-permanently-approves-five-substitute-option-in-top-level-competitions/",
        provenance="Application-style team-sheet editor reproducing the IFAB 2022/23 optional five-substitute rule. "
                   "This fixture covers normal time only, with no concussion substitutes.",
        description="Our match desk supports competitions adopting IFAB's five-substitute option. "
                    "changes_available returns the maximum number of players a team may replace now. "
                    "Allow 5 per team when five_rule is true, retaining the old limit of 3 otherwise. "
                    "In open play, three substitution windows already used means zero more substitutions. "
                    "Half-time uses no window, so only the player cap applies then. Counts are nonnegative, "
                    "windows is 0..3, and reaching or exceeding the player cap always yields zero.",
        starter=_function(target, params, """
            if not half_time and windows >= 3:
                return 0
            return max(0, 3 - used)
        """, """
            if !half_time && windows >= 3 { return 0; }
            if used >= 3 { return 0; }
            return 3 - used;
        """),
        reference=_function(target, params, """
            if not half_time and windows >= 3:
                return 0
            limit = 5 if five_rule else 3
            return max(0, limit - used)
        """, """
            if !half_time && windows >= 3 { return 0; }
            let limit = if five_rule { 5 } else { 3 };
            if used >= limit { return 0; }
            return limit - used;
        """),
        callers=_callers(
            _function(approve, [("request", "int"), *params], """
                available = changes_available(used, windows, half_time, five_rule)
                return int(1 <= request <= available)
            """, """
                let available = changes_available(used, windows, half_time, five_rule);
                if request >= 1 && request <= available { return 1; }
                return 0;
            """),
            _function(listable, [("unused_names", "int"), *params],
                      "return min(unused_names, changes_available(used, windows, half_time, five_rule))",
                      """
                      let available = changes_available(used, windows, half_time, five_rule);
                      if unused_names < available { return unused_names; }
                      return available;
                      """),
        ),
        public=[(target, (3, 1, False, True), 2), (approve, (2, 3, 3, True, True), 1),
                (listable, (4, 1, 3, False, True), 0)],
        heldout=[(target, (0, 0, False, True), 5), (target, (3, 3, False, True), 0),
                 (target, (4, 3, True, True), 1), (target, (5, 2, True, True), 0),
                 (target, (6, 3, True, True), 0), (target, (1, 1, True, False), 2),
                 (approve, (2, 2, 2, False, True), 1), (approve, (2, 2, 2, False, False), 0),
                 (approve, (0, 1, 1, True, True), 0), (approve, (1, 0, 3, False, True), 0),
                 (approve, (2, 4, 2, False, True), 0), (listable, (3, 3, 3, True, True), 2),
                 (listable, (1, 1, 1, False, True), 1), (listable, (4, 1, 2, False, False), 2),
                 (listable, (2, 5, 2, False, True), 0), (listable, (0, 0, 0, True, True), 0)],
    )


TASKS = [_postage(), _storage(), _restarts(), _lineup()]
