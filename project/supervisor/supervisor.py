"""Supervisor orchestrates agent routing, approval policy, and audit logging."""

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from supervisor.agent_registry import get_agent
from supervisor.approval_policy import requires_human_approval
from supervisor.audit_log import log_execution


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _serialize_task_input(task: Any) -> dict[str, Any] | None:
    """Best-effort JSON-safe snapshot of the task input for audit logging."""
    if task is None:
        return None
    if isinstance(task, dict):
        return _json_safe(task)
    dump = getattr(task, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return _json_safe(dump())
    if is_dataclass(task) and not isinstance(task, type):
        return _json_safe(asdict(task))
    as_dict = getattr(task, "dict", None)
    if callable(as_dict):
        return _json_safe(as_dict())
    return {"type": type(task).__name__, "repr": repr(task)[:500]}


class Supervisor:
    """Routes tasks to registered agents and aggregates their results."""

    def execute_task(self, agent_name: str, task: Any, task_id: str) -> dict:
        """Run a single task through the named agent.

        Args:
            agent_name: Registered agent identifier.
            task: Task payload passed to the agent's ``execute`` method.
            task_id: Unique identifier for audit logging.

        Returns:
            Dict with agent name, task id, audit entry id, raw result, and approval flag.
        """
        agent = get_agent(agent_name)
        result = agent.execute(task)
        final_approval_needed = requires_human_approval(agent_name, result)
        entry_id = log_execution(
            agent_name,
            task_id,
            result,
            final_approval_needed,
            input_data=_serialize_task_input(task),
        )

        return {
            "agent_name": agent_name,
            "task_id": task_id,
            "entry_id": entry_id,
            "result": result,
            "final_approval_needed": final_approval_needed,
        }

    def run_batch(
        self,
        agent_name: str,
        tasks: list[Any],
        task_ids: list[str],
    ) -> dict:
        """Run multiple tasks through the same agent and return an aggregated summary.

        Args:
            agent_name: Registered agent identifier.
            tasks: List of task payloads.
            task_ids: Parallel list of task identifiers.

        Returns:
            Aggregated summary with counts and individual execution results.

        Raises:
            ValueError: If ``tasks`` and ``task_ids`` differ in length.
        """
        if len(tasks) != len(task_ids):
            raise ValueError("tasks and task_ids must have the same length")

        results = [
            self.execute_task(agent_name, task, task_id)
            for task, task_id in zip(tasks, task_ids)
        ]
        needs_approval_count = sum(
            1 for entry in results if entry["final_approval_needed"]
        )

        return {
            "total": len(results),
            "needs_approval_count": needs_approval_count,
            "auto_processed_count": len(results) - needs_approval_count,
            "results": results,
        }
