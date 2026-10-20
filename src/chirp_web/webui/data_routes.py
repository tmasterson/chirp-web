"""Memory editing, image I/O, and transfer job routes."""

from fastapi import Query
from fastapi.responses import Response

from chirp_web.webui.service import WebServiceError


def register_data_routes(app, session, transfers, log):
    """Register radio image and memory API routes on an application."""
    from chirp_web.webui.api import (
            BankMembershipRequest, BankUpdate, DownloadRequest,
            ImportImageRequest, MemoryArrange, MemoryBulkUpdate,
            MemoryCopy, MemoryDelete, MemoryInsert, MemoryMove,
            MemoryPaste, MemoryQuery, MemoryScope, MemoryUpdate,
            RawMemoryRequest, SettingsUpdate, UploadRequest)

    @app.get('/api/memories')
    def list_memories(start: int | None = Query(default=None, ge=0),
                      limit: int = Query(default=50, ge=1, le=200),
                      search: str = Query(default='', max_length=200),
                      sort: str = Query(
                          default='number',
                          pattern='^(number|name|freq|mode|duplex)$'),
                      direction: str = Query(
                          default='asc', pattern='^(asc|desc)$'),
                      hide_empty: bool = False):
        details = session.describe()
        low, high = details['memory_bounds']
        filtered = bool(search or sort != 'number' or direction != 'asc' or
                        hide_empty)
        return session.memories(
                (0 if filtered else low) if start is None else start,
                limit, search, sort, direction, hide_empty)

    @app.post('/api/memories/query')
    def query_memories(payload: MemoryQuery):
        return session.memories(
                payload.start, payload.limit, sort=payload.sort,
                direction=payload.direction, hide_empty=payload.hide_empty,
                filters=[item.model_dump() for item in payload.filters],
                match=payload.match)

    @app.post('/api/memories/delete')
    def delete_memories(payload: MemoryDelete):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.delete_memories(numbers, payload.shift)

    @app.post('/api/memories/move')
    def move_memories(payload: MemoryMove):
        return session.move_memories(payload.numbers, payload.direction)

    @app.post('/api/memories/insert')
    def insert_memory(payload: MemoryInsert):
        return session.insert_memory_row(payload.number)

    @app.post('/api/memories/copy')
    def copy_memories(payload: MemoryCopy):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.copy_memories(numbers, cut=payload.cut)

    @app.post('/api/memories/paste')
    def paste_memories(payload: MemoryPaste):
        return session.paste_memories(
                payload.clipboard_id, payload.start, payload.overwrite)

    @app.post('/api/memories/raw')
    def raw_memories(payload: RawMemoryRequest):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return {'memories': session.raw_memories(numbers)}

    @app.post('/api/memories/raw-diff')
    def raw_memory_diff(payload: RawMemoryRequest):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.raw_memory_diff(numbers)

    @app.patch('/api/memories/bulk')
    def bulk_update_memories(payload: MemoryBulkUpdate):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        changes = payload.changes.model_dump(exclude_unset=True)
        extra_changes = changes.pop('extra_changes', None)
        if any(value is None for value in changes.values()):
            raise WebServiceError(
                    'Memory field values cannot be null.', 422)
        if extra_changes is None and not changes:
            raise WebServiceError('Provide at least one memory field.', 422)
        return session.bulk_update_memories(
                numbers, changes, extra_changes)

    @app.post('/api/memories/arrange')
    def arrange_memories(payload: MemoryArrange):
        return session.arrange_memories(
                payload.numbers, payload.operation,
                payload.field, payload.direction)

    @app.patch('/api/memories/{number}')
    def update_memory(number: str, payload: MemoryUpdate):
        number = int(number) if number.isdecimal() else number
        values = payload.model_dump(exclude_unset=True)
        extra_changes = values.pop('extra_changes', None)
        if any(value is None for value in values.values()):
            raise WebServiceError(
                    'Memory field values cannot be null.', 422)
        if extra_changes is None and not values:
            raise WebServiceError('Provide at least one memory field.', 422)
        return session.update_memory(number, values, extra_changes)

    @app.get('/api/banks')
    def list_banks():
        return session.bank_models()

    @app.patch('/api/memories/{number}/banks')
    def update_memory_bank_membership(
            number: str, payload: BankMembershipRequest):
        number = int(number) if number.isdecimal() else number
        return session.update_memory_bank_membership(
                number,
                payload.model,
                payload.bank_index,
                payload.enabled,
        )

    @app.patch('/api/banks')
    def update_bank(payload: BankUpdate):
        return session.update_bank(
                payload.model, payload.bank_index, payload.name,
                payload.memory_number, payload.index)

    @app.get('/api/settings')
    def get_settings():
        return session.radio_settings()

    @app.patch('/api/settings')
    def update_settings(payload: SettingsUpdate):
        return session.update_settings(
                [change.model_dump() for change in payload.changes],
                confirm_warnings=payload.confirm_warnings)

    @app.post('/api/session/save')
    def save_image(preserve_dirty: bool = False):
        try:
            return session.save_image(mark_clean=not preserve_dirty)
        except WebServiceError:
            raise
        except Exception as exc:
            log.exception('Unable to save radio image')
            raise WebServiceError(
                    'The radio driver could not save this image.',
                    500) from exc

    @app.get('/api/session/export.csv')
    def export_csv():
        return Response(
                session.export_csv(),
                media_type='text/csv',
                headers={'Content-Disposition':
                         'attachment; filename="channels.csv"'})

    @app.post('/api/session/export.csv')
    def export_scoped_csv(payload: MemoryScope):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return Response(
                session.export_csv(
                    payload.scope, numbers,
                    [item.model_dump() for item in payload.filters],
                    payload.match, payload.search, payload.sort,
                    payload.direction, payload.hide_empty),
                media_type='text/csv',
                headers={'Content-Disposition':
                         'attachment; filename="channels.csv"'})

    @app.post('/api/session/print')
    def print_memories(payload: MemoryScope):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.print_rows(
                payload.scope, numbers,
                [item.model_dump() for item in payload.filters],
                payload.match, payload.search, payload.sort,
                payload.direction, payload.hide_empty)

    @app.post('/api/session/import')
    def import_image(payload: ImportImageRequest):
        try:
            return session.import_image_memories(
                    payload.filename, payload.data_base64,
                    payload.placement, payload.destination_start)
        except WebServiceError:
            raise
        except Exception as exc:
            log.exception('Unable to merge memories from uploaded image')
            raise WebServiceError(
                    'The selected file could not be read as a radio image.',
                    422) from exc

    @app.post('/api/transfers/download')
    def download_radio(payload: DownloadRequest):
        return transfers.start(
                'download',
                payload.radio_id,
                payload.port,
                confirm_replace=payload.confirm_replace,
                confirm_prompts=payload.confirm_prompts)

    @app.post('/api/transfers/upload')
    def upload_radio(payload: UploadRequest):
        return transfers.start(
                'upload', '', payload.port, confirm=payload.confirm,
                confirm_prompts=payload.confirm_prompts)

    @app.get('/api/transfers/{job_id}')
    def transfer_status(job_id: str):
        return transfers.get(job_id)

    @app.delete('/api/transfers/{job_id}')
    def cancel_transfer(job_id: str):
        return transfers.cancel(job_id)
