from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from test_schema_v5 import STRICT_CONTROLLER_ENV, run_without_receipt
from test_workctl import file_tree_snapshot, run_workctl

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "plugins" / "work-governance" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

frontier_module: Any = importlib.import_module("workctl_modules.frontier")
build_frontier_draft = frontier_module.build_frontier_draft
FrontierError = frontier_module.FrontierError


def test_frontier_draft_projects_questions_and_agent_facts() -> None:
    """Decision-frontier drafts expose user-owned choices without creating authority."""
    payload = build_frontier_draft(
        {
            "goal_anchor": "Ship the 1.4.0 candidate without activating it.",
            "blocked_targets": ["task:T-001", "route"],
            "facts": [
                {
                    "summary": "The active source version is still 1.3.0.",
                    "source_ref": "project:plugin.json",
                }
            ],
            "agent_unknowns": [
                {
                    "summary": "Exact test split still needs source inspection.",
                    "next_probe": "Inspect tests before editing.",
                }
            ],
            "questions": [
                {
                    "question": "Should the first slice preserve CLI compatibility?",
                    "recommended_answer": "Yes, add new read-only commands only.",
                    "reason": "It protects existing 1.3.0 workflows.",
                }
            ],
        },
        manifest_sha256="0" * 64,
    )

    questions = cast(list[dict[str, object]], payload["questions"])
    assert payload["status"] == "FRONTIER_DRAFTED"
    assert payload["user_intervention"] == "required"
    assert payload["blocked_targets"] == ["task:T-001", "route"]
    assert questions[0]["id"] == "D-001"
    assert questions[0]["blocks"] == ["task:T-001", "route"]
    assert len(cast(str, payload["frontier_sha256"])) == 64


def test_frontier_draft_can_route_agent_owned_unknowns_without_user_question() -> None:
    """Agent-owned unknowns stay exploratory and do not force user intervention."""
    payload = build_frontier_draft(
        {
            "goal_anchor": "Find the next local evidence source.",
            "agent_owned": [
                {
                    "summary": "Controller command placement is discoverable locally.",
                    "next_probe": "Inspect the parser and command modules.",
                }
            ],
        },
        manifest_sha256="1" * 64,
    )

    assert payload["user_intervention"] == "not_required"
    assert payload["questions"] == []
    assert "Explore" in cast(str, payload["next_action"])


def test_frontier_rejects_empty_or_model_owned_questions() -> None:
    """A frontier needs a real unresolved target and cannot ask model-owned facts."""
    with pytest.raises(FrontierError, match="FRONTIER_EMPTY"):
        build_frontier_draft(
            {"goal_anchor": "Empty frontier."},
            manifest_sha256="2" * 64,
        )
    with pytest.raises(FrontierError, match="FRONTIER_QUESTION_OWNER_MUST_BE_USER"):
        build_frontier_draft(
            {
                "goal_anchor": "Bad owner.",
                "questions": [
                    {
                        "owner": "agent",
                        "question": "What file contains the parser?",
                        "recommended_answer": "Inspect locally.",
                        "reason": "Discoverable from source.",
                    }
                ],
            },
            manifest_sha256="3" * 64,
        )


def test_frontier_draft_command_is_read_only(tmp_path: Path) -> None:
    """The command drafts choices without creating Plan authority or runtime state."""
    run_workctl(tmp_path, "layout", "migrate", env=STRICT_CONTROLLER_ENV)
    before = file_tree_snapshot(tmp_path / ".work-governance")

    result = run_without_receipt(
        tmp_path,
        "frontier",
        "draft",
        "--stdin",
        input_text=json.dumps(
            {
                "goal_anchor": "Choose the smallest 1.4.0 implementation slice.",
                "blocked_targets": ["task:T-001"],
                "questions": [
                    {
                        "question": "Should 1.4.0 stay read-only before activation?",
                        "recommended_answer": "Yes, ship candidate commands first.",
                        "reason": "It keeps the live 1.3.0 plugin unaffected.",
                    }
                ],
            }
        ),
    )

    payload = cast(dict[str, object], json.loads(result.stdout))
    questions = cast(list[dict[str, object]], payload["questions"])
    assert result.returncode == 0
    assert payload["status"] == "FRONTIER_DRAFTED"
    assert questions[0]["recommended_answer"] == "Yes, ship candidate commands first."
    assert not (tmp_path / ".work-governance" / "_Plan").exists()
    assert file_tree_snapshot(tmp_path / ".work-governance") == before
