"""Linear.app GraphQL API integration for StageFlow issue syncing."""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from pathlib import Path

LINEAR_API_URL = "https://api.linear.app/graphql"

DEFAULT_STAGE_STATE_MAP: Dict[str, str] = {
    "pick": "Triage",
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
    """Load key=value pairs from a .env file."""
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


class LinearClient:
    def __init__(self, api_key: Optional[str] = None):
        self._api_key: str = api_key or os.environ.get(
            "LINEAR_API_KEY"
        ) or _load_env().get("LINEAR_API_KEY") or ""
        if not self._api_key:
            raise ValueError(
                "LINEAR_API_KEY not set. Pass api_key parameter, "
                "set LINEAR_API_KEY environment variable, or add to .env file."
            )

    def _query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against the Linear API."""
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        req = urllib.request.Request(
            LINEAR_API_URL,
            data=payload,
            headers={
                "Authorization": self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode("utf-8"))

    def get_issue(self, issue_identifier: str) -> Dict[str, Any]:
        """Fetch an issue by ID (UUID) or key (e.g. 'TEAM-42')."""
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                title
                description
                identifier
                state { id name type }
                team { id name key }
                url
                createdAt
                updatedAt
            }
        }
        """
        result = self._query(query, {"id": issue_identifier})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"issue": result.get("data", {}).get("issue")}

    def get_issue_by_identifier(self, identifier: str) -> Dict[str, Any]:
        """Fetch an issue by its human-readable identifier (e.g., 'ENG-123')."""
        query = """
        query GetIssueByIdentifier($identifier: String!) {
            issueByIdentifier(identifier: $identifier) {
                id
                title
                description
                identifier
                state { id name type }
                team { id name key }
                url
                createdAt
                updatedAt
            }
        }
        """
        result = self._query(query, {"identifier": identifier})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"issue": result.get("data", {}).get("issueByIdentifier")}

    def get_team_states(self, team_id: str) -> Dict[str, Any]:
        """Fetch workflow states for a team."""
        query = """
        query GetTeamStates($teamId: String!) {
            team(id: $teamId) {
                id
                name
                states { nodes { id name type } }
            }
        }
        """
        result = self._query(query, {"teamId": team_id})
        if "errors" in result:
            return {"error": result["errors"]}
        team = result.get("data", {}).get("team")
        return {"team": team}

    def update_issue_state(
        self,
        issue_id: str,
        state_id: str,
    ) -> Dict[str, Any]:
        """Update an issue's workflow state."""
        query = """
        mutation UpdateIssue($issueId: String!, $stateId: String!) {
            issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                issue { id identifier title state { id name } }
                success
            }
        }
        """
        result = self._query(query, {"issueId": issue_id, "stateId": state_id})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"result": result.get("data", {}).get("issueUpdate")}

    def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        state_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update issue fields."""
        input_vars: Dict[str, str] = {}
        if title is not None:
            input_vars["title"] = title
        if description is not None:
            input_vars["description"] = description
        if state_id is not None:
            input_vars["stateId"] = state_id

        query = """
        mutation UpdateIssue($issueId: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $issueId, input: $input) {
                issue { id identifier title state { id name } }
                success
            }
        }
        """
        result = self._query(query, {"issueId": issue_id, "input": input_vars})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"result": result.get("data", {}).get("issueUpdate")}

    def sync_stage_to_state(
        self,
        issue_id: str,
        stage_name: str,
        stage_state_map: Optional[Dict[str, str]] = None,
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync a StageFlow stage to a Linear issue state.

        Maps the stage name to a Linear workflow state name using
        stage_state_map, then finds the matching state ID for the
        issue's team and applies the transition.
        """
        state_name = (stage_state_map or DEFAULT_STAGE_STATE_MAP).get(
            stage_name, "In Progress"
        )

        issue_data = self.get_issue(issue_id)
        if "error" in issue_data:
            return issue_data
        issue = issue_data.get("issue")
        if not issue:
            return {"error": f"Issue '{issue_id}' not found"}

        team = issue.get("team") or {}
        team_id_to_use = team_id or team.get("id")
        if not team_id_to_use:
            return {"error": "No team ID available to look up states"}

        states_result = self.get_team_states(team_id_to_use)
        if "error" in states_result:
            return states_result

        states = states_result.get("team", {}).get("states", {}).get("nodes", [])
        target_state = next(
            (s for s in states if s["name"].lower() == state_name.lower()), None
        )

        if not target_state:
            available = [s["name"] for s in states]
            return {
                "error": (
                    f"No state '{state_name}' found in team workflow. "
                    f"Available: {', '.join(available)}"
                )
            }

        return self.update_issue_state(issue_id, target_state["id"])

    def add_comment(
        self,
        issue_id: str,
        body: str,
    ) -> Dict[str, Any]:
        """Add a comment to an issue."""
        query = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                comment { id body createdAt }
                success
            }
        }
        """
        result = self._query(query, {"issueId": issue_id, "body": body})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"result": result.get("data", {}).get("commentCreate")}

    def search_issues(self, query_str: str, limit: int = 10) -> Dict[str, Any]:
        """Search issues by title/description text."""
        query = """
        query SearchIssues($query: String!, $limit: Int!) {
            issueSearch(query: $query, first: $limit) {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                }
            }
        }
        """
        result = self._query(query, {"query": query_str, "limit": limit})
        if "errors" in result:
            return {"error": result["errors"]}
        return {"issues": result.get("data", {}).get("issueSearch", {}).get("nodes", [])}
