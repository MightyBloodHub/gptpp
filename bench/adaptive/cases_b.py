"""Four application maintenance fixtures with hand-authored integration expectations."""

from textwrap import dedent, indent


def _function(name, params, python_body, braced_body):
    implementations = {}
    for lang, integer, boolean in (("python", "int", "bool"), ("rust", "i64", "bool"), ("gpp", "I64", "Bool")):
        args = ", ".join(f"{p}: {integer if ty == 'int' else boolean}" for p, ty in params)
        if lang == "python":
            header = f"def {name}({args}) -> int:"
            body = indent(dedent(python_body).strip(), "    ")
            implementations[lang] = f"{header}\n{body}\n"
        else:
            effect = " !{}" if lang == "gpp" else ""
            header = f"fn {name}({args}) -> {integer}{effect} {{"
            body = indent(dedent(braced_body).strip(), "    ")
            implementations[lang] = f"{header}\n{body}\n}}\n"
    return implementations


def _callers(*functions):
    return {lang: "\n".join(fn[lang] for fn in functions) for lang in ("python", "rust", "gpp")}


def _transit():
    name = "service_minute"
    params = [("hour", "int"), ("minute", "int")]
    wait_args = params + [("now", "int")]
    old_py = """
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return -1
        return hour * 60 + minute
    """
    old_braced = """
        if hour < 0 || hour > 23 || minute < 0 || minute > 59 { return -1; }
        return hour * 60 + minute;
    """
    wait = _function("wait_minutes", wait_args, """
        departure = service_minute(hour, minute)
        if departure < 0:
            return -1
        return max(0, departure - now)
    """, """
        let departure = service_minute(hour, minute);
        if departure < 0 { return -1; }
        return if departure > now { departure - now } else { 0 };
    """)
    day = _function("day_badge", params, """
        departure = service_minute(hour, minute)
        return -1 if departure < 0 else departure // 1440
    """, """
        let departure = service_minute(hour, minute);
        return if departure < 0 { -1 } else { departure / 1440 };
    """)
    return dict(
        id="night_service_board", kind="maintenance", form="body", target=name, params=params,
        description="The transit board rejects late trips in GTFS stop_times. Extend the supported hour range "
                    "from 0..23 to 0..47 inclusive. Return whole minutes from the start of the same service day, "
                    "without wrapping at midnight. Minutes stay 0..59. An invalid hour or minute returns -1. "
                    "Inputs are already split into integers. The board uses a fixed service-day clock.",
        source_url="https://gtfs.org/documentation/schedule/reference/#stop_timestxt",
        provenance="GTFS Schedule permits departures after midnight to retain hours of 24 or greater on the "
                   "originating service day. The 47-hour cap, minute precision, wait display and day badge "
                   "are conventions of this authored application.",
        starter=_function(name, params, old_py, old_braced),
        reference=_function(name, params, old_py.replace("> 23", "> 47"), old_braced.replace("> 23", "> 47")),
        callers=_callers(wait, day),
        public=[("wait_minutes", (24, 10, 1435), 15), (name, (25, 35), 1535),
                ("day_badge", (23, 59), 0), (name, (11, 60), -1)],
        heldout=[(name, (0, 0), 0), (name, (24, 0), 1440), (name, (47, 59), 2879),
                 (name, (48, 0), -1), (name, (-1, 0), -1), (name, (30, -1), -1),
                 ("day_badge", (24, 0), 1), ("day_badge", (47, 59), 1),
                 ("day_badge", (48, 3), -1), ("day_badge", (0, 12), 0),
                 ("wait_minutes", (23, 45, 1400), 25), ("wait_minutes", (25, 5, 1505), 0),
                 ("wait_minutes", (26, 2, 1570), 0), ("wait_minutes", (47, 59, 0), 2879),
                 ("wait_minutes", (48, 0, 1440), -1), ("wait_minutes", (4, 60, 0), -1)],
    )


def _database():
    name = "page_bytes"
    params = [("header_word", "int")]
    old_py = """
        if header_word in (512, 1024, 2048, 4096, 8192, 16384, 32768):
            return header_word
        return 0
    """
    old_braced = """
        if header_word == 512 || header_word == 1024 || header_word == 2048 ||
           header_word == 4096 || header_word == 8192 || header_word == 16384 || header_word == 32768 {
            return header_word;
        }
        return 0;
    """
    offset = _function("page_offset", params + [("page", "int")], """
        size = page_bytes(header_word)
        return -1 if size == 0 or page < 1 else (page - 1) * size
    """, """
        let size = page_bytes(header_word);
        return if size == 0 || page < 1 { -1 } else { (page - 1) * size };
    """)
    counts = _function("whole_pages", params + [("file_bytes", "int")], """
        size = page_bytes(header_word)
        return -1 if size == 0 else file_bytes // size
    """, """
        let size = page_bytes(header_word);
        return if size == 0 { -1 } else { file_bytes / size };
    """)
    return dict(
        id="sqlite_page_header", kind="maintenance", form="body", target=name, params=params,
        description="Upgrade the database inspector's page-size decoder for SQLite 3.7.1 files. header_word "
                    "is the two-byte big-endian field already decoded as an integer in 0..65535. A value of 1 "
                    "means 65536 bytes. Keep ordinary power-of-two sizes from 512 through 32768 unchanged "
                    "and return 0 for every other header. Existing consumers use one-based page numbers and "
                    "nonnegative file lengths; a partial trailing page does not count.",
        source_url="https://www.sqlite.org/fileformat.html#page_size",
        provenance="SQLite documents a file-format change in version 3.7.1 permitting a 65536-byte page via "
                   "a special header word. The inspection UI, invalid-value sentinel and callers are authored.",
        starter=_function(name, params, old_py, old_braced),
        reference=_function(name, params, "if header_word == 1:\n    return 65536\n" + dedent(old_py).strip(),
                            "if header_word == 1 { return 65536; }\n" + dedent(old_braced).strip()),
        callers=_callers(offset, counts),
        public=[("page_offset", (1, 3), 131072), (name, (1,), 65536),
                ("whole_pages", (4096, 8191), 1), (name, (1000,), 0)],
        heldout=[(name, (0,), 0), (name, (2,), 0), (name, (512,), 512), (name, (16384,), 16384),
                 (name, (32768,), 32768), (name, (32769,), 0), (name, (65535,), 0),
                 ("page_offset", (1, 1), 0), ("page_offset", (1, 0), -1), ("page_offset", (8192, 4), 24576),
                 ("page_offset", (768, 1), -1), ("whole_pages", (1, 65535), 0),
                 ("whole_pages", (1, 65536), 1), ("whole_pages", (1, 196610), 3),
                 ("whole_pages", (1024, 0), 0), ("whole_pages", (511, 8192), -1)],
    )


def _gallery():
    name = "display_width"
    params = [("width", "int"), ("height", "int"), ("orientation", "int")]
    pan = _function("horizontal_pan", params + [("viewport", "int")], """
        return max(0, display_width(width, height, orientation) - viewport)
    """, """
        let extra = display_width(width, height, orientation) - viewport;
        return if extra > 0 { extra } else { 0 };
    """)
    sheet = _function("strip_width", params + [("photos", "int")], """
        if photos == 0:
            return 0
        return photos * display_width(width, height, orientation) + (photos - 1) * 8
    """, """
        if photos == 0 { return 0; }
        return photos * display_width(width, height, orientation) + (photos - 1) * 8;
    """)
    return dict(
        id="mirrored_gallery_layout", kind="maintenance", form="expr", target=name, params=params,
        description="The gallery mislays photographs carrying mirrored EXIF orientations 5 and 7. Use stored "
                    "height as display width for every quarter-turn or diagonal transpose (tags 5 through 8 "
                    "inclusive). Return stored width for tags 1 through 4 and for unknown tags. Preserve the "
                    "pan and contact-strip calculations. Stored dimensions and viewport are positive pixels "
                    "up to 10000, and a strip holds 0..100 photographs.",
        source_url="https://github.com/python-pillow/Pillow/blob/10.4.0/src/PIL/ImageOps.py#L688-L701",
        provenance="Pillow's ImageOps.exif_transpose implementation maps EXIF 5 and 7 to diagonal transforms "
                   "and 6 and 8 to quarter turns. This authored gallery reproduces the effect on layout width.",
        starter=_function(name, params, "return height if orientation == 6 or orientation == 8 else width",
                          "return if orientation == 6 || orientation == 8 { height } else { width };"),
        reference=_function(name, params, "return height if 5 <= orientation <= 8 else width",
                            "return if orientation >= 5 && orientation <= 8 { height } else { width };"),
        callers=_callers(pan, sheet),
        public=[("horizontal_pan", (600, 900, 5, 700), 200), (name, (1200, 800, 7), 800),
                ("strip_width", (100, 70, 6, 2), 148), (name, (9, 5, 4), 9)],
        heldout=[(name, (13, 8, 0), 13), (name, (13, 8, 2), 13), (name, (13, 8, 3), 13),
                 (name, (13, 8, 5), 8), (name, (13, 8, 6), 8), (name, (13, 8, 8), 8),
                 (name, (13, 8, 9), 13), ("horizontal_pan", (100, 200, 7, 120), 80),
                 ("horizontal_pan", (200, 100, 5, 130), 0), ("horizontal_pan", (101, 70, 1, 100), 1),
                 ("horizontal_pan", (101, 70, 8, 70), 0), ("strip_width", (200, 120, 7, 3), 376),
                 ("strip_width", (71, 45, 5, 1), 45), ("strip_width", (71, 45, 5, 0), 0),
                 ("strip_width", (71, 45, 1, 2), 150), ("strip_width", (4, 4, 7, 3), 28)],
    )


def _text():
    name = "utf16_units"
    params = [("scalar", "int")]
    pair = [("first", "int"), ("second", "int")]
    span = _function("range_units", pair, """
        a = utf16_units(first)
        b = utf16_units(second)
        return -1 if a == 0 or b == 0 else a + b
    """, """
        let a = utf16_units(first);
        let b = utf16_units(second);
        return if a == 0 || b == 0 { -1 } else { a + b };
    """)
    advance = _function("advance_offset", [("offset", "int"), *params], """
        count = utf16_units(scalar)
        return offset + count
    """, """
        return offset + utf16_units(scalar);
    """)
    recover = _function("range_end", [("start", "int"), *pair], """
        count = range_units(first, second)
        return start if count < 0 else start + count
    """, """
        let count = range_units(first, second);
        return if count < 0 { start } else { start + count };
    """)
    return dict(
        id="utf16_editor_offsets", kind="maintenance", form="expr", target=name, params=params,
        description="Our editor drops supplementary Unicode scalars when converting selections into UTF-16 "
                    "offsets. Return 1 code unit for scalar values 0..65535 except the surrogate range "
                    "55296..57343, and 2 for 65536..1114111 inclusive. Return 0 for the surrogate range, "
                    "negative numbers and values above the Unicode maximum. Inputs are integers. Preserve "
                    "the selection callers' behavior for an invalid input.",
        source_url="https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/#G25660",
        provenance="The Unicode Standard defines scalar values and their UTF-16 encoding. The cursor and "
                   "two-scalar selection APIs, including their invalid-value handling, are authored.",
        starter=_function(name, params, "return 1 if 0 <= scalar <= 65535 and not 55296 <= scalar <= 57343 else 0",
                          "return if scalar >= 0 && scalar <= 65535 && (scalar < 55296 || scalar > 57343) { 1 } else { 0 };"),
        reference=_function(name, params, "return 2 if 65536 <= scalar <= 1114111 else "
                            "(1 if 0 <= scalar <= 65535 and not 55296 <= scalar <= 57343 else 0)",
                            "return if scalar >= 65536 && scalar <= 1114111 { 2 } else { "
                            "if scalar >= 0 && scalar <= 65535 && (scalar < 55296 || scalar > 57343) { 1 } else { 0 } };"),
        callers=_callers(span, advance, recover),
        public=[("range_end", (12, 65, 128578), 15), (name, (65536,), 2),
                ("advance_offset", (7, 55296), 7), ("range_units", (65, 233), 2)],
        heldout=[(name, (-1,), 0), (name, (0,), 1), (name, (55295,), 1), (name, (56320,), 0),
                 (name, (57343,), 0), (name, (57344,), 1), (name, (65535,), 1), (name, (1114111,), 2),
                 (name, (1114112,), 0), ("advance_offset", (11, 128512), 13), ("advance_offset", (9, 90), 10),
                 ("range_units", (128512, 65536), 4), ("range_units", (128512, 57343), -1),
                 ("range_end", (0, 65536, 1114111), 4), ("range_end", (70, 57343, 128512), 70),
                 ("range_end", (11, 0, 65535), 13)],
    )


TASKS = [_transit(), _database(), _gallery(), _text()]
