from __future__ import annotations

import argparse
import csv
import io
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


SERVICE_ID = "decip-certificados"
LEGACY_PAGE_MARKER = b"<title>Certificados DECIP</title>"


class InstanceState(Enum):
    FREE = "free"
    DECIP = "decip"
    OTHER = "other"


@dataclass(frozen=True)
class ProbeResult:
    state: InstanceState
    detail: str = ""


@dataclass(frozen=True)
class ListenerDetails:
    pid: int | None = None
    name: str = "não identificado"
    executable: str = "não disponível"
    command_line: str = "não disponível"


def inspect_instance(host: str, port: int, timeout: float = 0.6) -> ProbeResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except ConnectionRefusedError:
        return ProbeResult(InstanceState.FREE)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10061:
            return ProbeResult(InstanceState.FREE)
        return ProbeResult(InstanceState.OTHER, f"falha ao consultar a porta ({type(exc).__name__})")

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("service") == SERVICE_ID and payload.get("status") == "ok":
                return ProbeResult(InstanceState.DECIP)
            return ProbeResult(InstanceState.OTHER, "resposta HTTP não pertence ao DECIP Certificados")
        except HTTPError as exc:
            if exc.code == 404:
                try:
                    with urlopen(f"http://{host}:{port}/", timeout=timeout) as response:
                        if LEGACY_PAGE_MARKER in response.read(65_536):
                            return ProbeResult(InstanceState.DECIP, "instância DECIP de versão anterior")
                except (HTTPError, URLError, OSError):
                    pass
            return ProbeResult(InstanceState.OTHER, f"não respondeu como DECIP ({type(exc).__name__})")
        except (URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.2)
    return ProbeResult(InstanceState.OTHER, f"não respondeu como DECIP ({type(last_error).__name__})")


def _listener_pid_from_netstat(port: int, host: str) -> int | None:
    completed = subprocess.run(
        ["netstat.exe", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )
    candidates: list[tuple[int, int]] = []
    for line in completed.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 5 and columns[0].upper() == "TCP" and columns[-2].upper() == "LISTENING":
            local_address = columns[1]
            address, _, local_port = local_address.rpartition(":")
            address = address.strip("[]")
            if local_port == str(port) and columns[-1].isdigit():
                if address == host:
                    score = 0
                elif address in {"0.0.0.0", "::", "*"}:
                    score = 1
                else:
                    continue
                candidates.append((score, int(columns[-1])))
    return min(candidates)[1] if candidates else None


def listener_details(port: int, host: str = "127.0.0.1") -> ListenerDetails:
    try:
        pid = _listener_pid_from_netstat(port, host)
    except (OSError, subprocess.SubprocessError):
        pid = None
    if pid is None:
        return ListenerDetails()

    script = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction Stop; "
        "$p | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            process = json.loads(completed.stdout)
            return ListenerDetails(
                pid=pid,
                name=process.get("Name") or "não identificado",
                executable=process.get("ExecutablePath") or "não disponível",
                command_line=process.get("CommandLine") or "não disponível",
            )
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass

    try:
        completed = subprocess.run(
            ["tasklist.exe", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        rows = list(csv.reader(io.StringIO(completed.stdout)))
        name = rows[0][0] if rows and len(rows[0]) >= 2 else "não identificado"
    except (OSError, subprocess.SubprocessError, csv.Error):
        name = "não identificado"
    return ListenerDetails(pid=pid, name=name)


def _print_conflict(host: str, port: int, reason: str) -> None:
    details = listener_details(port, host=host)
    print(f"[ERRO] A porta {port} está ocupada por outro serviço.")
    print(f"[DIAGNÓSTICO] Motivo: {reason}.")
    print(f"[DIAGNÓSTICO] PID: {details.pid if details.pid is not None else 'não identificado'}")
    print(f"[DIAGNÓSTICO] Processo: {details.name}")
    print(f"[DIAGNÓSTICO] Executável: {details.executable}")
    print(f"[DIAGNÓSTICO] Origem/comando: {details.command_line}")
    print("[SEGURANÇA] Nenhum processo foi encerrado automaticamente.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de inicialização do DECIP Certificados")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)

    result = inspect_instance(args.host, args.port)
    if result.state is InstanceState.FREE:
        return 0
    if result.state is InstanceState.DECIP:
        print(f"[DECIP] Uma instância funcional já está ativa em http://{args.host}:{args.port}.")
        return 10
    _print_conflict(args.host, args.port, result.detail)
    return 20


if __name__ == "__main__":
    sys.exit(main())
