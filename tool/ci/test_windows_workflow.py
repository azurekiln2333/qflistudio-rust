from pathlib import Path
import unittest

from ci_support import require_hosted_runner


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "app-installers.yml"
)


def setUpModule() -> None:
    require_hosted_runner()


class WindowsWorkflowTests(unittest.TestCase):
    def test_long_paths_are_enabled_and_verified_before_checkout(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        application_job = workflow.split("\n  application:\n", 1)[1]
        setup_start = application_job.index(
            "      - name: Enable Windows long paths for Git"
        )
        checkout_start = application_job.index("      - uses: actions/checkout@")
        setup_step = application_job[setup_start:checkout_start]

        self.assertIn("if: runner.os == 'Windows'", setup_step)
        self.assertIn("working-directory: ${{ github.workspace }}", setup_step)
        self.assertIn("shell: bash", setup_step)
        self.assertIn("git config --global core.longpaths true", setup_step)
        self.assertIn(
            'if [[ "$(git config --global --get core.longpaths)" != "true" ]]; then',
            setup_step,
        )
        self.assertIn("exit 1", setup_step)


if __name__ == "__main__":
    unittest.main()
