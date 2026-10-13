"""
Qastroute AI - Server-Sent Events (SSE) Streaming Engine.
Codestral-optimized token streaming for OpenAI and Anthropic dual protocols.
"""

import asyncio
import json
import time
from typing import AsyncGenerator

async def stream_openai_chunks(
    full_text: str,
    model: str,
    request_id: str,
    chunk_size: int = 4
) -> AsyncGenerator[str, None]:
    """
    Simulates / yields OpenAI-compatible SSE chunks for streaming responses.
    Format: data: {"choices": [{"delta": {"content": "..."}}]}
    Followed by data: [DONE]
    """
    words = full_text.split(" ")
    created_ts = int(time.time())

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        delta_text = " ".join(chunk_words)
        if i + chunk_size < len(words):
            delta_text += " "

        event = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": delta_text},
                    "finish_reason": None
                }
            ]
        }
        yield f"data: {json.dumps(event)}\n\n"
        await asyncio.sleep(0.01)

    # Final completion chunk
    final_event = {
        "id": f"chatcmpl-{request_id}",
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


async def stream_anthropic_events(
    full_text: str,
    model: str,
    request_id: str,
    chunk_size: int = 4
) -> AsyncGenerator[str, None]:
    """
    Yields Anthropic-compatible SSE events:
    message_start -> content_block_start -> content_block_delta -> content_block_stop -> message_stop
    """
    msg_id = f"msg_{request_id}"

    # 1. message_start
    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None}})}\n\n"

    # 2. content_block_start
    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

    words = full_text.split(" ")
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        delta_text = " ".join(chunk_words)
        if i + chunk_size < len(words):
            delta_text += " "

        delta_payload = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": delta_text}
        }
        yield f"event: content_block_delta\ndata: {json.dumps(delta_payload)}\n\n"
        await asyncio.sleep(0.01)

    # 3. content_block_stop & message_delta & message_stop
    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}})}\n\n"
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
