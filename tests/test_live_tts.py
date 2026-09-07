import asyncio
import json
import os
import unittest
from contextlib import asynccontextmanager

os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")

import app
from deepgram.core.api_error import ApiError
from deepgram.speak.v1.types import SpeakV1Metadata
from fastapi.testclient import TestClient


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.responses = asyncio.Queue()

    async def send_text(self, message):
        self.calls.append(("Speak", message.text))
        await self.responses.put(b"Speak")

    async def send_flush(self):
        self.calls.append(("Flush",))
        await self.responses.put(b"Flush")

    async def send_clear(self):
        self.calls.append(("Clear",))
        await self.responses.put(b"Clear")

    async def send_close(self):
        self.calls.append(("Close",))
        await self.responses.put(b"Close")

    async def __aiter__(self):
        while True:
            yield await self.responses.get()


class LiveTtsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.token = self.client.get("/api/session").json()["token"]
        self.original_connect = app.deepgram.speak.v1.connect

    def tearDown(self):
        app.deepgram.speak.v1.connect = self.original_connect

    def connect(self, path="/api/live-text-to-speech"):
        return self.client.websocket_connect(
            path, subprotocols=[f"access_token.{self.token}"]
        )

    def test_translates_controls_and_forwards_container(self):
        connection = FakeConnection()
        connect_options = None

        @asynccontextmanager
        async def connect(**kwargs):
            nonlocal connect_options
            connect_options = kwargs
            yield connection

        app.deepgram.speak.v1.connect = connect

        with self.connect(
            "/api/live-text-to-speech?model=aura-asteria-en&encoding=linear16"
            "&sample_rate=48000&container=none"
        ) as websocket:
            for payload, expected in [
                ('{"type":"Speak","text":"hello"}', b"Speak"),
                ('{"type":"Flush"}', b"Flush"),
                ('{"type":"Clear"}', b"Clear"),
                ('{"type":"Close"}', b"Close"),
            ]:
                websocket.send_text(payload)
                self.assertEqual(websocket.receive_bytes(), expected)

        self.assertEqual(
            connect_options,
            {
                "model": "aura-asteria-en",
                "encoding": "linear16",
                "sample_rate": 48000,
                "request_options": {
                    "additional_query_parameters": {"container": "none"}
                },
            },
        )
        self.assertEqual(
            connection.calls,
            [("Speak", "hello"), ("Flush",), ("Clear",), ("Close",)],
        )

    def test_forwards_sdk_metadata_as_json(self):
        metadata = SpeakV1Metadata(
            request_id="request-id",
            model_name="aura",
            model_version="1",
            model_uuid="model-id",
        )

        class MetadataConnection:
            async def __aiter__(self):
                yield metadata

        @asynccontextmanager
        async def connect(**kwargs):
            yield MetadataConnection()

        app.deepgram.speak.v1.connect = connect

        with self.connect() as websocket:
            self.assertEqual(
                json.loads(websocket.receive_text()), metadata.model_dump(mode="json")
            )

    def test_redacts_api_error_details_from_browser(self):
        @asynccontextmanager
        async def connect(**kwargs):
            raise ApiError(
                status_code=400,
                headers={"Authorization": "Token browser-triggerable-secret"},
                body="bad request",
            )
            yield

        app.deepgram.speak.v1.connect = connect

        with self.connect() as websocket:
            error = json.loads(websocket.receive_text())

        self.assertEqual(
            error,
            {
                "type": "Error",
                "description": "Deepgram rejected the connection (HTTP 400)",
                "code": "CONNECTION_FAILED",
            },
        )
        self.assertNotIn("browser-triggerable-secret", str(error))
