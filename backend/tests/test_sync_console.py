"""Dependency-free regression of the real summary function against Windows cp1252."""
import ast
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout


class SyncConsoleTests(unittest.TestCase):
    def test_summary_survives_windows_console_encoding(self):
        # Extract only the stdlib-only output helper; no model/DB/network is needed.
        source = Path(__file__).parents[1] / "app" / "sync.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "print_sync_summary")
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        raw = io.BytesIO()
        output = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        report = SimpleNamespace(synced=["Test Volunteer (DEMO-001)"], failed=[("Other Volunteer", "No usable face")])
        with redirect_stdout(output):
            namespace["print_sync_summary"](report)
        output.flush()
        text = raw.getvalue().decode("cp1252")
        self.assertIn("Done: 1 synced, 1 failed.", text)
        self.assertIn("[OK] Test Volunteer", text)
        self.assertIn("[FAILED] Other Volunteer", text)
        output.detach()


if __name__ == "__main__":
    unittest.main()
