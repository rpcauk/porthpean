"""Test greetd framing and PAM conversation without GTK, PAM or a real login."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import socket
import struct
import threading
import unittest

BASE = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('greeter', str(BASE / 'files/porthpean-greeter'))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def request(self, message):
        self.requests.append(message)
        return next(self.replies)


def prompt(kind, text):
    return {'type': 'auth_message', 'auth_message_type': kind, 'auth_message': text}


class Greeter(unittest.TestCase):
    def test_password_then_otp_and_visible_prompt_before_start(self):
        client = FakeClient([prompt('info', 'Notice'), prompt('secret', 'Password:'),
            prompt('secret', 'Verification code:'), prompt('visible', 'Other answer:'),
            {'type': 'success'}, {'type': 'success'}])
        conversation = module.Conversation(client)
        self.assertEqual(conversation.start('ryan', 'synthetic-password'), ('secret', 'Verification code:', 'Notice'))
        self.assertFalse(any(r['type'] == 'start_session' for r in client.requests))
        self.assertEqual(conversation.answer('synthetic-otp')[0], 'visible')
        self.assertEqual(conversation.answer('visible answer')[0], 'started')
        self.assertEqual(client.requests[-1]['cmd'], ['/usr/bin/niri-session'])
        self.assertEqual([r.get('response') for r in client.requests if r['type'] == 'post_auth_message_response'],
                         [None, 'synthetic-password', 'synthetic-otp', 'visible answer'])

    def test_unknown_reply_cannot_start_session(self):
        client = FakeClient([{'type': 'unexpected'}])
        with self.assertRaises(module.LoginError):
            module.Conversation(client).start('ryan', 'synthetic')
        self.assertEqual(len(client.requests), 1)

    def test_fragmented_socket_response_and_authentication_failure(self):
        client_socket, server_socket = socket.socketpair()
        received = []
        errors = []
        def server():
            try:
                header = server_socket.recv(4)
                size, = struct.unpack('=I', header)
                body = bytearray()
                while len(body) < size:
                    body.extend(server_socket.recv(size - len(body)))
                received.append(json.loads(body))
                payload = json.dumps({'type': 'error', 'error_type': 'auth_error', 'description': 'private PAM detail'}).encode()
                for byte in struct.pack('=I', len(payload)) + payload:
                    server_socket.sendall(bytes([byte]))
            except Exception as error:
                errors.append(error)
            finally:
                server_socket.close()
        thread = threading.Thread(target=server)
        thread.start()
        try:
            with self.assertRaisesRegex(module.LoginError, '^Authentication failed. Try again.$'):
                module.GreetdClient(client_socket).request({'type': 'create_session', 'username': 'ryan'})
        finally:
            client_socket.close()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(received, [{'type': 'create_session', 'username': 'ryan'}])

    def test_cancel_closes_socket_and_never_starts_a_session(self):
        class Connection:
            closed = False
            def close(self): self.closed = True
        connection = Connection()
        client = module.GreetdClient(connection)
        requests = []
        client.request = lambda message: requests.append(message)
        client.cancel()
        self.assertTrue(connection.closed)
        self.assertEqual(requests, [{'type': 'cancel_session'}])
