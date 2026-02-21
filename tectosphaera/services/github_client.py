import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("github_client")


class GitHubClient:
    """Асинхронный клиент для работы с репозиторием через GitHub API."""

    def __init__(self, token: Optional[str], repo: str):
        self.token = token
        self.repo = repo
        self.api_base = f"https://api.github.com/repos/{repo}"
        self.headers = (
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            if token
            else {"Accept": "application/vnd.github.v3+json"}
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()

    async def get_file(self, path: str, ref: str = "main") -&gt; Optional[str]:
        """Получить содержимое файла."""
        url = f"{self.api_base}/contents/{path}"
        params = {"ref": ref}
        try:
            resp = await self._client.get(  # type: ignore
                url, headers=self.headers, params=params
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8")
            return data["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.exception(f"GitHub API error while getting {path}")
            raise
        except Exception:
            logger.exception(f"Unexpected error while getting {path}")
            return None

    async def create_or_update_file(
        self,
        path: str,
        message: str,
        content: str,
        sha: Optional[str] = None,
        branch: str = "main",
    ) -&gt; Dict[str, Any]:
        """Создать или обновить файл."""
        url = f"{self.api_base}/contents/{path}"
        data = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            data["sha"] = sha
        resp = await self._client.put(url, headers=self.headers, json=data)  # type: ignore
        resp.raise_for_status()
        return resp.json()

    async def get_sha(self, path: str, ref: str = "main") -&gt; Optional[str]:
        """Получить SHA файла."""
        url = f"{self.api_base}/contents/{path}"
        params = {"ref": ref}
        try:
            resp = await self._client.get(  # type: ignore
                url, headers=self.headers, params=params
            )
            resp.raise_for_status()
            return resp.json()["sha"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception:
            logger.exception(f"Error getting SHA for {path}")
            return None