"""Cross-language tests of reverse graph traversal and bounded excerpt selection."""
import unittest

from caller_context import caller_context


def function(name, body, signature=None):
    return {"name": name, "signature": signature or f"decl {name}()", "body": body}


class CallerContextTests(unittest.TestCase):
    def test_reverse_edges_depth_and_recursion_across_surfaces(self):
        for language, comment in [("gpp", "//"), ("rust", "//"), ("python", "#")]:
            records = [
                function("leaf", "return relay(1)"),
                function("relay", "before = 1\nvalue = leaf(before)\nreturn value"),
                function("client", "return relay(2)"),
                function("third_hop", "return client(1)"),
                function("decoy", f"{comment} leaf(9)\nreturn 345"),
            ]
            with self.subTest(language=language):
                text = caller_context(records, "leaf", language)
                self.assertLess(text.index("decl relay"), text.index("decl client"))
                self.assertIn("value = leaf(before)", text)
                self.assertNotIn("decl leaf", text)
                self.assertNotIn("third_hop", text)
                self.assertNotIn("decoy", text)
                self.assertEqual(text, caller_context(reversed(records), "leaf", language))

    def test_python_and_rust_declarations_comments_literals_and_attributes_are_not_edges(self):
        records = [function("target", "return 1")]
        py = [
            function("quoted", 'return "target(5)"'),
            function("attribute", "return obj.target()"),
            function("decl", "def target():\n    return 0\nreturn target()"),
            function("nested", "def another():\n    return target()\nreturn 1"),
        ]
        rust = [
            function("quoted", 'let s = r##"abc " target(5)"##; 1'),
            function("comment", "/* /* inner */ still target() */ 2"),
            function("attribute", "obj.target()"),
            function("decl", "fn target() -> i64 { 0 } target()"),
            function("nested", "fn another() -> i64 { target() } 1"),
        ]
        for lang, decoys in [("python", py), ("rust", rust)]:
            self.assertEqual(caller_context(records + decoys, "target", lang), "")

    def test_breadth_name_ties_and_long_lines_obey_budget(self):
        records = [function("target", "return 0;")]
        for name in ("z", "a", "d", "b", "c"):
            records.append(function(name, "let x = " + "0 + " * 300 + "target(1)" + " + 1" * 300 + ";",
                                    name + "p" * 500))
        text = caller_context(records, "target", "gpp")
        self.assertLess(len(text), 1500)
        self.assertEqual(text.count("target(1)"), 3)
        self.assertIn("appp", text)
        self.assertIn("bppp", text)
        self.assertIn("cppp", text)
        self.assertNotIn("zppp", text)

    def test_diamond_uses_one_earliest_callsite(self):
        records = [function("leaf", "return 0;"), function("left", "return leaf();"),
                   function("right", "return leaf();"),
                   function("top", "let x = right();\nreturn left() + x;")]
        text = caller_context(records, "leaf", "gpp")
        self.assertEqual(text.count("decl top"), 1)
        self.assertIn("decl top()  [calls right]", text)


if __name__ == "__main__":
    unittest.main()
