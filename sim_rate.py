import math
import queue
import threading
import time
from ctypes.wintypes import DWORD

from loguru import logger
from SimConnect import AircraftRequests, SimConnect


COMMANDS = {
    "increase": (b"SIM_RATE_INCR", 0),
    "decrease": (b"SIM_RATE_DECR", 0),
    "normal": (b"SIM_RATE_SET", 1),
}


def valid_rate(rate):
    return (isinstance(rate, (int, float)) and not isinstance(rate, bool)
            and math.isfinite(rate) and rate > 0)


class SimRateWorker(threading.Thread):
    def __init__(self, messages, connection_factory=SimConnect,
                 request_factory=AircraftRequests, poll_interval=0.25,
                 retry_interval=3.0):
        super().__init__(name="SimConnect worker", daemon=True)
        self.messages = messages
        self.connection_factory = connection_factory
        self.request_factory = request_factory
        self.poll_interval = poll_interval
        self.retry_interval = retry_interval
        self._stop_requested = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._commands = queue.Queue(maxsize=16)
        self._generation = 0
        self._connected = False
        self._reset_deadline = None
        self._reset_next_step = 0
        self._events = {}
        self.connection = None
        self.requests = None

    @property
    def controls_available(self):
        with self._lock:
            return self._connected and self._reset_deadline is None

    def submit(self, command):
        if command not in COMMANDS:
            raise ValueError(f"Unknown command: {command}")
        with self._lock:
            if not self._connected or self._reset_deadline is not None:
                return False
            try:
                self._commands.put_nowait((self._generation, command))
            except queue.Full:
                return False
        self._wake.set()
        return True

    def stop(self):
        self._stop_requested.set()
        self._wake.set()

    def _send(self, command):
        name, value = COMMANDS[command]
        event = self._events.get(name)
        if event is None:
            event = self.connection.map_to_sim_event(name)
            if event is None:
                raise RuntimeError(f"Cannot map {name.decode()}")
            self._events[name] = event
        if not self.connection.send_event(event, DWORD(value)):
            raise ConnectionError(f"Cannot transmit {name.decode()}")
        logger.info("Sent {} ({})", name.decode(), value)

    def _disconnect(self):
        with self._lock:
            self._connected = False
            self._reset_deadline = None
            self._generation += 1
        self.messages.put(("disconnected", None))
        connection, self.connection = self.connection, None
        self.requests = None
        self._events.clear()
        if connection:
            try:
                connection.exit()
            except Exception:
                logger.exception("SimConnect cleanup failed")

    def _process_command(self):
        try:
            generation, command = self._commands.get_nowait()
        except queue.Empty:
            return
        if generation != self._generation:
            return  # Never replay commands against a new simulator session.
        self._send(command)
        if command == "normal":
            with self._lock:
                self._reset_deadline = time.monotonic() + 8.0
                self._generation += 1  # Discard clicks queued before the reset.
            self._reset_next_step = time.monotonic() + 0.75
            self.messages.put(("resetting", None))

    def _verify_reset(self, rate):
        if self._reset_deadline is None:
            return
        now = time.monotonic()
        if math.isclose(rate, 1.0, rel_tol=0, abs_tol=0.01):
            with self._lock:
                self._reset_deadline = None
            self.messages.put(("reset_done", None))
        elif now >= self._reset_deadline:
            with self._lock:
                self._reset_deadline = None
            self.messages.put(("error", "MSFS did not accept 1x. Try again in an active flight."))
        elif now >= self._reset_next_step:
            # Fall back to rate steps if the simulator ignores SIM_RATE_SET.
            self._send("decrease" if rate > 1 else "increase")
            self._reset_next_step = now + 0.75

    def run(self):
        try:
            while not self._stop_requested.is_set():
                self._wake.clear()
                try:
                    if self.connection is None:
                        self.connection = self.connection_factory(auto_connect=False)
                        self.connection.connect()
                        self.requests = self.request_factory(self.connection, _time=100, _attemps=50)
                    if getattr(self.connection, "quit", 0):
                        raise ConnectionError("Simulator closed")
                    if self._connected:
                        self._process_command()
                    rate = self.requests.get("SIMULATION_RATE")
                    if not valid_rate(rate):
                        raise ConnectionError("Simulation rate is unavailable")
                    if not self._connected:
                        with self._lock:
                            self._connected = True
                        self.messages.put(("connected", None))
                    self.messages.put(("rate", rate))
                    self._verify_reset(rate)
                    self._wake.wait(self.poll_interval)
                except Exception as error:
                    logger.debug("Waiting for MSFS: {}", error)
                    self._disconnect()
                    self._stop_requested.wait(self.retry_interval)
        finally:
            self._disconnect()
