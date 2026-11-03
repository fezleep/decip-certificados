import os
import shutil
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from app.launcher import InstanceState, inspect_instance, listener_details, main as launcher_main
from app.web import create_app
import run


ROOT = Path(__file__).resolve().parents[1]


class _Connection:
    def __enter__(self): return self
    def __exit__(self, *_): pass


class _Response(BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class LauncherTests(unittest.TestCase):
    def _run_launcher_sandbox(self, probe_exit_code, runtime_exit_code=0):
        temporary = tempfile.TemporaryDirectory(dir=ROOT)
        sandbox = Path(temporary.name)
        launcher = (ROOT / "iniciar.bat").read_text(encoding="utf-8")
        launcher = launcher.replace(
            'start "DECIP Certificados" http://127.0.0.1:8766',
            'echo opened>browser-opened.txt',
        )
        (sandbox / "iniciar.bat").write_text(launcher, encoding="utf-8")
        scripts = sandbox / ".venv" / "Scripts"
        scripts.mkdir(parents=True)
        base_python = Path(os.sys._base_executable)
        shutil.copy2(base_python, scripts / "python.exe")
        (sandbox / ".venv" / "pyvenv.cfg").write_text(
            f"home = {base_python.parent}\nexecutable = {base_python}\nversion = 3.12.0\n",
            encoding="utf-8",
        )
        app_dir = sandbox / "app"
        app_dir.mkdir()
        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "launcher.py").write_text(
            f"import sys\nprint('[SONDA] status {probe_exit_code}')\nsys.exit({probe_exit_code})\n",
            encoding="utf-8",
        )
        (sandbox / "run.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "Path('server-started.txt').write_text('started', encoding='utf-8')\n"
            f"sys.exit({runtime_exit_code})\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "iniciar.bat"],
            cwd=sandbox,
            input="\n",
            text=True,
            capture_output=True,
            timeout=10,
        )
        return temporary, sandbox, result

    def test_health_endpoint_identifies_decip_without_exposing_state(self):
        app = create_app({"TESTING": True, "DB_PATH": ":memory:"})

        response = app.test_client().get("/api/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"service": "decip-certificados", "status": "ok"}, response.get_json())

    def test_inspect_instance_reports_free_port(self):
        with patch("app.launcher.socket.create_connection", side_effect=ConnectionRefusedError):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.FREE, result.state)

    def test_inspect_instance_does_not_treat_socket_access_denied_as_free(self):
        denied = PermissionError(10013, "acesso ao socket negado")
        with patch("app.launcher.socket.create_connection", side_effect=denied):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.OTHER, result.state)
        self.assertIn("PermissionError", result.detail)

    def test_inspect_instance_recognizes_existing_decip(self):
        with patch("app.launcher.socket.create_connection", return_value=_Connection()), \
             patch("app.launcher.urlopen", return_value=_Response(b'{"service":"decip-certificados","status":"ok"}')):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.DECIP, result.state)

    def test_inspect_instance_rejects_another_http_service(self):
        with patch("app.launcher.socket.create_connection", return_value=_Connection()), \
             patch("app.launcher.urlopen", return_value=_Response(b'{"service":"outro-programa","status":"ok"}')):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.OTHER, result.state)

    def test_inspect_instance_rejects_json_that_is_not_an_object(self):
        with patch("app.launcher.socket.create_connection", return_value=_Connection()), \
             patch("app.launcher.urlopen", return_value=_Response(b"[]")):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.OTHER, result.state)
        self.assertIn("não pertence", result.detail)

    def test_inspect_instance_retries_health_while_decip_is_starting(self):
        responses = [TimeoutError(), _Response(b'{"service":"decip-certificados","status":"ok"}')]
        with patch("app.launcher.socket.create_connection", return_value=_Connection()), \
             patch("app.launcher.urlopen", side_effect=responses), \
             patch("app.launcher.time.sleep"):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.DECIP, result.state)

    def test_inspect_instance_recognizes_decip_version_without_health_endpoint(self):
        missing_health = HTTPError("http://127.0.0.1:8766/api/health", 404, "Not Found", {}, None)
        legacy_page = _Response(b"<html><head><title>Certificados DECIP</title></head></html>")
        with patch("app.launcher.socket.create_connection", return_value=_Connection()), \
             patch("app.launcher.urlopen", side_effect=[missing_health, legacy_page]):
            result = inspect_instance("127.0.0.1", 8766)

        self.assertIs(InstanceState.DECIP, result.state)

    @unittest.skipUnless(os.name == "nt", "diagnóstico de processo específico do Windows")
    def test_listener_details_reports_pid_for_controlled_service(self):
        netstat = subprocess.CompletedProcess([], 0, "  TCP    127.0.0.1:8766    0.0.0.0:0    LISTENING    4321\n", "")
        process = subprocess.CompletedProcess([], 0, '{"ProcessId":4321,"Name":"python.exe","ExecutablePath":"C:\\\\Python312\\\\python.exe","CommandLine":"python run.py"}', "")
        with patch("app.launcher.subprocess.run", side_effect=[netstat, process]):
            details = listener_details(8766)

        self.assertEqual(4321, details.pid)
        self.assertEqual("python.exe", details.name)
        self.assertEqual("C:\\Python312\\python.exe", details.executable)
        self.assertEqual("python run.py", details.command_line)

    @unittest.skipUnless(os.name == "nt", "diagnóstico de processo específico do Windows")
    def test_listener_details_prefers_loopback_listener_for_same_port(self):
        netstat_output = (
            "  TCP    10.0.0.5:8766      0.0.0.0:0    LISTENING    1111\n"
            "  TCP    127.0.0.1:8766     0.0.0.0:0    LISTENING    2222\n"
        )
        netstat = subprocess.CompletedProcess([], 0, netstat_output, "")
        process = subprocess.CompletedProcess([], 0, '{"ProcessId":2222,"Name":"python.exe","ExecutablePath":"C:\\\\Python312\\\\python.exe","CommandLine":"python run.py"}', "")
        with patch("app.launcher.subprocess.run", side_effect=[netstat, process]):
            details = listener_details(8766, host="127.0.0.1")

        self.assertEqual(2222, details.pid)

    @unittest.skipUnless(os.name == "nt", "diagnóstico de processo específico do Windows")
    def test_listener_details_remains_useful_when_metadata_is_unavailable(self):
        netstat = subprocess.CompletedProcess([], 1, "", "acesso negado")
        with patch("app.launcher.subprocess.run", return_value=netstat):
            details = listener_details(8766)

        self.assertIsNone(details.pid)
        self.assertEqual("não identificado", details.name)
        self.assertEqual("não disponível", details.executable)

    def test_server_binds_before_opening_browser_and_stays_in_foreground(self):
        events = []

        class FakeServer:
            def serve_forever(self): events.append("serve")
            def server_close(self): events.append("close")

        def server_factory(host, port, app, threaded):
            events.append(("bind", host, port, threaded))
            return FakeServer()

        result = run.main(
            app_factory=lambda: object(),
            server_factory=server_factory,
            browser_open=lambda url: events.append(("browser", url)),
        )

        self.assertEqual(0, result)
        self.assertEqual(
            [("bind", "127.0.0.1", 8766, True), ("browser", "http://127.0.0.1:8766"), "serve", "close"],
            events,
        )

    def test_launcher_checks_port_8766_by_default(self):
        with patch("app.launcher.inspect_instance") as inspect:
            inspect.return_value.state = InstanceState.FREE

            result = launcher_main([])

        self.assertEqual(0, result)
        inspect.assert_called_once_with("127.0.0.1", 8766)

    def test_browser_failure_does_not_stop_server(self):
        events = []

        class FakeServer:
            def serve_forever(self): events.append("serve")
            def server_close(self): events.append("close")

        result = run.main(
            app_factory=lambda: object(),
            server_factory=lambda *args, **kwargs: FakeServer(),
            browser_open=lambda url: (_ for _ in ()).throw(OSError("sem navegador")),
        )

        self.assertEqual(0, result)
        self.assertEqual(["serve", "close"], events)

    def test_ctrl_c_closes_foreground_server_cleanly(self):
        events = []

        class FakeServer:
            def serve_forever(self): raise KeyboardInterrupt
            def server_close(self): events.append("close")

        result = run.main(
            app_factory=lambda: object(),
            server_factory=lambda *args, **kwargs: FakeServer(),
            browser_open=lambda url: None,
        )

        self.assertEqual(0, result)
        self.assertEqual(["close"], events)

    def test_existing_decip_opens_existing_instance_without_starting_server(self):
        temporary, sandbox, result = self._run_launcher_sandbox(10)
        try:
            self.assertEqual(0, result.returncode)
            self.assertFalse((sandbox / "server-started.txt").exists())
            self.assertEqual("opened", (sandbox / "browser-opened.txt").read_text(encoding="utf-8").strip())
            self.assertIn("instancia existente", (result.stdout + result.stderr).lower())
        finally:
            temporary.cleanup()

    def test_other_service_blocks_start_without_terminating_or_starting_it(self):
        temporary, sandbox, result = self._run_launcher_sandbox(20)
        try:
            self.assertNotEqual(0, result.returncode)
            self.assertFalse((sandbox / "server-started.txt").exists())
            self.assertIn("outro programa", (result.stdout + result.stderr).lower())
        finally:
            temporary.cleanup()

    def test_free_port_starts_server_once(self):
        temporary, sandbox, result = self._run_launcher_sandbox(0)
        try:
            self.assertEqual(0, result.returncode)
            self.assertEqual("started", (sandbox / "server-started.txt").read_text(encoding="utf-8"))
        finally:
            temporary.cleanup()

    def test_runtime_failure_is_reported_and_keeps_window_open(self):
        temporary, sandbox, result = self._run_launcher_sandbox(0, runtime_exit_code=7)
        try:
            output = result.stdout + result.stderr
            self.assertEqual(7, result.returncode)
            self.assertTrue((sandbox / "server-started.txt").exists())
            self.assertIn("ERRO", output.upper())
            self.assertIn("Pressione uma tecla para continuar", output)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
