"""Tests for Notion integration."""

import json
from unittest.mock import patch
import pytest

from stageflow.integrations.notion import (
    NotionClient,
    DEFAULT_STAGE_STATUS_MAP,
    _load_env,
)


def _mock_urlopen(data: dict, status: int = 200):
    class MockResponse:
        def read(self):
            return json.dumps(data).encode("utf-8")
        def getcode(self):
            return status
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    def opener(request, timeout=None):
        return MockResponse()
    return opener


class TestNotionClientInit:
    def test_init_with_explicit_key(self):
        client = NotionClient(api_key="secret_notion_key")
        assert client._api_key == "secret_notion_key"

    def test_init_from_env_var(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "env_notion_key")
        client = NotionClient()
        assert client._api_key == "env_notion_key"

    def test_init_from_dotenv(self, monkeypatch):
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        with patch("stageflow.integrations.notion._load_env",
                   return_value={"NOTION_API_KEY": "dotenv_key"}):
            client = NotionClient()
            assert client._api_key == "dotenv_key"

    def test_init_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("NOTION_API_KEY", raising=False)
        with patch("stageflow.integrations.notion._load_env", return_value={}):
            with pytest.raises(ValueError, match="NOTION_API_KEY not set"):
                NotionClient()


class TestNotionGetPage:
    def test_get_page(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "id": "page-1",
            "properties": {
                "Status": {"type": "status", "status": {"name": "Todo"}},
                "Name": {"type": "title", "title": [{"text": {"content": "Fix bug"}}]},
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.get_page("page-1")
        assert result["id"] == "page-1"

    def test_get_page_not_found(self, monkeypatch):
        import urllib.error
        import io
        monkeypatch.setenv("NOTION_API_KEY", "test")
        def raise_404(request, timeout=None):
            raise urllib.error.HTTPError(
                "url", 404, "Not Found", {},
                io.BytesIO(json.dumps({"message": "Page not found"}).encode())
            )
        with patch("urllib.request.urlopen", raise_404):
            client = NotionClient()
            result = client.get_page("bad-id")
        assert "error" in result
        assert result["status"] == 404


class TestNotionUpdate:
    def test_update_page_properties(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "id": "page-1",
            "properties": {"Status": {"type": "status", "status": {"name": "Done"}}}
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.update_page_properties("page-1", {
                "Status": {"status": {"name": "Done"}}
            })
        assert result["properties"]["Status"]["status"]["name"] == "Done"


class TestNotionDatabase:
    def test_query_database(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "results": [
                {"id": "p1", "properties": {"Name": {"title": [{"text": {"content": "Task 1"}}]}}},
            ],
            "has_more": False,
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.query_database("db-1")
        assert len(result["results"]) == 1

    def test_query_database_with_filter(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {"results": [], "has_more": False}
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.query_database(
                "db-1",
                filter_obj={"property": "Status", "status": {"equals": "In Progress"}}
            )
        assert result["results"] == []

    def test_get_database(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "id": "db-1",
            "properties": {
                "Status": {"type": "status", "status": {}},
                "Name": {"type": "title", "title": {}},
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.get_database("db-1")
        assert "Status" in result["properties"]


class TestNotionCreate:
    def test_create_page(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "id": "new-page",
            "properties": {"Name": {"title": [{"text": {"content": "New Task"}}]}},
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.create_page("db-1", {
                "Name": {"title": [{"text": {"content": "New Task"}}]},
            })
        assert result["id"] == "new-page"


class TestNotionSync:
    def test_sync_stage_to_status(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        call_count = [0]
        responses = [
            {  # get_page
                "id": "page-x",
                "properties": {
                    "Status": {"type": "status", "status": {"name": "Todo"}},
                    "Name": {"type": "title", "title": []},
                },
            },
            {  # update_page_properties
                "id": "page-x",
                "properties": {
                    "Status": {"type": "status", "status": {"name": "In Review"}},
                },
            },
        ]
        def multi_response(request, timeout=None):
            idx = call_count[0]
            call_count[0] += 1
            class M:
                def read(s):
                    return json.dumps(responses[idx]).encode("utf-8")
                def __enter__(s): return s
                def __exit__(s, *a): pass
            return M()

        with patch("urllib.request.urlopen", multi_response):
            client = NotionClient()
            result = client.sync_stage_to_status("page-x", "verify")
        assert result["properties"]["Status"]["status"]["name"] == "In Review"

    def test_sync_stage_status_property_missing(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {
            "id": "page-y",
            "properties": {"Name": {"type": "title", "title": []}},
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.sync_stage_to_status("page-y", "implement")
        assert "error" in result
        assert "Status" in result["error"]

    def test_sync_stage_custom_map(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        call_count = [0]
        responses = [
            {
                "id": "page-z",
                "properties": {"State": {"type": "select", "select": {"name": "Backlog"}}},
            },
            {
                "id": "page-z",
                "properties": {"State": {"type": "select", "select": {"name": "QA"}}},
            },
        ]
        def multi_response(request, timeout=None):
            idx = call_count[0]
            call_count[0] += 1
            class M:
                def read(s):
                    return json.dumps(responses[idx]).encode("utf-8")
                def __enter__(s): return s
                def __exit__(s, *a): pass
            return M()

        with patch("urllib.request.urlopen", multi_response):
            client = NotionClient()
            result = client.sync_stage_to_status(
                "page-z", "verify",
                status_property="State",
                stage_status_map={"verify": "QA"}
            )
        assert result["properties"]["State"]["select"]["name"] == "QA"


class TestNotionMisc:
    def test_append_blocks(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {"results": [{"id": "block-1", "type": "paragraph"}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.append_blocks("page-1", [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": "StageFlow update"}}]},
            }])
        assert len(result["results"]) == 1

    def test_search_pages(self, monkeypatch):
        monkeypatch.setenv("NOTION_API_KEY", "test")
        mock = {"results": [{"id": "p1", "title": [{"text": {"content": "Login bug"}}]}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock)):
            client = NotionClient()
            result = client.search_pages("login")
        assert len(result["results"]) == 1

    def test_default_stage_status_map(self):
        assert DEFAULT_STAGE_STATUS_MAP["analyze"] == "In Progress"
        assert DEFAULT_STAGE_STATUS_MAP["verify"] == "In Review"
        assert DEFAULT_STAGE_STATUS_MAP["done"] == "Done"


class TestLoadEnvNotion:
    def test_load_env_valid(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("NOTION_API_KEY=ntn_test\nOTHER=xyz\n")
        result = _load_env(env_file)
        assert result == {"NOTION_API_KEY": "ntn_test", "OTHER": "xyz"}

    def test_load_env_missing(self, temp_dir):
        result = _load_env(temp_dir / "missing.env")
        assert result == {}

    def test_load_env_skips_comments_blanks(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text('# config\nNOTION_API_KEY="key123"\n\nDEBUG=1\n')
        result = _load_env(env_file)
        assert result == {"NOTION_API_KEY": "key123", "DEBUG": "1"}
