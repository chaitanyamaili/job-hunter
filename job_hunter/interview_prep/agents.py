from __future__ import annotations

import subprocess

_AGENTS: dict[str, list[str]] = {
    "claude": ["claude", "-p"],
    "gemini": ["gemini", "-p"],
}


class AgentError(Exception):
    """Raised when a requested agent CLI is unavailable or fails."""


def run_agent(name: str, prompt: str) -> str:
    if name not in _AGENTS:
        valid = ", ".join(sorted(_AGENTS))
        raise AgentError(f"unknown agent '{name}'; expected one of: {valid}")

    argv = _AGENTS[name] + [prompt]
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AgentError(
            f"agent '{name}' not found on PATH; install it or omit --agent to get the prompt only"
        ) from exc

    if result.returncode != 0:
        raise AgentError(
            f"agent '{name}' exited with status {result.returncode}: {result.stderr.strip()}"
        )

    return result.stdout.strip()
