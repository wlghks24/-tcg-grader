#!/usr/bin/env python3
"""환경변수 기반 GitHub Contents API 동기화.
토큰을 소스에 저장하지 않으며, 설정이 없으면 네트워크 요청을 하지 않는다.
"""
from __future__ import annotations
import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from safe_runtime import (
    atomic_write_json,
    env_int,
    reject_nonstandard_json,
    safe_read_text,
    safe_urlopen_no_redirect,
    unique_json_object,
)


class GitHubSyncEngine:
    def __init__(self, token=None, repo_owner=None, repo_name=None, file_path="tcg_sync_data.json", branch=None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo_owner = repo_owner or os.environ.get("GITHUB_OWNER", "")
        self.repo_name = repo_name or os.environ.get("GITHUB_REPO", "")
        self.file_path = file_path
        self.branch = branch or os.environ.get("GITHUB_BRANCH", "main")
        self.cache = Path(os.environ.get("TCG_GITHUB_CACHE", ".github_sync_cache.json"))

    @property
    def configured(self):
        return bool(self.token and self.repo_owner and self.repo_name)


    def _validate_config(self):
        slug=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
        if not slug.fullmatch(self.repo_owner or "") or not slug.fullmatch(self.repo_name or ""):
            raise ValueError("invalid GitHub repository identity")
        pure=Path(self.file_path)
        if pure.is_absolute() or ".." in pure.parts or not self.file_path or len(self.file_path)>300:
            raise ValueError("invalid GitHub file path")

    def _url(self):
        self._validate_config()
        path = urllib.parse.quote(self.file_path, safe="/")
        return f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{path}"

    def _request(self, method="GET", payload=None):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "TCG-Grader-Sync/75",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {self.token}",
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self._url(), data=data, headers=headers, method=method)
        
        timeout=env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
        # v75: bearer-token requests never follow redirects, preventing Authorization leakage.
        with safe_urlopen_no_redirect(req, timeout=timeout, allowed_hosts={'api.github.com'}) as response:
            return json.loads(response.read().decode("utf-8"))

    def _load_cache(self):
        try:
            return json.loads(
                safe_read_text(self.cache),
                parse_constant=reject_nonstandard_json,
                object_pairs_hook=unique_json_object,
            )
        except (OSError, ValueError, TypeError):
            return []

    def _save_cache(self, data):
        try:
            atomic_write_json(self.cache,data,suffix=".cache.tmp")
        except (OSError, ValueError, TypeError):
            pass

    def pull_from_github(self):
        if not self.configured:
            return self._load_cache(), None
        try:
            obj = self._request()
            content = base64.b64decode(obj.get("content", "")).decode("utf-8")
            data = json.loads(content)
            self._save_cache(data)
            return data, obj.get("sha")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
            return self._load_cache(), None

    def push_to_github(self, data, sha=None, message="TCG data sync"):
        if not self.configured:
            self._save_cache(data)
            return False
        payload = {
            "message": message,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        try:
            self._request("PUT", payload)
            self._save_cache(data)
            return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._save_cache(data)
            return False
