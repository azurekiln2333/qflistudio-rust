"""Shared process-output regressions; execute only on GitHub-hosted runners."""

import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ci_support as support


def setUpModule():
    support.require_hosted_runner()


class ConsoleOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = mock.patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_TEMP": str(self.root),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def run_with_console(self, encoding, returncode):
        raw = "SDK \u4e2d\u6587 \u2022 ready\naccess_token=private-fixture-value\n::error::tool text\n"
        captured = io.BytesIO()
        console = io.TextIOWrapper(captured, encoding=encoding)
        log = self.root / f"{encoding}-{returncode}.log"

        def process(command, **kwargs):
            kwargs["stdout"].write(raw)
            return mock.Mock(returncode=returncode)

        try:
            with mock.patch.object(support.sys, "stdout", console), \
                    mock.patch.object(support.subprocess, "run", side_effect=process) as command:
                if returncode:
                    with self.assertRaisesRegex(RuntimeError, rf"Command failed \({returncode}\)"):
                        support.run(["mock-tool"], log, cwd=self.root)
                else:
                    output = support.run(["mock-tool"], log, cwd=self.root)
                    self.assertIn("SDK \u4e2d\u6587 \u2022 ready", output)
                command.assert_called_once()
            console.flush()
            published = captured.getvalue().decode(encoding)
        finally:
            console.detach()
        report = log.read_text(encoding="utf-8")
        self.assertIn("SDK \u4e2d\u6587 \u2022 ready", report)
        self.assertNotIn("private-fixture-value", report)
        self.assertNotIn("private-fixture-value", published)
        self.assertIn("[sensitive diagnostic line redacted]", report)
        lines = published.splitlines()
        stops = [index for index, line in enumerate(lines) if line.startswith("::stop-commands::")]
        self.assertEqual(len(stops), 2)
        for index in stops:
            token = lines[index].split("::stop-commands::", 1)[1]
            self.assertIn(f"::{token}::", lines[index + 1:])
        output_stop = stops[-1]
        output_resume = lines.index("::" + lines[output_stop].split("::stop-commands::", 1)[1] + "::")
        self.assertLess(output_stop, lines.index("::error::tool text"))
        self.assertLess(lines.index("::error::tool text"), output_resume)
        if encoding == "cp1252":
            self.assertIn(r"SDK \u4e2d\u6587", published)
        else:
            self.assertIn("SDK \u4e2d\u6587 \u2022 ready", published)
        return published

    def test_successful_unicode_process_output_preserves_reports_on_cp1252_and_utf8(self):
        for encoding in ("cp1252", "utf-8"):
            with self.subTest(encoding=encoding):
                self.run_with_console(encoding, 0)

    def test_unicode_failure_annotation_does_not_mask_nonzero_exit(self):
        published = self.run_with_console("cp1252", 7)
        self.assertIn("::error::Command failed (7)", published)
        self.assertIn(r"SDK \u4e2d\u6587", published)
        self.assertIn("%0A", published)

    def test_untrusted_output_restores_command_boundary_when_console_write_fails(self):
        with mock.patch.object(support.secrets, "token_hex", return_value="fixture-boundary"), \
                mock.patch.object(support, "print_console", side_effect=[None, OSError("console failed"), None]) as emit:
            with self.assertRaisesRegex(OSError, "console failed"):
                support.print_untrusted("untrusted")
        self.assertEqual(emit.call_args_list, [
            mock.call("::stop-commands::fixture-boundary"),
            mock.call("untrusted"), mock.call("::fixture-boundary::"),
        ])


if __name__ == "__main__":
    support.require_hosted_runner()
    unittest.main()
