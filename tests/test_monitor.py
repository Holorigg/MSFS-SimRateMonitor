import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_settings import Settings, load_settings, save_settings
from sim_rate import SimRateWorker, valid_rate


class FakeConnection:
    def __init__(self, auto_connect=False, rate=1.0, ignore_set=False, ignore_all=False):
        self.rate = rate
        self.ignore_set = ignore_set
        self.ignore_all = ignore_all
        self.quit = 0
        self.sent = []
        self.closed = False

    def connect(self):
        pass

    def map_to_sim_event(self, name):
        return name

    def send_event(self, event, value):
        self.sent.append((event, value.value))
        if not self.ignore_all:
            if event == b"SIM_RATE_INCR":
                self.rate *= 2
            elif event == b"SIM_RATE_DECR":
                self.rate /= 2
            elif event == b"SIM_RATE_SET" and not self.ignore_set:
                self.rate = float(value.value)
        return True

    def exit(self):
        self.closed = True


class FakeRequests:
    def __init__(self, connection, **kwargs):
        self.connection = connection

    def get(self, name):
        assert name == "SIMULATION_RATE"
        return self.connection.rate


class SettingsTests(unittest.TestCase):
    def test_round_trip_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "settings.json"
            settings = Settings(True, "m", -1200, 250)
            save_settings(settings, path)
            self.assertEqual(settings, load_settings(path))
            path.write_text(json.dumps({"start_minimized": "false", "overlay_size": "broken",
                                        "overlay_x": True, "overlay_y": 1000000}))
            self.assertEqual(Settings(), load_settings(path))
            path.write_text("corrupt json")
            self.assertEqual(Settings(), load_settings(path))
            path.write_text("null")
            self.assertEqual(Settings(), load_settings(path))


class RateTests(unittest.TestCase):
    def setUp(self):
        self.messages = queue.Queue()
        self.worker = SimRateWorker(self.messages)
        self.connection = FakeConnection()
        self.worker.connection = self.connection
        self.worker._connected = True

    def test_plus_minus_and_normal_change_the_reported_rate(self):
        for command, expected in (("increase", 2), ("increase", 4),
                                  ("decrease", 2), ("normal", 1)):
            self.assertTrue(self.worker.submit(command))
            self.worker._process_command()
            self.assertEqual(self.connection.rate, expected)
        self.worker._verify_reset(self.connection.rate)
        self.assertTrue(self.worker.controls_available)
        self.assertEqual(self.connection.sent[-1], (b"SIM_RATE_SET", 1))

    def test_normal_falls_back_in_both_directions_when_set_is_ignored(self):
        for rate in (8.0, 0.25):
            with self.subTest(rate=rate):
                self.connection.rate = rate
                self.connection.ignore_set = True
                self.worker.submit("normal")
                self.worker._process_command()
                self.assertFalse(self.worker.controls_available)
                for _ in range(6):
                    self.worker._reset_next_step = 0
                    self.worker._verify_reset(self.connection.rate)
                self.assertEqual(self.connection.rate, 1.0)
                self.assertTrue(self.worker.controls_available)

    def test_normal_stops_with_an_error_when_simulator_ignores_every_event(self):
        self.connection.rate = 4
        self.connection.ignore_all = True
        self.worker.submit("normal")
        self.worker._process_command()
        with patch("sim_rate.time.monotonic", return_value=self.worker._reset_deadline + 1):
            self.worker._verify_reset(4)
        self.assertEqual(self.messages.get_nowait()[0], "resetting")
        self.assertEqual(self.messages.get_nowait()[0], "error")
        self.assertTrue(self.worker.controls_available)
        self.assertEqual(self.connection.rate, 4)

    def test_disconnected_commands_are_rejected_and_queued_commands_never_replay(self):
        self.worker.submit("increase")
        self.worker._disconnect()
        self.assertTrue(self.connection.closed)
        self.assertFalse(self.worker.submit("normal"))
        replacement = FakeConnection()
        self.worker.connection = replacement
        self.worker._connected = True
        self.worker._process_command()
        self.assertEqual(replacement.sent, [])

    def test_failed_event_is_not_reported_as_success(self):
        self.connection.send_event = Mock(return_value=False)
        self.worker.submit("normal")
        with self.assertRaises(ConnectionError):
            self.worker._process_command()
        self.assertIsNone(self.worker._reset_deadline)

    def test_invalid_rates_are_not_connection_success(self):
        for value in (None, 0, -1, True, "1", float("nan"), float("inf")):
            self.assertFalse(valid_rate(value))
        self.assertTrue(valid_rate(0.25))

    def test_worker_reconnects_and_exits_without_a_live_simulator(self):
        connections = []

        def factory(**kwargs):
            connection = FakeConnection(**kwargs)
            connections.append(connection)
            return connection

        worker = SimRateWorker(self.messages, factory, FakeRequests,
                               poll_interval=0.01, retry_interval=0.01)
        worker.start()

        def wait_for(kind):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                received, value = self.messages.get(timeout=2)
                if received == kind:
                    return value
            self.fail(f"No {kind} message")

        try:
            wait_for("connected")
            connections[0].quit = 1
            wait_for("disconnected")
            wait_for("connected")
            self.assertGreaterEqual(len(connections), 2)
            self.assertTrue(connections[0].closed)
            worker.submit("increase")
            while wait_for("rate") != 2:
                pass
        finally:
            worker.stop()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(connections[-1].closed)


if __name__ == "__main__":
    unittest.main()
