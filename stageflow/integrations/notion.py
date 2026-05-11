"""Notion REST API integration for StageFlow page syncing."""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, List, Any
from pathlib import Path

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

DEFAULT_STAGE_STATUS_MAP: Dict[str, str] = {
    "pick": "Backlog",
    "analyze": "In Progress",
    "plan": "In Progress",
    "implement": "In Progress",
    "verify": "In Review",
    "document": "In Progress",
    "review": "In Review",
    "wrap_up": "Done",
    "mr": "In Review",
    "done": "Done",
}


def _load_env(path: Optional[Path] = None) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    if path is None:
        path = Path(".env")
    if not path.exists():
        return env_vars
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env_vars[key] = value
    return env_vars


class NotionClient:
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get(
            "NOTION_API_KEY"
        ) or _load_env().get("NOTION_API_KEY")
        if not self._api_key:
            raise ValueError(
                "NOTION_API_KEY not set. Pass api_key parameter, "
                "set NOTION_API_KEY environment variable, or add to .env file."
            )

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{NOTION_API_URL}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"error": json.loads(e.read().decode("utf-8")), "status": e.code}

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """Fetch a page by its ID."""
        return self._request("GET", f"/pages/{page_id}")

    def update_page_properties(
        self,
        page_id: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update a page's properties."""
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """Query a database for pages."""
        body: Dict[str, Any] = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        return self._request("POST", f"/databases/{database_id}/query", body)

    def get_database(self, database_id: str) -> Dict[str, Any]:
        """Get database metadata including property schema."""
        return self._request("GET", f"/databases/{database_id}")

    def create_page(
        self,
        parent_database_id: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a new page in a database."""
        parent = {"database_id": parent_database_id, "type": "database_id"}
        body: Dict[str, Any] = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children
        return self._request("POST", "/pages", body)

    def sync_stage_to_status(
        self,
        page_id: str,
        stage_name: str,
        status_property: str = "Status",
        stage_status_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Sync a StageFlow stage to a Notion page status property.

        Maps the stage name to a Notion status value, then updates
        the page's status property.
        """
        status_name = (stage_status_map or DEFAULT_STAGE_STATUS_MAP).get(
            stage_name, "In Progress"
        )

        page_data = self.get_page(page_id)
        if "error" in page_data:
            return page_data

        properties = page_data.get("properties", {})
        status_prop = properties.get(status_property)
        if not status_prop:
            return {
                "error": f"Status property '{status_property}' not found on page. "
                f"Available: {', '.join(properties.keys())}"
            }

        status_type = status_prop.get("type", "status")
        return self.update_page_properties(page_id, {
            status_property: {status_type: {"name": status_name}}
        })

    def append_blocks(
        self,
        page_id: str,
        blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Append content blocks to a page."""
        return self._request(
            "PATCH", f"/blocks/{page_id}/children", {"children": blocks}
        )

    def search_pages(
        self,
        query: str,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """Search for pages across a workspace."""
        body = {"query": query, "page_size": page_size}
        return self._request("POST", "/search", body)
