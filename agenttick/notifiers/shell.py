"""
Shell Notifier — Run a local command template with event fields.

Fields are injected via environment variables and string placeholders
for safety (no shell injection via field values).
"""

import asyncio
import os
import shlex
from typing import Dict, Optional

from .base import Notifier, register_notifier_type


class ShellNotifier(Notifier):
    """
    Execute a shell command template for notifications.

    Config:
        cmd: Command template string (required)
            Placeholders: {title}, {text}, {tags}
            Environment vars: AGENT_TICK_TITLE, AGENT_TICK_TEXT, AGENT_TICK_TAGS
        timeoutMs: Command timeout in milliseconds (default: 10000)
        shell: Whether to use shell execution (default: False for safety)

    Example cmd:
        'logger "agent-tick: {title} — {text}"'
        'notify-send "{title}" "{text}"'
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.cmd_template: str = config.get("cmd", "")
        if not self.cmd_template:
            raise ValueError("ShellNotifier requires 'cmd' in config")

        self.timeout_s: float = config.get("timeoutMs", 10000) / 1000.0
        self.use_shell: bool = config.get("shell", False)

    async def send(
        self, title: str, text: str, tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Execute the command with event fields substituted.

        Fields are:
        1. Substituted into the command template via str.format()
        2. Available as environment variables (AGENT_TICK_TITLE, etc.)
        """
        tags_str = ",".join(f"{k}={v}" for k, v in (tags or {}).items())

        # Sanitize values for safe template substitution
        safe_title = self._sanitize(title)
        safe_text = self._sanitize(text)
        safe_tags = self._sanitize(tags_str)

        try:
            cmd = self.cmd_template.format(
                title=safe_title,
                text=safe_text,
                tags=safe_tags,
            )
        except (KeyError, IndexError) as e:
            print(f"[ShellNotifier] Template error: {e}")
            return False

        # Set environment variables for the subprocess
        env = os.environ.copy()
        env["AGENT_TICK_TITLE"] = title
        env["AGENT_TICK_TEXT"] = text
        env["AGENT_TICK_TAGS"] = tags_str

        try:
            if self.use_shell:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                args = shlex.split(cmd)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_s
            )

            if proc.returncode == 0:
                return True
            else:
                print(
                    f"[ShellNotifier] Command exited with code {proc.returncode}: "
                    f"{stderr.decode().strip()}"
                )
                return False

        except asyncio.TimeoutError:
            print(
                f"[ShellNotifier] Command timed out after {self.timeout_s}s"
            )
            if proc:
                proc.kill()
            return False
        except FileNotFoundError as e:
            print(f"[ShellNotifier] Command not found: {e}")
            return False
        except Exception as e:
            print(f"[ShellNotifier] Error: {e}")
            return False

    @staticmethod
    def _sanitize(value: str) -> str:
        """
        Sanitize a value for safe template substitution.

        Removes characters that could cause shell injection when
        the command is not run through shell=True.
        """
        # Remove backticks, $(), and other shell expansion chars
        dangerous = ["`", "$(", "${", ";", "&&", "||", "|", "\n", "\r"]
        result = value
        for char in dangerous:
            result = result.replace(char, "")
        return result


# Register with factory
register_notifier_type("shell", ShellNotifier)
