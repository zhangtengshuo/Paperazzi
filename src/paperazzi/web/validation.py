"""Phase 5 HTTP validation helpers.

In-process HTTP validation uses HTTPX ASGITransport + AsyncClient. Product-path
validation starts a real Uvicorn subprocess and queries localhost with proxy
inheritance disabled.
"""
from __future__ import annotations
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import platform
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping
import httpx
from fastapi import FastAPI

PACKAGE_DISTRIBUTIONS = {
    "fastapi": "fastapi", "starlette": "starlette", "httpx": "httpx",
    "anyio": "anyio", "sqlalchemy": "SQLAlchemy", "alembic": "alembic",
    "uvicorn": "uvicorn", "pydantic": "pydantic", "pymupdf": "PyMuPDF",
}

def environment_snapshot() -> dict[str, object]:
    packages = {}
    for module_name, distribution_name in PACKAGE_DISTRIBUTIONS.items():
        try:
            version = importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        spec = importlib.util.find_spec(module_name)
        packages[module_name] = {
            "version": version,
            "module_origin": spec.origin if spec is not None else None,
        }
    try:
        loop_policy = type(asyncio.get_event_loop_policy()).__name__
    except Exception:
        loop_policy = "UNAVAILABLE"
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "sys_prefix": sys.prefix,
        "base_prefix": getattr(sys, "base_prefix", None),
        "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV"),
        "virtual_env_present": bool(os.environ.get("VIRTUAL_ENV")),
        "platform": platform.platform(),
        "sqlite_runtime": sqlite3.sqlite_version,
        "event_loop_policy": loop_policy,
        "proxy_env_present": {
            key: bool(os.environ.get(key))
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        },
        "packages": packages,
    }

def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp.replace(path)

def compare_constraints(path: Path) -> dict[str, object]:
    expected: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        expected[name.strip()] = version.strip()
    rows: dict[str, dict[str, object]] = {}
    for distribution, expected_version in expected.items():
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        rows[distribution] = {
            "expected": expected_version,
            "installed": installed,
            "matches": installed == expected_version,
        }
    return {
        "constraints_file": str(path),
        "matches": all(row["matches"] for row in rows.values()),
        "packages": rows,
    }

def _body_preview(response: httpx.Response, limit: int = 240) -> str | None:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type or "text/" in content_type or "html" in content_type:
        return response.text[:limit]
    return None

async def _run_asgi_smoke_async(app: FastAPI, routes: Mapping[str, str], request_timeout: float) -> dict[str, object]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    results = {}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://paperazzi.test",
        timeout=request_timeout, trust_env=False,
    ) as client:
        for name, path in routes.items():
            started = time.perf_counter()
            try:
                response = await asyncio.wait_for(client.get(path), timeout=request_timeout)
                results[name] = {
                    "path": path, "status_code": response.status_code,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "content_type": response.headers.get("content-type"),
                    "body_preview": _body_preview(response),
                }
            except asyncio.TimeoutError:
                results[name] = {
                    "path": path, "status": "TIMEOUT",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            except Exception as exc:
                results[name] = {
                    "path": path, "status": "ERROR", "error_type": type(exc).__name__,
                    "error": str(exc)[:800],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                }
    return results

def run_asgi_smoke(app: FastAPI, routes: Mapping[str, str], *, request_timeout: float = 5.0) -> dict[str, object]:
    started = time.perf_counter()
    try:
        requests = asyncio.run(_run_asgi_smoke_async(app, routes, request_timeout))
    except Exception as exc:
        return {
            "status": "ERROR", "error_type": type(exc).__name__, "error": str(exc)[:1200],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "requests": {},
        }
    ok = all(isinstance(row, dict) and isinstance(row.get("status_code"), int) for row in requests.values())
    return {
        "status": "PASS" if ok else "FAIL",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "requests": requests,
    }

def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])

def _terminate_process(proc: subprocess.Popen[str]) -> str:
    if proc.poll() is None:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
    else:
        output, _ = proc.communicate(timeout=2)
    return output[-6000:]

def run_uvicorn_smoke(
    db_path: Path, routes: Mapping[str, str], *,
    startup_timeout: float = 12.0, request_timeout: float = 5.0,
) -> dict[str, object]:
    port = _reserve_local_port()
    env = dict(os.environ)
    env["PAPERAZZI_DB"] = str(db_path.resolve())
    src_root = Path(__file__).resolve().parents[2]
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_root) if not current_pythonpath else str(src_root) + os.pathsep + current_pythonpath
    command = [
        sys.executable, "-m", "uvicorn", "paperazzi.web.api:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port), "--loop", "asyncio",
        "--http", "h11", "--lifespan", "off", "--log-level", "warning", "--no-access-log",
    ]
    started = time.perf_counter()
    proc = subprocess.Popen(
        command, cwd=Path(__file__).resolve().parents[3], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    requests = {}
    startup_error = None
    try:
        deadline = time.monotonic() + startup_timeout
        with httpx.Client(base_url=base_url, timeout=request_timeout, trust_env=False) as client:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    startup_error = f"Uvicorn exited early with code {proc.returncode}"
                    break
                try:
                    response = client.get("/health")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                startup_error = "Uvicorn startup timed out"
            if startup_error is None:
                for name, path in routes.items():
                    request_started = time.perf_counter()
                    try:
                        response = client.get(path)
                        requests[name] = {
                            "path": path, "status_code": response.status_code,
                            "elapsed_ms": round((time.perf_counter() - request_started) * 1000, 3),
                            "content_type": response.headers.get("content-type"),
                            "body_preview": _body_preview(response),
                        }
                    except Exception as exc:
                        requests[name] = {
                            "path": path, "status": "ERROR", "error_type": type(exc).__name__,
                            "error": str(exc)[:800],
                            "elapsed_ms": round((time.perf_counter() - request_started) * 1000, 3),
                        }
    finally:
        log_tail = _terminate_process(proc)
    status = "FAIL" if startup_error else (
        "PASS" if all(isinstance(row, dict) and isinstance(row.get("status_code"), int) for row in requests.values()) else "FAIL"
    )
    return {
        "status": status, "startup_error": startup_error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "port": port, "command": command, "requests": requests,
        "server_log_tail": log_tail,
        "http_proxy_inheritance": "DISABLED_BY_TRUST_ENV_FALSE",
    }
