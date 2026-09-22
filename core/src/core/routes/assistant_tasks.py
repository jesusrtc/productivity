"""Task edits within the standard Assistant document model."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool
from lab import assistant_tasks as tasks
from core.routes.assistant import _require_root

router = APIRouter(prefix='/api/assistant')


class DocumentTaskChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str
    expected: str
    task_id: str | None = None
    values: dict = {}
    delete: StrictBool = False


@router.post('/document-task')
def change_task(change: DocumentTaskChange, request: Request):
    root = _require_root(request)
    try:
        if change.delete and not change.task_id:
            raise ValueError('Select a task to delete')
        return tasks.change(root, change.document_id, change.values, task_id=change.task_id,
                            expected=change.expected, delete=change.delete)
    except (OSError, ValueError) as exc:
        raise HTTPException(409 if 'changed elsewhere' in str(exc) else 400, str(exc)) from exc


@router.post('/document-task/repeat')
def repeat_task(change: DocumentTaskChange, request: Request):
    root = _require_root(request)
    try:
        return tasks.repeat(root,change.document_id,change.task_id,expected=change.expected)
    except (OSError,ValueError) as exc:
        raise HTTPException(409 if 'changed elsewhere' in str(exc) else 400,str(exc)) from exc
