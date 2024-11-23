import asyncio
import json
import base64
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_receive_from_openai():
    """Test the receive_from_openai function."""

    # Mock WebSocket connection
    openai_ws = AsyncMock()

    # Mock simulated OpenAI messages
    simulated_responses = [
        # Valid response
        {
            "type": "response.audio.delta",
            "delta": base64.b64encode(b"FakeAudioData").decode("utf-8"),
        },
        # Invalid response (missing 'delta')
        {
            "type": "response.audio.delta",
        },
        # Non-audio response
        {
            "type": "response.done",
            "message": "This is a non-audio response.",
        },
    ]

    # Simulate receiving responses from OpenAI WebSocket
    async def mock_receive():
        for response in simulated_responses:
            yield json.dumps(response)

    openai_ws.__aiter__.side_effect = mock_receive

    # Stream SID for the Twilio connection
    stream_sid = "testStream123"

    # Mock WebSocket object for sending responses to Twilio
    mock_websocket = AsyncMock()

    async def receive_from_openai():
        """Process responses from OpenAI and forward to Twilio."""
        nonlocal stream_sid
        try:
            async for openai_message in openai_ws:
                response = json.loads(openai_message)
                print(f"Received from OpenAI: {response}")

                if response.get("type") == "response.audio.delta" and "delta" in response:
                    try:
                        # Validate OpenAI audio delta
                        audio_bytes = base64.b64decode(response["delta"])
                        print(f"Decoded OpenAI audio delta successfully: {len(audio_bytes)} bytes")

                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": response["delta"]},
                            "from_openai": True
                        }
                        await mock_websocket.send_json(audio_delta)
                        print(f"Sent audio response to Twilio: {audio_delta}")
                    except Exception as e:
                        print(f"Error decoding or forwarding OpenAI audio delta: {e}")
                else:
                    print(f"Ignored non-audio response from OpenAI: {response}")
        except Exception as e:
            print(f"Error receiving from OpenAI: {e}")

    # Run the function
    await receive_from_openai()

    # Verify WebSocket sends
    mock_websocket.send_json.assert_any_call({
        "event": "media",
        "streamSid": "testStream123",
        "media": {"payload": simulated_responses[0]["delta"]},
        "from_openai": True
    })

    # Ensure invalid messages are ignored
    assert mock_websocket.send_json.call_count == 1  # Only the valid response is forwarded
