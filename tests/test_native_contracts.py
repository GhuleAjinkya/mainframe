"""Source contract checks; these do not execute REXX or submit any JCL."""

from pathlib import Path
import re
import unittest

from stkcp.contracts import EXPLANATIONS, UNKNOWN_EXPLANATION


ROOT = Path(__file__).resolve().parents[1]


class NativeSourceContractTests(unittest.TestCase):
    def test_rexx_explanations_match_python_contract(self):
        source = (ROOT / "src/rexx/REPORT.rexx").read_text(encoding="ascii")
        mapping_source = source.split("Explain: procedure", 1)[1]
        matches = re.findall(
            r"when code = '([^']+)' then return,([\s\S]*?)"
            r"(?=\n    when|\n    otherwise)", mapping_source,
        )
        explanations = {
            code: " ".join(re.findall(r"'([^']*)'", body))
            for code, body in matches
        }
        self.assertEqual(explanations, EXPLANATIONS)
        fallback = mapping_source.split("otherwise return,", 1)[1]
        self.assertEqual(" ".join(re.findall(r"'([^']*)'", fallback)),
                         UNKNOWN_EXPLANATION)

    def test_sources_fit_dataset_record_widths(self):
        paths = [(ROOT / "src/rexx/REPORT.rexx", 80)]
        paths += [(path, 80) for path in (ROOT / "jcl").glob("*.jcl")]
        for path, width in paths:
            for number, line in enumerate(path.read_text("ascii").splitlines(), 1):
                with self.subTest(path=path.name, line=number):
                    self.assertLessEqual(len(line), width)
                    if line.startswith("//") and not line.startswith("//*"):
                        self.assertLessEqual(len(line), 71)


if __name__ == "__main__":
    unittest.main()
