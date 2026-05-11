"""Tests for Linear.app integration."""

import json
import os
from unittest.mock import patch, MagicMock
import pytest

from stageflow.integrations.linear import (
    LinearClient,
    DEFAULT_STAGE_STATE_MAP,
    _load_env,
)


class TestLinearClientInit:
    def test_init_with_explicit_key(self):
        client = LinearClient(api_key="lin_api_test123")
        assert client._api_key == "lin_api_test123"

    def test_init_from_env_var(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_env_key")
        client = LinearClient()
        assert client._api_key == "lin_api_env_key"

    def test_init_from_dotenv(self, temp_dir, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        env_file = temp_dir / ".env"
        env_file.write_text('LINEAR_API_KEY="key_from_dotenv"\n')
        from stageflow.integrations import linear
        with patch.object(linear, "_load_env", return_value={"LINEAR_API_KEY": "key_from_dotenv"}):
            client = LinearClient()
            assert client._api_key == "key_from_dotenv"

    def test_init_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with patch("stageflow.integrations.linear._load_env", return_value={}):
            with pytest.raises(ValueError, match="LINEAR_API_KEY not set"):
                LinearClient()


def _mock_urlopen(data: dict, status: int = 200):
    """Helper to mock urllib.request.urlopen."""
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


class TestLinearGetIssue:
    def test_get_issue_by_id(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_issue = {
            "data": {
                "issue": {
                    "id": "abc-123",
                    "title": "Fix login bug",
                    "state": {"name": "In Progress"},
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_issue)):
            client = LinearClient()
            result = client.get_issue("abc-123")
        assert result["issue"]["title"] == "Fix login bug"

    def test_get_issue_by_identifier(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_issue = {
            "data": {
                "issueByIdentifier": {
                    "id": "uuid-1",
                    "identifier": "ENG-42",
                    "title": "Add dark mode",
                    "state": {"name": "Todo"},
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_issue)):
            client = LinearClient()
            result = client.get_issue_by_identifier("ENG-42")
        assert result["issue"]["identifier"] == "ENG-42"

    def test_get_issue_graphql_error(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {"errors": [{"message": "Issue not found"}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.get_issue("bad-id")
        assert "error" in result
        assert len(result["error"]) == 1


class TestLinearTeamStates:
    def test_get_team_states(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {
            "data": {
                "team": {
                    "id": "team-1",
                    "name": "Engineering",
                    "states": {"nodes": [
                        {"id": "s1", "name": "Todo", "type": "unstarted"},
                        {"id": "s2", "name": "In Progress", "type": "started"},
                        {"id": "s3", "name": "Done", "type": "completed"},
                    ]},
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.get_team_states("team-1")
        assert len(result["team"]["states"]["nodes"]) == 3

    def test_get_team_states_error(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {"errors": [{"message": "Team not found"}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.get_team_states("bad-team")
        assert "error" in result


class TestLinearUpdate:
    def test_update_issue_state(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {
            "data": {
                "issueUpdate": {
                    "issue": {"id": "abc-1", "state": {"name": "Done"}},
                    "success": True,
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.update_issue_state("abc-1", "state-done")
        assert result["result"]["success"] is True

    def test_update_issue_with_fields(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {
            "data": {
                "issueUpdate": {
                    "issue": {"id": "abc-2", "title": "Updated title"},
                    "success": True,
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.update_issue("abc-2", title="Updated title")
        assert result["result"]["success"] is True

    def test_update_issue_graphql_error(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {"errors": [{"message": "Permission denied"}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.update_issue_state("abc-1", "bad-state")
        assert "error" in result


class TestLinearSync:
    def test_sync_stage_to_state_success(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        call_count = [0]
        responses = [
            {  # get_issue
                "data": {
                    "issue": {
                        "id": "iss-1",
                        "team": {"id": "team-x"},
                        "state": {"name": "Todo"},
                    }
                }
            },
            {  # get_team_states
                "data": {
                    "team": {
                        "states": {"nodes": [
                            {"id": "st-in-progress", "name": "In Progress"},
                            {"id": "st-done", "name": "Done"},
                        ]},
                    }
                }
            },
            {  # update_issue_state
                "data": {
                    "issueUpdate": {
                        "issue": {"state": {"name": "In Progress"}},
                        "success": True,
                    }
                }
            },
        ]
        def multi_response(request, timeout=None):
            body = json.loads(request.data.decode("utf-8"))
            idx = call_count[0]
            call_count[0] += 1
            class MockResp:
                def read(s):
                    return json.dumps(responses[idx]).encode("utf-8")
                def __enter__(s):
                    return s
                def __exit__(s, *a):
                    pass
            return MockResp()

        with patch("urllib.request.urlopen", multi_response):
            client = LinearClient()
            result = client.sync_stage_to_state("iss-1", "implement")
        assert result["result"]["success"] is True

    def test_sync_stage_unknown_state_name(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        call_count = [0]
        responses = [
            {
                "data": {
                    "issue": {
                        "id": "iss-2",
                        "team": {"id": "team-y"},
                    }
                }
            },
            {
                "data": {
                    "team": {
                        "states": {"nodes": [
                            {"id": "st1", "name": "Backlog"},
                            {"id": "st2", "name": "Done"},
                        ]},
                    }
                }
            },
        ]
        def multi_response(request, timeout=None):
            idx = call_count[0]
            call_count[0] += 1
            class MockResp:
                def read(s):
                    return json.dumps(responses[idx]).encode("utf-8")
                def __enter__(s):
                    return s
                def __exit__(s, *a):
                    pass
            return MockResp()

        with patch("urllib.request.urlopen", multi_response):
            client = LinearClient()
            result = client.sync_stage_to_state("iss-2", "implement")
        assert "error" in result
        assert "Available:" in result["error"]

    def test_sync_stage_issue_not_found(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {"errors": [{"message": "Issue not found"}]}
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.sync_stage_to_state("bad-issue", "implement")
        assert "error" in result

    def test_sync_stage_custom_map(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        call_count = [0]
        responses = [
            {
                "data": {"issue": {"id": "iss-3", "team": {"id": "t1"}, "state": {"name": "X"}}}
            },
            {
                "data": {"team": {"states": {"nodes": [{"id": "qa", "name": "QA"}]}}}
            },
            {
                "data": {"issueUpdate": {"issue": {"state": {"name": "QA"}}, "success": True}}
            },
        ]
        def multi_response(request, timeout=None):
            idx = call_count[0]
            call_count[0] += 1
            class MockResp:
                def read(s):
                    return json.dumps(responses[idx]).encode("utf-8")
                def __enter__(s):
                    return s
                def __exit__(s, *a):
                    pass
            return MockResp()

        with patch("urllib.request.urlopen", multi_response):
            client = LinearClient()
            result = client.sync_stage_to_state(
                "iss-3", "verify", stage_state_map={"verify": "QA"}
            )
        assert result["result"]["success"] is True


class TestLinearMisc:
    def test_add_comment(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {
            "data": {
                "commentCreate": {
                    "comment": {"id": "cmt-1", "body": "StageFlow: moved to verify"},
                    "success": True,
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.add_comment("iss-1", "StageFlow: moved to verify")
        assert result["result"]["success"] is True

    def test_search_issues(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        mock_resp = {
            "data": {
                "issueSearch": {
                    "nodes": [
                        {"id": "i1", "identifier": "ENG-1", "title": "Fix auth"},
                    ]
                }
            }
        }
        with patch("urllib.request.urlopen", _mock_urlopen(mock_resp)):
            client = LinearClient()
            result = client.search_issues("auth")
        assert len(result["issues"]) == 1
        assert result["issues"][0]["identifier"] == "ENG-1"

    def test_http_error_handling(self, monkeypatch):
        import urllib.error
        monkeypatch.setenv("LINEAR_API_KEY", "test")
        def raise_error(request, timeout=None):
            raise urllib.error.HTTPError(
                "https://api.linear.app/graphql", 401, "Unauthorized",
                {}, io.BytesIO(json.dumps({"errors": [{"message": "Invalid API key"}]}).encode())
            )
        import io
        with patch("urllib.request.urlopen", raise_error):
            client = LinearClient()
            result = client.get_issue("any-id")
        assert "error" in result

    def test_default_stage_state_map_coverage(self):
        assert DEFAULT_STAGE_STATE_MAP["analyze"] == "In Progress"
        assert DEFAULT_STAGE_STATE_MAP["verify"] == "In Review"
        assert DEFAULT_STAGE_STATE_MAP["done"] == "Done"


class TestLoadEnv:
    def test_load_env_valid_file(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text('LINEAR_API_KEY=my_key\nOTHER=val\n')
        result = _load_env(env_file)
        assert result == {"LINEAR_API_KEY": "my_key", "OTHER": "val"}

    def test_load_env_missing_file(self, temp_dir):
        result = _load_env(temp_dir / "nonexistent.env")
        assert result == {}

    def test_load_env_ignores_comments_and_blanks(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text('# comment\nLINEAR_API_KEY="key"\n\nOTHER=123\n')
        result = _load_env(env_file)
        assert result == {"LINEAR_API_KEY": "key", "OTHER": "123"}

    def test_load_env_skips_malformed(self, temp_dir):
        env_file = temp_dir / ".env"
        env_file.write_text("NO_EQUALS\nKEY=val\n")
        result = _load_env(env_file)
        assert result == {"KEY": "val"}
