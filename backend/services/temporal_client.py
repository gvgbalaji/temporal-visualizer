"""
Temporal client service — connects to Temporal server
and triggers workflow executions.
"""

import asyncio
import os
import uuid
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")


def _run_async(coro):
    """Run an async coroutine from synchronous context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def trigger_workflow(
    workflow_name: str,
    task_queue: str,
    input_data: dict,
    workflow_id: str = None,
) -> dict:
    """
    Trigger a Temporal workflow execution.

    Args:
        workflow_name: The registered workflow name (e.g., "StockAnalysis")
        task_queue: The task queue to use
        input_data: The workflow input as a dict
        workflow_id: Optional custom workflow ID

    Returns:
        Dict with workflow_id and status
    """
    from temporalio.client import Client

    if not workflow_id:
        workflow_id = f"{workflow_name.lower()}-{uuid.uuid4()}"

    async def _start():
        client = await Client.connect(TEMPORAL_HOST)
        handle = await client.start_workflow(
            workflow_name,
            arg=input_data,
            id=workflow_id,
            task_queue=task_queue,
            execution_timeout=timedelta(minutes=10),
        )
        return handle.id

    try:
        wf_id = _run_async(_start())
        return {"workflow_id": wf_id, "status": "started"}
    except Exception as e:
        raise RuntimeError(f"Failed to start workflow: {str(e)}")


def get_workflow_status(workflow_id: str) -> dict:
    """
    Get the status of a running Temporal workflow.

    Args:
        workflow_id: The workflow execution ID

    Returns:
        Dict with workflow status information
    """
    from temporalio.client import Client

    async def _status():
        client = await Client.connect(TEMPORAL_HOST)
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        return {
            "workflow_id": workflow_id,
            "status": str(desc.status),
            "start_time": str(desc.start_time),
        }

    try:
        return _run_async(_status())
    except Exception as e:
        raise RuntimeError(f"Failed to get workflow status: {str(e)}")
