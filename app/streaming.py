"""
Qastroute AI - Real-Time Server-Sent Events (SSE) Streaming Engine.
Forwards upstream token chunks as they arrive from LLM providers without full-body buffering.
Supports native OpenAI and Anthropic dual protocols with connection cleanup on client disconnect.
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Union

async def stream_openai_sse(
    token_generator: AsyncGenerator[str, None],
    model: str,
    request_id: str
) -> AsyncGenerator[str, None]:
    """
    Consumes asynchronous tokens from upstream adapter and yields OpenAI-compatible SSE chunks in real time.
    Format: data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"..."}}]}
    """
    created_ts = int(time.time())
    chunk_id = f"chatcmpl-{request_id}"

    try:
        async for token in token_generator:
            if not token:
                continue
            event = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": token},
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(event)}\n\n"

        # Final stop chunk
        final_event = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(final_event)}\n\n"
        yield "data: [DONE]\n\n"

    except asyncio.CancelledError:
        # Client disconnected; cleanup cleanly
        return
    except Exception as e:
        err_event = {
            "error": {
                "message": f"Stream error: {str(e)}",
                "type": "streaming_error"
            }
        }
        yield f"data: {json.dumps(err_event)}\n\n"
        yield "data: [DONE]\n\n"


async def stream_anthropic_sse(
    token_generator: AsyncGenerator[str, None],
    model: str,
    request_id: str
) -> AsyncGenerator[str, None]:
    """
    Consumes asynchronous tokens from upstream adapter and yields Anthropic Messages SSE events in real time.
    Sequence: message_start -> content_block_start -> content_block_delta ... -> content_block_stop -> message_stop
    """
    msg_id = f"msg_{request_id}"

    try:
        # 1. message_start
        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None}})}\n\n"

        # 2. content_block_start
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

        # 3. Stream content_block_delta chunks
        async for token in token_generator:
            if not token:
                continue
            delta_payload = {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": token}
            }
            yield f"event: content_block_delta\ndata: {json.dumps(delta_payload)}\n\n"

        # 4. content_block_stop & message_delta & message_stop
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}})}\n\n"
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

    except asyncio.CancelledError:
        return
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(e)}})}\n\n"


# Backward compatibility helpers for string inputs in legacy tests
async def _text_to_async_gen(text: str) -> AsyncGenerator[str, None]:
    words = text.split(" ")
    for i, w in enumerate(words):
        yield w + (" " if i < len(words) - 1 else "")
        await asyncio.sleep(0.005)

async def stream_openai_chunks(full_text_or_gen: Union[str, AsyncGenerator[str, None]], model: str, request_id: str):
    if isinstance(full_text_or_gen, str):
        gen = _text_to_async_gen(full_text_or_gen)
    else:
        gen = full_text_or_gen
    async for chunk in stream_openai_sse(gen, model, request_id):
        yield chunk

async def stream_anthropic_events(full_text_or_gen: Union[str, AsyncGenerator[str, None]], model: str, request_id: str):
    if isinstance(full_text_or_gen, str):
        gen = _text_to_async_gen(full_text_or_gen)
    else:
        gen = full_text_or_gen
    async for chunk in stream_anthropic_sse(gen, model, request_id):
        yield chunk
