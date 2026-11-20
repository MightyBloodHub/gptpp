"""Standards-derived maintenance tasks for four small scalar application modules."""

from datetime import date, timedelta
from textwrap import dedent, indent


def _function(name, params, python, braced):
    """The scalar bodies below use the same braced syntax in Rust and GPT++."""
    bodies = {}
    for lang, integer, boolean in (("python", "int", "bool"), ("rust", "i64", "bool"), ("gpp", "I64", "Bool")):
        args = ", ".join(f"{n}: {integer if ty == 'int' else boolean}" for n, ty in params)
        if lang == "python":
            header = f"def {name}({args}) -> int:"
            bodies[lang] = header + "\n" + indent(dedent(python).strip(), "    ") + "\n"
        else:
            effects = " !{}" if lang == "gpp" else ""
            header = f"fn {name}({args}) -> {integer}{effects} {{"
            bodies[lang] = header + "\n" + indent(dedent(braced).strip(), "    ") + "\n}\n"
    return bodies


def _callers(*functions):
    return {lang: "\n".join(fn[lang] for fn in functions) for lang in ("python", "rust", "gpp")}


def _cases(oracle, examples, hidden):
    for entry, args, expected in examples:
        assert oracle(entry, args) == expected, (entry, args, expected)
    seen = {(entry, args) for entry, args, _ in examples}
    assert len(seen) == len(examples) and len(set(hidden)) == len(hidden) and seen.isdisjoint(hidden)
    return dict(public=examples, heldout=[(name, args, oracle(name, args)) for name, args in hidden])


def _calendar():
    name = "iso_weekday"
    params = [("day_offset", "int")]
    grid = params + [("sunday_first", "bool")]
    starter = _function(name, params,
        "return 0 if day_offset < 0 else (day_offset + 3) % 7 + 1",
        "return if day_offset < 0 { 0 } else { (day_offset + 3) % 7 + 1 };")
    reference = _function(name, params,
        "return (day_offset + 3) % 7 + 1",
        "return ((day_offset + 3) % 7 + 7) % 7 + 1;")
    column = _function("grid_column", grid, """
        weekday = iso_weekday(day_offset)
        return weekday % 7 if sunday_first else weekday - 1
    """, """
        let weekday = iso_weekday(day_offset);
        return if sunday_first { weekday % 7 } else { weekday - 1 };
    """)
    badge = _function("weekend_badge", params, "return 1 if iso_weekday(day_offset) >= 6 else 0",
                      "return if iso_weekday(day_offset) >= 6 { 1 } else { 0 };")
    heading = _function("week_start", grid, "return day_offset - grid_column(day_offset, sunday_first)",
                        "return day_offset - grid_column(day_offset, sunday_first);")

    def oracle(entry, args):
        # Calendar arithmetic comes from the standard library. Search backward
        # from the actual date for the viewer's heading instead of using grid_column.
        epoch = date(1970, 1, 1)
        current = epoch + timedelta(days=args[0])
        if entry == name:
            return current.isoweekday()
        if entry == "weekend_badge":
            return int(current.weekday() in (5, 6))
        start = current
        while start.weekday() != (6 if args[1] else 0):
            start -= timedelta(days=1)
        if entry == "week_start":
            return (start - epoch).days
        assert entry == "grid_column"
        return (current - start).days

    examples = [(name, (-4,), 7), ("grid_column", (0, False), 3),
                ("weekend_badge", (-5,), 1), ("week_start", (-1, True), -4)]
    hidden = [(name, (d,)) for d in (-365000, -11, -7, -3, -1, 0, 3, 365000)]
    hidden += [("grid_column", (-4, True)), ("grid_column", (-4, False)), ("grid_column", (4, False)),
               ("weekend_badge", (-8,)), ("weekend_badge", (2,)), ("week_start", (-4, False)),
               ("week_start", (-365000, True)), ("week_start", (4, True))]
    return dict(id="archive_calendar", kind="maintenance", form="expr", target=name, params=params,
                description="The archive calendar is importing dates before 1970. Replace the legacy weekday "
                "value 0 for negative day offsets with the correct ISO weekday. Offsets are whole UTC days "
                "from Thursday 1970-01-01, between -365000 and 365000 inclusive. Monday is 1 and Sunday "
                "is 7. Preserve all on-or-after-epoch behavior, weekend badges and both week-start layouts.",
                source_url="https://docs.python.org/3/library/datetime.html#datetime.date.isoweekday",
                provenance="The ISO weekday numbering follows Python's documented date.isoweekday contract. "
                "The archival import, epoch-offset interface and layout callers are authored scenarios.",
                starter=starter, reference=reference, callers=_callers(column, badge, heading),
                **_cases(oracle, examples, hidden))


def _wave():
    name = "pcm_byte"
    params = [("sample", "int")]
    pair = [("left", "int"), ("right", "int")]
    clip_py = "if sample < -32768:\n    return 0\nif sample > 32767:\n    return 255\n"
    clip_braces = "if sample < -32768 { return 0; }\nif sample > 32767 { return 255; }\n"
    starter = _function(name, params, clip_py + "return 128 - ((-sample) // 256) if sample < 0 else 128 + sample // 256",
                        clip_braces + "return sample / 256 + 128;")
    reference = _function(name, params, clip_py + "return (sample + 32768) // 256",
                          clip_braces + "return (sample + 32768) / 256;")
    stereo = _function("stereo_word", pair, "return pcm_byte(left) + 256 * pcm_byte(right)",
                       "return pcm_byte(left) + 256 * pcm_byte(right);")
    meter = _function("meter_distance", params, "return abs(pcm_byte(sample) - 128)", """
        let delta = pcm_byte(sample) - 128;
        return if delta < 0 { -delta } else { delta };
    """)
    mono = _function("mono_preview", params, "return stereo_word(sample, sample)",
                     "return stereo_word(sample, sample);")

    def oracle(entry, args):
        # Read the most significant byte of a signed little-endian PCM sample
        # and flip its sign bit. Construct caller expectations as binary frames.
        def octet(value):
            clipped = max(-32768, min(32767, value))
            return clipped.to_bytes(2, "little", signed=True)[1] ^ 128
        if entry == name:
            return octet(args[0])
        if entry == "meter_distance":
            return abs(octet(args[0]) - 128)
        if entry == "mono_preview":
            frame = bytes([octet(args[0])]) * 2
        else:
            assert entry == "stereo_word"
            frame = bytes(octet(x) for x in args)
        return int.from_bytes(frame, "little")

    examples = [(name, (-1,), 127), ("stereo_word", (-32768, 32767), 65280),
                ("meter_distance", (-257,), 2), ("mono_preview", (0,), 32896)]
    hidden = [(name, (v,)) for v in (-131072, -32769, -32768, -32767, -256, -255, 0, 255, 256, 32768)]
    hidden += [("stereo_word", (-257, -1)), ("stereo_word", (131071, -131072)),
               ("meter_distance", (-1,)), ("meter_distance", (32767,)),
               ("mono_preview", (-32767,)), ("mono_preview", (131071,))]
    return dict(id="wave_preview", kind="maintenance", form="body", target=name, params=params,
                description="Correct quantization in the audio preview exporter. The mixer provides integer "
                "sample values in [-131072,131071]. Clip to the signed 16-bit range, bias by 32768, then "
                "discard the low eight bits to obtain unsigned 8-bit PCM. The old exporter rounds small "
                "negative samples toward silence. Keep existing saturation, positive buckets, stereo channel "
                "order, meter distance from byte 128, and duplicated mono preview.",
                source_url="https://learn.microsoft.com/en-us/windows/win32/multimedia/devices-and-data-types",
                provenance="Microsoft documents signed 16-bit PCM and unsigned 8-bit PCM including their "
                "midpoints. Truncating the biased value to its high byte is this exporter's quantizer policy.",
                starter=starter, reference=reference, callers=_callers(stereo, meter, mono),
                **_cases(oracle, examples, hidden))


def _dns():
    name = "serial_order"
    params = [("current", "int"), ("candidate", "int")]
    manual = params + [("operator_approved", "bool")]
    capacity = manual + [("zone_octets", "int")]
    starter = _function(name, params, """
        if candidate == current:
            return 0
        return 1 if candidate > current else -1
    """, """
        if candidate == current { return 0; }
        return if candidate > current { 1 } else { -1 };
    """)
    reference = _function(name, params, """
        delta = (candidate - current) % 4294967296
        if delta == 0:
            return 0
        if delta == 2147483648:
            return 2
        return 1 if delta < 2147483648 else -1
    """, """
        let delta = (candidate + 4294967296 - current) % 4294967296;
        if delta == 0 { return 0; }
        if delta == 2147483648 { return 2; }
        return if delta < 2147483648 { 1 } else { -1 };
    """)
    transfer = _function("should_transfer", manual, """
        order = serial_order(current, candidate)
        return 1 if order == 1 or (order == 2 and operator_approved) else 0
    """, """
        let order = serial_order(current, candidate);
        return if order == 1 || (order == 2 && operator_approved) { 1 } else { 0 };
    """)
    flag = _function("review_flag", params, "return 1 if serial_order(current, candidate) == 2 else 0",
                     "return if serial_order(current, candidate) == 2 { 1 } else { 0 };")
    budget = _function("planned_octets", capacity, """
        return zone_octets * should_transfer(current, candidate, operator_approved)
    """, "return zone_octets * should_transfer(current, candidate, operator_approved);")

    def oracle(entry, args):
        # Compare lengths of clockwise and anticlockwise trips on the ring.
        # Equal nonzero lengths have no order, regardless of argument order.
        old, new = args[:2]
        direct = abs(new - old)
        opposite = 2**32 - direct
        if direct == 0:
            relation = 0
        elif direct == opposite:
            relation = 2
        else:
            relation = 1 if (new > old) == (direct < opposite) else -1
        if entry == name:
            return relation
        if entry == "review_flag":
            return int(direct == opposite)
        transfer_ok = (relation == 1) or (relation == 2 and args[2])
        if entry == "should_transfer":
            return int(transfer_ok)
        assert entry == "planned_octets"
        return args[3] if transfer_ok else 0

    top, half = 2**32 - 1, 2**31
    examples = [(name, (top, 0), 1), ("review_flag", (0, half), 1),
                ("should_transfer", (8, 7, True), 0), ("planned_octets", (9, 10, False, 600), 600)]
    hidden = [(name, (a, b)) for a, b in ((0, 0), (17, 19), (19, 17), (0, top), (half, 0),
                                           (0, half - 1), (0, half + 1), (top, half - 1))]
    hidden += [("review_flag", (11, half + 11)), ("review_flag", (top, 0)),
               ("should_transfer", (half + 1, 1, False)), ("should_transfer", (half + 1, 1, True)),
               ("planned_octets", (top - 1, 2, False, 700)), ("planned_octets", (2, top - 1, True, 400)),
               ("planned_octets", (4, half + 4, False, 900)), ("planned_octets", (4, half + 4, True, 900))]
    return dict(id="dns_zone_serial", kind="maintenance", form="body", target=name, params=params,
                description="The DNS secondary compares SOA serials numerically and drops an update across "
                "32-bit rollover. Implement RFC 1982 serial ordering. Both serials are in [0,4294967295]. "
                "Return 0 for equal, 1 when the candidate is strictly less than half a ring forward, -1 "
                "when it is strictly less than half a ring backward, and local status 2 at exactly half "
                "a ring. Retain the callers' policy: an ambiguous transfer requires operator approval; "
                "approval cannot authorize an older or equal serial. zone_octets is in [0,1000000].",
                source_url="https://www.rfc-editor.org/rfc/rfc1982.html#section-3.2",
                provenance="RFC 1982 defines finite serial comparison and leaves half-range comparisons "
                "undefined. Status 2 and manual approval are conventions of this authored zone publisher.",
                starter=starter, reference=reference, callers=_callers(transfer, flag, budget),
                **_cases(oracle, examples, hidden))


def _ranges():
    name = "first_byte"
    params = [("size", "int"), ("amount", "int"), ("suffix", "bool")]
    chunk = params + [("window", "int")]
    old_py = """
        if suffix:
            if amount == 0 or amount > size:
                return -1
            return size - amount
        return amount if amount < size else -1
    """
    old_braces = """
        if suffix {
            if amount == 0 || amount > size { return -1; }
            return size - amount;
        }
        return if amount < size { amount } else { -1 };
    """
    starter = _function(name, params, old_py, old_braces)
    reference = _function(name, params, """
        if suffix:
            if amount == 0:
                return -1
            return max(0, size - amount)
        return amount if amount < size else -1
    """, """
        if suffix {
            if amount == 0 { return -1; }
            return if amount < size { size - amount } else { 0 };
        }
        return if amount < size { amount } else { -1 };
    """)
    accept = _function("range_allowed", params, "return 1 if first_byte(size, amount, suffix) >= 0 else 0",
                       "return if first_byte(size, amount, suffix) >= 0 { 1 } else { 0 };")
    length = _function("response_length", params, """
        first = first_byte(size, amount, suffix)
        return size - first if first >= 0 else 0
    """, """
        let first = first_byte(size, amount, suffix);
        return if first >= 0 { size - first } else { 0 };
    """)
    pending = _function("pending_after_write", chunk, """
        return max(0, response_length(size, amount, suffix) - window)
    """, """
        let remaining = response_length(size, amount, suffix) - window;
        return if remaining > 0 { remaining } else { 0 };
    """)

    def oracle(entry, args):
        # Slice a concrete sequence of byte offsets. A positive suffix can
        # select an empty representation, whose normalized starting offset is 0.
        size, amount, suffix = args[:3]
        offsets = range(size)
        selected = offsets[-amount:] if suffix and amount else offsets[amount:] if not suffix else range(0)
        allowed = bool(selected) or (size == 0 and suffix and amount > 0)
        if entry == name:
            return selected[0] if selected else (0 if allowed else -1)
        if entry == "range_allowed":
            return int(allowed)
        if entry == "response_length":
            return len(selected)
        assert entry == "pending_after_write"
        return len(selected[args[3]:])

    examples = [(name, (4, 9, True), 0), ("range_allowed", (0, 3, True), 1),
                ("response_length", (9, 2, False), 7), ("pending_after_write", (10, 2, True, 1), 1)]
    hidden = [(name, (s, a, tail)) for s, a, tail in ((0, 0, False), (0, 0, True), (0, 1, True),
               (1, 1, False), (8, 0, True), (8, 8, True), (8, 7, True), (8, 7, False))]
    hidden += [("range_allowed", (1, 2, True)), ("range_allowed", (1, 2, False)),
               ("response_length", (12, 13, True)), ("response_length", (0, 3, True)),
               ("response_length", (3, 3, False)), ("pending_after_write", (8, 10, True, 2)),
               ("pending_after_write", (8, 7, True, 99)), ("pending_after_write", (8, 0, False, 0))]
    return dict(id="download_byte_ranges", kind="maintenance", form="body", target=name, params=params,
                description="Correct a download server's already-parsed single byte-range normalization. "
                "suffix=false means bytes=amount-: start at amount if it is strictly less than size, "
                "else return -1. suffix=true means bytes=-amount: a zero suffix is unsatisfiable (-1); "
                "a positive suffix selects up to that many final bytes. Oversized suffixes select the "
                "whole object. For an empty object a positive suffix is satisfiable with starting offset 0 "
                "and length 0. Preserve zero-based offsets, admission flags, response lengths and remaining "
                "bytes after the first write. size, amount and window are in [0,65535].",
                source_url="https://www.rfc-editor.org/rfc/rfc9110.html#section-14.1.2",
                provenance="RFC 9110 sections 14.1.1–14.1.2 define single suffix ranges, oversize handling "
                "and satisfiability on empty representations. The -1 sentinel and streaming callers are local.",
                starter=starter, reference=reference, callers=_callers(accept, length, pending),
                **_cases(oracle, examples, hidden))


TASKS = [_calendar(), _wave(), _dns(), _ranges()]
