"""Demo script for the Email Reply Monitoring Agent."""

from datetime import datetime, timezone

from agents.email_reply_agent import EmailReplyMonitoringAgent
from models.task import EmailThread
from backend.mock_data import get_sample_threads


def print_result(thread: EmailThread, result) -> None:
    """Print an AgentResult in a readable format."""
    print(f"\nThread: {thread.thread_id}")
    print(f"  Messages: {len(thread.messages)}")
    if thread.messages:
        last = thread.messages[-1]
        print(f"  Last sender: {last.sender}")
    print(f"  Data: {result.data}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Requires approval: {result.requires_approval}")
    print(f"  Reasoning: {result.reasoning}")


def main() -> None:
    """Run sample email threads through the monitoring agent."""
    now = datetime.now(timezone.utc)
    agent = EmailReplyMonitoringAgent()

    for thread in get_sample_threads(reference_time=now):
        result = agent.execute(thread, current_time=now)
        print_result(thread, result)


if __name__ == "__main__":
    print("Email Reply Monitoring Agent — Demo")
    print("=" * 40)
    main()
