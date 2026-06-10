"""
Tests for app.py: init_wasmtime, create_sample_wat, run_wasm_calculation.

app.py has module-level side effects (network download, file writes, Gradio UI
construction), so we mock the heavy dependencies before importing the module.
"""

import importlib
import subprocess
import sys
import types
import unittest
from io import StringIO
from unittest.mock import MagicMock, call, mock_open, patch


# ---------------------------------------------------------------------------
# Helpers to import app.py with all side-effecting calls neutralised
# ---------------------------------------------------------------------------

def _make_gradio_stub():
    """Return a minimal fake `gradio` module so the UI block never runs."""
    gr = types.ModuleType("gradio")
    for cls in (
        "Blocks", "Row", "Column", "Accordion",
        "Markdown", "Textbox", "Number", "Button", "Code",
    ):
        mock_cls = MagicMock()
        # Make instances usable as context managers
        mock_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        setattr(gr, cls, mock_cls)
    return gr


def _import_app_with_mocks(
    wasmtime_bin_exists=True,
    tar_path_exists=False,
    extracted_dirs=None,
):
    """
    Import (or reload) app.py with the desired filesystem state mocked.

    Returns the loaded module.
    """
    if extracted_dirs is None:
        extracted_dirs = ["wasmtime-v20.0.0-x86_64-linux"]

    # Remove cached module so each call gets a fresh import
    sys.modules.pop("app", None)

    gr_stub = _make_gradio_stub()
    sys.modules["gradio"] = gr_stub

    def fake_exists(path):
        # WASMTIME_BIN is checked by init_wasmtime and run_wasm_calculation
        import app as _app  # noqa: PLC0415 – needed for the path constant
        if path == _app.WASMTIME_BIN:
            return wasmtime_bin_exists
        if path == "wasmtime.tar.xz":
            return tar_path_exists
        return False

    mock_tar = MagicMock()
    mock_tar.__enter__ = MagicMock(return_value=mock_tar)
    mock_tar.__exit__ = MagicMock(return_value=False)

    with (
        patch("os.path.exists", side_effect=fake_exists),
        patch("os.listdir", return_value=extracted_dirs + ["other_dir"]),
        patch("os.path.isdir", return_value=True),
        patch("os.rename"),
        patch("os.remove"),
        patch("os.chmod"),
        patch("urllib.request.urlretrieve"),
        patch("tarfile.open", return_value=mock_tar),
        patch("builtins.open", mock_open()),
        patch("subprocess.run"),
    ):
        import app
        return app


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestInitWasmtime(unittest.TestCase):
    """Tests for init_wasmtime()."""

    def setUp(self):
        sys.modules.pop("app", None)
        sys.modules["gradio"] = _make_gradio_stub()

    def tearDown(self):
        sys.modules.pop("app", None)

    # -- already initialized --------------------------------------------------

    def test_already_initialized_returns_ready_message(self):
        """When the binary already exists, returns without downloading."""
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            result = app.init_wasmtime()

        self.assertEqual(result, "Wasmtime is already initialized and ready.")

    def test_already_initialized_does_not_call_urlretrieve(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
            patch("urllib.request.urlretrieve") as mock_retrieve,
        ):
            import app
            app.init_wasmtime()

        mock_retrieve.assert_not_called()

    # -- successful first-time download ---------------------------------------

    def test_successful_download_returns_success_message(self):
        sys.modules.pop("app", None)

        mock_tar = MagicMock()
        mock_tar.__enter__ = MagicMock(return_value=mock_tar)
        mock_tar.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def exists_side_effect(path):
            # First call (init_wasmtime guard) → False; subsequent calls → True
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return True

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("os.listdir", return_value=["wasmtime-v20.0.0-x86_64-linux"]),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.remove"),
            patch("os.chmod"),
            patch("urllib.request.urlretrieve"),
            patch("tarfile.open", return_value=mock_tar),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            result = app.init_wasmtime()

        self.assertEqual(result, "Wasmtime downloaded and initialized successfully!")

    def test_successful_download_calls_urlretrieve_with_correct_url(self):
        sys.modules.pop("app", None)

        mock_tar = MagicMock()
        mock_tar.__enter__ = MagicMock(return_value=mock_tar)
        mock_tar.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return True

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("os.listdir", return_value=["wasmtime-v20.0.0-x86_64-linux"]),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.remove"),
            patch("os.chmod"),
            patch("urllib.request.urlretrieve") as mock_retrieve,
            patch("tarfile.open", return_value=mock_tar),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            app.init_wasmtime()

        expected_url = (
            "https://github.com/bytecodealliance/wasmtime/releases/download/"
            "v20.0.0/wasmtime-v20.0.0-x86_64-linux.tar.xz"
        )
        mock_retrieve.assert_called_once_with(expected_url, "wasmtime.tar.xz")

    def test_archive_is_removed_after_extraction(self):
        sys.modules.pop("app", None)

        mock_tar = MagicMock()
        mock_tar.__enter__ = MagicMock(return_value=mock_tar)
        mock_tar.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return True  # tar_path existence check → True so remove is called

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("os.listdir", return_value=["wasmtime-v20.0.0-x86_64-linux"]),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.remove") as mock_remove,
            patch("os.chmod"),
            patch("urllib.request.urlretrieve"),
            patch("tarfile.open", return_value=mock_tar),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            app.init_wasmtime()

        mock_remove.assert_called_once_with("wasmtime.tar.xz")

    def test_chmod_sets_executable_permission(self):
        sys.modules.pop("app", None)

        mock_tar = MagicMock()
        mock_tar.__enter__ = MagicMock(return_value=mock_tar)
        mock_tar.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return True

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("os.listdir", return_value=["wasmtime-v20.0.0-x86_64-linux"]),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.remove"),
            patch("os.chmod") as mock_chmod,
            patch("urllib.request.urlretrieve"),
            patch("tarfile.open", return_value=mock_tar),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            app.init_wasmtime()

        mock_chmod.assert_called_once_with(app.WASMTIME_BIN, 0o755)

    # -- extracted directory not found ----------------------------------------

    def test_missing_extracted_dir_returns_error(self):
        sys.modules.pop("app", None)

        mock_tar = MagicMock()
        mock_tar.__enter__ = MagicMock(return_value=mock_tar)
        mock_tar.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return False

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            # no directory that starts with "wasmtime-v"
            patch("os.listdir", return_value=["other_dir"]),
            patch("os.path.isdir", return_value=True),
            patch("os.rename"),
            patch("os.remove"),
            patch("os.chmod"),
            patch("urllib.request.urlretrieve"),
            patch("tarfile.open", return_value=mock_tar),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            result = app.init_wasmtime()

        self.assertEqual(result, "Error: Could not find extracted wasmtime directory.")

    # -- exception during download --------------------------------------------

    def test_download_exception_returns_failure_message(self):
        sys.modules.pop("app", None)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return False

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("urllib.request.urlretrieve", side_effect=OSError("network error")),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            result = app.init_wasmtime()

        self.assertTrue(result.startswith("Initialization failed:"))
        self.assertIn("network error", result)

    def test_tarfile_exception_returns_failure_message(self):
        sys.modules.pop("app", None)

        call_count = {"n": 0}

        def exists_side_effect(path):
            if "wasmtime" in path and call_count["n"] == 0:
                call_count["n"] += 1
                return False
            return False

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("urllib.request.urlretrieve"),
            patch("tarfile.open", side_effect=tarfile.TarError("bad archive")),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            result = app.init_wasmtime()

        self.assertTrue(result.startswith("Initialization failed:"))
        self.assertIn("bad archive", result)


class TestCreateSampleWat(unittest.TestCase):
    """Tests for create_sample_wat()."""

    def setUp(self):
        sys.modules.pop("app", None)
        sys.modules["gradio"] = _make_gradio_stub()

    def tearDown(self):
        sys.modules.pop("app", None)

    def _load_app(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            return app

    def test_returns_string(self):
        app = self._load_app()
        m = mock_open()
        with patch("builtins.open", m):
            result = app.create_sample_wat()
        self.assertIsInstance(result, str)

    def test_return_value_contains_module_declaration(self):
        app = self._load_app()
        with patch("builtins.open", mock_open()):
            result = app.create_sample_wat()
        self.assertIn("(module", result)

    def test_return_value_contains_add_function(self):
        app = self._load_app()
        with patch("builtins.open", mock_open()):
            result = app.create_sample_wat()
        self.assertIn("(func $add", result)
        self.assertIn("i32.add", result)

    def test_return_value_exports_add_function(self):
        app = self._load_app()
        with patch("builtins.open", mock_open()):
            result = app.create_sample_wat()
        self.assertIn('(export "add"', result)

    def test_writes_to_sample_wat_path(self):
        app = self._load_app()
        m = mock_open()
        with patch("builtins.open", m):
            app.create_sample_wat()
        m.assert_called_once_with(app.SAMPLE_WAT, "w")

    def test_written_content_matches_return_value(self):
        app = self._load_app()
        m = mock_open()
        with patch("builtins.open", m):
            result = app.create_sample_wat()
        handle = m()
        written = "".join(
            call_args[0][0] for call_args in handle.write.call_args_list
        )
        self.assertEqual(written, result)


class TestRunWasmCalculation(unittest.TestCase):
    """Tests for run_wasm_calculation(a, b)."""

    def setUp(self):
        sys.modules.pop("app", None)
        sys.modules["gradio"] = _make_gradio_stub()

    def tearDown(self):
        sys.modules.pop("app", None)

    def _load_app(self, wasmtime_exists=True):
        def exists_side_effect(path):
            return wasmtime_exists

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("builtins.open", mock_open()),
            patch("subprocess.run"),
        ):
            import app
            return app

    # -- binary missing -------------------------------------------------------

    def test_missing_binary_returns_error_message(self):
        app = self._load_app()
        with patch("os.path.exists", return_value=False):
            result = app.run_wasm_calculation(1, 2)
        self.assertEqual(result, "Error: WASM runtime not initialized.")

    # -- successful execution -------------------------------------------------

    def test_successful_execution_returns_result_string(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "42\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = app.run_wasm_calculation(12, 30)

        self.assertIn("42", result)
        self.assertIn("WASM VM execution", result)

    def test_successful_execution_calls_compile_then_run(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "10\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(3, 7)

        self.assertEqual(mock_run.call_count, 2)
        # First call is the compile command
        compile_call_args = mock_run.call_args_list[0][0][0]
        self.assertIn("compile", compile_call_args)
        # Second call is the run command
        run_call_args = mock_run.call_args_list[1][0][0]
        self.assertIn("run", run_call_args)
        self.assertIn("--invoke", run_call_args)
        self.assertIn("add", run_call_args)

    def test_integer_arguments_passed_as_strings_to_subprocess(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "7\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(3, 4)

        run_call_args = mock_run.call_args_list[1][0][0]
        self.assertIn("3", run_call_args)
        self.assertIn("4", run_call_args)

    def test_float_inputs_are_truncated_to_int(self):
        """Floats are converted via int() before being passed to subprocess."""
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "5\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(2.9, 2.1)

        run_call_args = mock_run.call_args_list[1][0][0]
        self.assertIn("2", run_call_args)

    def test_negative_integer_inputs_passed_correctly(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "-3\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(-5, 2)

        run_call_args = mock_run.call_args_list[1][0][0]
        self.assertIn("-5", run_call_args)

    def test_zero_inputs_are_passed_correctly(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "0\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(0, 0)

        run_call_args = mock_run.call_args_list[1][0][0]
        self.assertEqual(run_call_args.count("0"), 2)

    # -- subprocess errors ----------------------------------------------------

    def test_called_process_error_on_compile_returns_error_message(self):
        app = self._load_app()

        error = subprocess.CalledProcessError(1, "wasmtime")
        error.stdout = "compile stdout"
        error.stderr = "compile stderr"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", side_effect=error),
        ):
            result = app.run_wasm_calculation(1, 2)

        self.assertIn("Execution Error", result)
        self.assertIn("compile stdout", result)
        self.assertIn("compile stderr", result)

    def test_called_process_error_on_run_returns_error_message(self):
        app = self._load_app()

        compile_result = MagicMock()
        compile_result.stdout = ""

        run_error = subprocess.CalledProcessError(1, "wasmtime")
        run_error.stdout = "run stdout"
        run_error.stderr = "run stderr"

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "subprocess.run",
                side_effect=[compile_result, run_error],
            ),
        ):
            result = app.run_wasm_calculation(1, 2)

        self.assertIn("Execution Error", result)
        self.assertIn("run stdout", result)
        self.assertIn("run stderr", result)

    def test_unexpected_exception_returns_error_message(self):
        app = self._load_app()

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", side_effect=RuntimeError("unexpected!")),
        ):
            result = app.run_wasm_calculation(1, 2)

        self.assertIn("Unexpected Error", result)
        self.assertIn("unexpected!", result)

    # -- subprocess flags -----------------------------------------------------

    def test_subprocess_run_called_with_capture_output_and_text(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "99\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            app.run_wasm_calculation(50, 49)

        for single_call in mock_run.call_args_list:
            kwargs = single_call[1]
            self.assertTrue(kwargs.get("capture_output"))
            self.assertTrue(kwargs.get("text"))
            self.assertTrue(kwargs.get("check"))

    # -- output stripping -----------------------------------------------------

    def test_stdout_is_stripped_of_whitespace(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "   42   \n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = app.run_wasm_calculation(12, 30)

        self.assertIn("42", result)
        self.assertNotIn("   42   ", result)

    # -- large boundary values ------------------------------------------------

    def test_large_integer_inputs_do_not_raise(self):
        app = self._load_app()

        mock_result = MagicMock()
        mock_result.stdout = "2000000000\n"

        with (
            patch("os.path.exists", return_value=True),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = app.run_wasm_calculation(1_000_000_000, 1_000_000_000)

        self.assertIn("WASM VM execution", result)


if __name__ == "__main__":
    unittest.main()
