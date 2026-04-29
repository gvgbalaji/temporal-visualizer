"""
Temporal client service — connects to Temporal server
and triggers workflow executions.
"""

import asyncio
import json
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


def _decode_payloads(payloads):
    """Decode Temporal Payloads protobuf to Python objects."""
    if not payloads:
        return None
    try:
        items = list(payloads.payloads)
    except (AttributeError, TypeError):
        return None
    if not items:
        return None

    decoded = []
    for payload in items:
        encoding = payload.metadata.get("encoding", b"")
        if isinstance(encoding, bytes):
            encoding = encoding.decode("utf-8", errors="replace")
        data = payload.data
        if "json" in encoding.lower():
            try:
                decoded.append(json.loads(data))
                continue
            except Exception:
                pass
        try:
            decoded.append(data.decode("utf-8", errors="replace"))
        except Exception:
            decoded.append(f"<{len(data)} bytes>")

    if not decoded:
        return None
    return decoded[0] if len(decoded) == 1 else decoded


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


def get_workflow_events(workflow_id: str) -> dict:
    """
    Fetch and parse workflow history events from Temporal for replay visualization.

    Returns structured events including activity inputs/outputs.
    """
    from temporalio.client import Client
    from temporalio.api.enums.v1 import EventType

    async def _fetch():
        client = await Client.connect(TEMPORAL_HOST)
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()

        events = []
        scheduled_to_name = {}  # scheduled event_id → activity name

        async for event in handle.fetch_history_events():
            et = event.event_type

            if et == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
                attrs = event.workflow_execution_started_event_attributes
                events.append({
                    "eventId": event.event_id,
                    "type": "WorkflowExecutionStarted",
                    "input": _decode_payloads(attrs.input),
                })

            elif et == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                attrs = event.activity_task_scheduled_event_attributes
                name = attrs.activity_type.name
                scheduled_to_name[event.event_id] = name
                events.append({
                    "eventId": event.event_id,
                    "type": "ActivityTaskScheduled",
                    "activityName": name,
                    "input": _decode_payloads(attrs.input),
                })

            elif et == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
                attrs = event.activity_task_completed_event_attributes
                sched_id = attrs.scheduled_event_id
                events.append({
                    "eventId": event.event_id,
                    "type": "ActivityTaskCompleted",
                    "scheduledEventId": sched_id,
                    "activityName": scheduled_to_name.get(sched_id),
                    "output": _decode_payloads(attrs.result),
                })

            elif et == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED:
                attrs = event.activity_task_failed_event_attributes
                sched_id = attrs.scheduled_event_id
                error = ""
                if attrs.failure:
                    error = attrs.failure.message or str(attrs.failure)
                events.append({
                    "eventId": event.event_id,
                    "type": "ActivityTaskFailed",
                    "scheduledEventId": sched_id,
                    "activityName": scheduled_to_name.get(sched_id),
                    "error": error,
                })

            elif et == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
                attrs = event.workflow_execution_completed_event_attributes
                events.append({
                    "eventId": event.event_id,
                    "type": "WorkflowExecutionCompleted",
                    "output": _decode_payloads(attrs.result),
                })

            elif et == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
                attrs = event.workflow_execution_failed_event_attributes
                error = ""
                if attrs.failure:
                    error = attrs.failure.message or str(attrs.failure)
                events.append({
                    "eventId": event.event_id,
                    "type": "WorkflowExecutionFailed",
                    "error": error,
                })

        status_str = str(desc.status)
        if "." in status_str:
            status_str = status_str.split(".")[-1]

        return {
            "workflow_id": workflow_id,
            "status": status_str,
            "events": events,
        }

    try:
        return _run_async(_fetch())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch workflow events: {str(e)}")
