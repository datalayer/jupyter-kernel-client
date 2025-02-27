# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""A remote kernel client."""

from __future__ import annotations

import logging
import os
import queue
import signal
import sys
import time
import typing as t
from getpass import getpass
from threading import Event, Lock, Thread
from urllib.parse import urlencode

import websocket  # type:ignore[import-untyped]
from jupyter_client.adapter import adapt
from jupyter_client.channels import major_protocol_version
from jupyter_client.channelsabc import ChannelABC, HBChannelABC
from jupyter_client.client import validate_string_dict
from jupyter_client.clientabc import KernelClientABC
from jupyter_client.jsonutil import extract_dates
from jupyter_client.session import Message, Session

from .constants import REQUEST_TIMEOUT
from .log import get_logger
from .utils import deserialize_msg_from_ws_v1, serialize_msg_to_ws_v1


class WSSession(Session):
    """WebSocket session."""

    def __init__(self, log: logging.Logger | None = None, **kwargs):
        super().__init__(**kwargs)
        self.log = log or get_logger()
        if not self.debug:
            self.debug = self.log.level == logging.DEBUG

    def serialize(self, msg: dict[str, t.Any], **kwargs) -> list[bytes]:  # type:ignore[override,no-untyped-def]
        """Serialize the message components to bytes.

        This is roughly the inverse of deserialize. The serialize/deserialize
        methods work with full message lists, whereas pack/unpack work with
        the individual message parts in the message list.

        Parameters
        ----------
        msg : dict or Message
            The next message dict as returned by the self.msg method.

        Returns
        -------
        msg_list : list
            The list of bytes objects to be sent with the format::

                [p_header, p_parent,
                 p_metadata, p_content, buffer1, buffer2, ...]

            In this list, the ``p_*`` entities are the packed or serialized
            versions, so if JSON is used, these are utf8 encoded JSON strings.
        """
        content = msg.get("content", {})
        if content is None:
            content = self.none
        elif isinstance(content, dict):
            content = self.pack(content)
        elif isinstance(content, bytes):
            # content is already packed, as in a relayed message
            pass
        elif isinstance(content, str):
            # should be bytes, but JSON often spits out unicode
            content = content.encode("utf8")
        else:
            message = f"Content incorrect type: {type(content)}"
            raise TypeError(message)

        real_message = [
            self.pack(msg["header"]),
            self.pack(msg["parent_header"]),
            self.pack(msg["metadata"]),
            content,
        ]

        to_send = []

        to_send.extend(real_message)

        return to_send

    def deserialize(  # type:ignore[override,no-untyped-def]
        self, msg_list: list[bytes], content: bool = True, **kwargs
    ) -> dict[str, t.Any]:
        """Deserialize a msg_list to a nested message dict.

        This is roughly the inverse of serialize. The serialize/deserialize
        methods work with full message lists, whereas pack/unpack work with
        the individual message parts in the message list.

        Parameters
        ----------
        msg_list : list of bytes
            The list of message parts of the form [p_header,p_parent,
            p_metadata,p_content,buffer1,buffer2,...].
        content : bool (True)
            Whether to unpack the content dict (True), or leave it packed
            (False).

        Returns
        -------
        msg : dict
            The nested message dict with top-level keys [header, parent_header,
            content, buffers].  The buffers are returned as memoryviews.
        """
        minimum_length = 4
        message = {}
        if not len(msg_list) >= minimum_length:
            msg = f"malformed message, must have at least {minimum_length:d} elements"
            raise TypeError(msg)
        header = self.unpack(msg_list[0])
        message["header"] = extract_dates(header)
        message["msg_id"] = header["msg_id"]
        message["msg_type"] = header["msg_type"]
        message["parent_header"] = extract_dates(self.unpack(msg_list[1]))
        message["metadata"] = self.unpack(msg_list[2])
        if content:
            message["content"] = self.unpack(msg_list[3])
        else:
            message["content"] = msg_list[3]
        buffers = [memoryview(b) for b in msg_list[4:]]
        message["buffers"] = buffers
        self.log.debug("WSSession.deserialize\n%s", message)
        # adapt to the current version
        return adapt(message)

    def send(  # type:ignore[override]
        self,
        stream: websocket.WebSocketApp,
        channel: str,
        msg_or_type: dict[str, t.Any] | str,
        content: dict[str, t.Any] | None = None,
        parent: dict[str, t.Any] | None = None,
        buffers: list[bytes] | None = None,
        header: dict[str, t.Any] | None = None,
        metadata: dict[str, t.Any] | None = None,
    ) -> dict[str, t.Any] | None:
        """Build and send a message via stream or socket.

        The message format used by this function internally is as follows:

        [p_header,p_parent,p_content,
         buffer1,buffer2,...]

        The serialize/deserialize methods convert the nested message dict into this
        format.

        Parameters
        ----------

        stream : websocket.WebSocketApp
            The websocket object used to send the data.
        channel : str
            Channel name
        msg_or_type : str or Message/dict
            Normally, msg_or_type will be a msg_type unless a message is being
            sent more than once. If a header is supplied, this can be set to
            None and the msg_type will be pulled from the header.

        content : dict or None
            The content of the message (ignored if msg_or_type is a message).
        header : dict or None
            The header dict for the message (ignored if msg_to_type is a message).
        parent : Message or dict or None
            The parent or parent header describing the parent of this message
            (ignored if msg_or_type is a message).
        metadata : dict or None
            The metadata describing the message
        buffers : list or None
            The already-serialized buffers to be appended to the message.


        Returns
        -------
        msg : dict
            The constructed message.
        """

        if isinstance(msg_or_type, (Message, dict)):
            # We got a Message or message dict, not a msg_type so don't
            # build a new Message.
            msg = msg_or_type
            buffers = buffers or msg.get("buffers", [])
        else:
            msg = self.msg(
                msg_or_type,
                content=content,
                parent=parent,
                header=header,
                metadata=metadata,
            )
        if self.check_pid and os.getpid() != self.pid:
            get_logger().warning("Attempted to send message from fork\n%s", msg)
            return None
        buffers = [] if buffers is None else buffers
        for idx, buf in enumerate(buffers):
            if isinstance(buf, memoryview):
                view = buf
            else:
                try:
                    # check to see if buf supports the buffer protocol.
                    view = memoryview(buf)
                except TypeError as e:
                    emsg = "Buffer objects must support the buffer protocol."
                    raise TypeError(emsg) from e
            if not view.contiguous:
                emsg = f"Buffer {idx:d} ({buf!r}) is not contiguous"
                # zmq requires memoryviews to be contiguous
                raise ValueError(emsg)

        if self.adapt_version:
            msg = adapt(msg, self.adapt_version)
        to_send = self.serialize(msg)
        to_send.extend(buffers)

        stream.send_bytes(serialize_msg_to_ws_v1(to_send, channel))

        self.log.debug("WSSession.send\n%s\n%s\n%s", msg, to_send, buffers)

        return msg

    def send_raw(
        self,
        stream: websocket.WebSocketApp,
        msg_list: list,
        flags: int = 0,
        copy: bool = True,
        ident: bytes | list[bytes] | None = None,
    ) -> None:
        """Send a raw message via ident path.

        This method is used to send a already serialized message.

        Parameters
        ----------
        stream : websocket.WebSocketApp
            The websocket to use for sending the message.
        msg_list : list
            The serialized list of messages to send. This only includes the
            [p_header,p_parent,p_metadata,p_content,buffer1,buffer2,...] portion of
            the message.
        ident : ident or list
            A single ident or a list of idents to use in sending.
        """
        raise NotImplementedError("WSSession.send_raw should not be needed")

    def recv(
        self,
        socket: websocket.WebSocketApp,
        mode: int = 0,  # FIXME
        content: bool = True,
        copy: bool = True,
    ) -> tuple[list[bytes] | None, dict[str, t.Any] | None]:
        """Receive and unpack a message.

        Parameters
        ----------
        socket : ZMQStream or Socket
            The socket or stream to use in receiving.

        Returns
        -------
        [idents], msg
            [idents] is a list of idents and msg is a nested message dict of
            same format as self.msg returns.
        """
        raise NotImplementedError("WSSession.recv should not be needed")


class WSChannel(ChannelABC):
    """WebSocket channel"""

    def __init__(
        self,
        channel_name: str,
        socket: websocket.WebSocketApp,
        session: WSSession,
        messages_queue: queue.Queue,
        log: logging.Logger,
    ) -> None:
        """Create a channel.

        Parameters
        ----------
        channel_name : str
            Channel name
        socket : :class:`websocket.WebSocketApp`
            The websocket connection.
        session : :class:`session.Session`
            The session to use.
        messages_queue: queue.Queue
            Messages queue
        log: logging.Logger
            Logger
        """
        self.channel_name = channel_name
        self.socket = socket
        self.session = session
        self._messages = messages_queue
        self.log = log

    def start(self) -> None:
        """Start the channel."""
        # Nothing to do the websocket is not per channel
        pass

    def stop(self) -> None:
        """Stop the channel."""
        if not self._messages.empty():
            # If unprocessed messages are detected, drain the queue collecting non-status
            # messages.  If any remain that are not 'shutdown_reply' and this is not iopub
            # go ahead and issue a warning.
            msgs = []
            while self._messages.qsize():
                msg = self._messages.get_nowait()
                if msg["msg_type"] != "status":
                    msgs.append(msg["msg_type"])
            if self.channel_name == "iopub" and "shutdown_reply" in msgs:
                return
            if len(msgs):
                self.log.warning(
                    "Stopping channel '%s' with %d unprocessed non-status messages: %s.",
                    self.channel_name,
                    len(msgs),
                    msgs,
                )

    def is_alive(self) -> bool:
        """Test whether the channel is alive."""
        return True  # FIXME

    def send(self, msg: dict[str, t.Any]) -> None:
        """Pass a message to the websocket to send"""
        self.log.debug(
            "Sending message on channel: %s, msg_id: %s, msg_type: %s",
            self.channel_name,
            msg["msg_id"],
            msg["msg_type"],
        )
        self.session.send(self.socket, self.channel_name, msg)

    def get_msg(self, timeout: float | None = None) -> dict:
        """Return the next message in the queue.

        Blocks until a message is received or timeout is reached.

        Parameters
        ----------
        timeout: float
            Timeout in seconds

        Returns
        -------
        The next message

        Raises
        ------
        Empty exception if no message is received before the timeout.
        """
        return self._messages.get(timeout=timeout)

    def get_msgs(self) -> list[dict[str, t.Any]]:
        """Get all available messages.

        Returns
        -------
        The list of messages queued.
        """
        msgs = []
        while not self._messages.empty():
            msgs.append(self._messages.get_nowait())

        return msgs

    def msg_ready(self) -> bool:
        """Is there a message that has been received?"""
        return not self._messages.empty()


class HBWSChannel(HBChannelABC, WSChannel):
    # FIXME implement an heartbeat

    @property
    def time_to_dead(self) -> float:
        return 1.0  # Taken from jupyter_client.channels.HBChannel

    def pause(self) -> None:
        """Pause the heartbeat channel."""
        pass  # FIXME

    def unpause(self) -> None:
        """Unpause the heartbeat channel."""
        pass  # FIXME

    def is_beating(self) -> bool:
        """Test whether the channel is beating."""
        return True  # FIXME
        # if self.is_alive() and not self._pause and self._beating:
        #     return True
        # else:
        #     return False


class KernelWebSocketClient(KernelClientABC):
    """A kernel client to connect to a Jupyter Server via WebSocket.

    Arguments
    ---------
    endpoint: str
        Kernel websocket endpoint to connect to
    token: str | None
        Authentication token to the server; default None
    username: str | None
        User connecting with the client; default None
    timeout: float
        Timeout for request to the server; default REQUEST_TIMEOUT
    log: logging.Logger | None
        Application logger; default None
    debug_session: bool
        Verbose session; default False. It will print lots of details on sys.stdout
    ping_interval: float
        Interval in seconds to send a ping message to the server; default 60.
        If it is set to 0, no ping message will be sent.
    reconnect_interval: float
        Amount of time to wait before trying to reconnect the websocket;
        default 0 means no reconnection.
    """

    DEFAULT_INTERRUPT_WAIT = 1

    def __init__(  # type:ignore[no-untyped-def]
        self,
        endpoint: str,
        token: str | None = None,
        username: str | None = None,
        timeout: float = REQUEST_TIMEOUT,
        log: logging.Logger | None = None,
        debug_session: bool = False,
        ping_interval: float = 60,
        reconnect_interval: int = 0,
        **kwargs,
    ):
        """Initialize the client."""
        self.allow_stdin = False  # Will change when the stdin channel opens
        self.shutting_down = False
        self.kernel_ws_endpoint = endpoint
        self.token = token
        self.log: logging.Logger = log or get_logger()
        self.kernel_socket: websocket.WebSocketApp | None = None
        self.connection_thread: Thread | None = None
        self.connection_ready = Event()
        self._message_received = Event()
        self.interrupt_thread = None
        self.ping_interval: float = ping_interval
        self.reconnect_interval = reconnect_interval
        self.timeout = timeout
        self.session = WSSession(log=self.log)
        self.session.username = username or ""
        self.session.debug = debug_session

        self._kernel_info: dict | None = None
        self._shell_channel: WSChannel | None = None
        self._iopub_channel: WSChannel | None = None
        self._stdin_channel: WSChannel | None = None
        self._hb_channel: HBWSChannel | None = None
        self._control_channel: WSChannel | None = None
        self._shell_msg_queue: queue.Queue[dict] = queue.Queue()
        self._iopub_msg_queue: queue.Queue[dict] = queue.Queue()
        self._stdin_msg_queue: queue.Queue[dict] = queue.Queue()
        self._hb_msg_queue: queue.Queue[dict] = queue.Queue()
        self._control_msg_queue: queue.Queue[dict] = queue.Queue()

        self._interactive_lock = Lock()

    def __del__(self):
        self.stop_channels()

    @property
    def kernel(self) -> t.Any:
        # FIXME this is a strange abstract property
        # because it does not exists on jupyter_client.client.KernelClient
        return None

    @property
    def shell_channel_class(self) -> type[WSChannel]:
        return WSChannel

    @property
    def iopub_channel_class(self) -> type[WSChannel]:
        return WSChannel

    @property
    def hb_channel_class(self) -> type[HBWSChannel]:
        return HBWSChannel

    @property
    def stdin_channel_class(self) -> type[WSChannel]:
        return WSChannel

    @property
    def control_channel_class(self) -> type[WSChannel]:
        return WSChannel

    def start_channels(
        self,
        shell: bool = True,
        iopub: bool = True,
        stdin: bool = True,
        hb: bool = True,
        control: bool = True,
    ) -> None:
        """Start the channels for the client."""
        self.log.debug("Connecting kernel client to %s", self.kernel_ws_endpoint)

        url = self.kernel_ws_endpoint
        params = {"session_id": self.session.session}
        if self.token is not None:
            params["token"] = self.token
        url += "?" + urlencode(params)
        self.kernel_socket = websocket.WebSocketApp(
            url,
            header=["User-Agent: Jupyter Kernel Client"],
            # Use the new optimized protocol
            subprotocols=["v1.kernel.websocket.jupyter.org"],
            on_close=self._on_close,
            on_open=self._on_open,
            on_message=self._on_message,
        )
        self.connection_thread = Thread(target=self._run_websocket)
        self.connection_thread.start()

        self.connection_ready.wait(timeout=self.timeout)
        if iopub:
            self.iopub_channel.start()
        if shell:
            self.shell_channel.start()
        if stdin:
            self.stdin_channel.start()
            self.allow_stdin = True
        else:
            self.allow_stdin = False
        if hb:
            self.hb_channel.start()
        if control:
            self.control_channel.start()

    def stop_channels(self) -> None:
        """Stop the channels for the client."""
        # Terminate thread, close socket and clear queues.
        if self.shutting_down:
            return
        self.shutting_down = True

        if self.kernel_socket:
            self.kernel_socket.close()
            self.kernel_socket = None

        if self.connection_thread is not None and self.connection_thread.is_alive():
            self.connection_thread.join(self.timeout)
            if self.connection_thread.is_alive():
                self.log.warning("Failed to stop websocket connection thread.")
            self.connection_thread = None

    @property
    def channels_running(self) -> bool:
        """Are any of the channels created and running?"""
        return self.connection_ready.is_set()

    @property
    def shell_channel(self) -> WSChannel:
        """Get the shell channel object for this kernel."""
        if self._shell_channel is None:
            assert self.kernel_socket is not None  # noqa: S101
            self._shell_channel = self.shell_channel_class(
                "shell",
                self.kernel_socket,
                self.session,
                self._shell_msg_queue,
                self.log,
            )
        return self._shell_channel

    @property
    def iopub_channel(self) -> WSChannel:
        if self._iopub_channel is None:
            assert self.kernel_socket is not None  # noqa: S101
            self._iopub_channel = self.iopub_channel_class(
                "iopub",
                self.kernel_socket,
                self.session,
                self._iopub_msg_queue,
                self.log,
            )
        return self._iopub_channel

    @property
    def stdin_channel(self) -> WSChannel:
        if self._stdin_channel is None:
            assert self.kernel_socket is not None  # noqa: S101
            self._stdin_channel = self.stdin_channel_class(
                "stdin",
                self.kernel_socket,
                self.session,
                self._stdin_msg_queue,
                self.log,
            )
        return self._stdin_channel

    @property
    def hb_channel(self) -> HBWSChannel:
        if self._hb_channel is None:
            assert self.kernel_socket is not None  # noqa: S101
            self._hb_channel = self.hb_channel_class(
                "hb", self.kernel_socket, self.session, self._hb_msg_queue, self.log
            )
        return self._hb_channel

    @property
    def control_channel(self) -> WSChannel:
        if self._control_channel is None:
            assert self.kernel_socket is not None  # noqa: S101
            self._control_channel = self.control_channel_class(
                "control",
                self.kernel_socket,
                self.session,
                self._control_msg_queue,
                self.log,
            )
        return self._control_channel

    def get_shell_msg(self, *args: t.Any, **kwargs: t.Any) -> dict[str, t.Any]:
        """Get a message from the shell channel

        Parameters
        ----------
        timeout: float
            Timeout in seconds

        Returns
        -------
        The next message

        Raises
        ------
        Empty exception if no message is received before the timeout.
        """
        return self.shell_channel.get_msg(*args, **kwargs)

    def get_iopub_msg(self, *args: t.Any, **kwargs: t.Any) -> dict[str, t.Any]:
        """Get a message from the iopub channel

        Parameters
        ----------
        timeout: float
            Timeout in seconds

        Returns
        -------
        The next message

        Raises
        ------
        Empty exception if no message is received before the timeout.
        """
        return self.iopub_channel.get_msg(*args, **kwargs)

    def get_stdin_msg(self, *args: t.Any, **kwargs: t.Any) -> dict[str, t.Any]:
        """Get a message from the stdin channel

        Parameters
        ----------
        timeout: float
            Timeout in seconds

        Returns
        -------
        The next message

        Raises
        ------
        Empty exception if no message is received before the timeout.
        """
        return self.stdin_channel.get_msg(*args, **kwargs)

    def get_control_msg(self, *args: t.Any, **kwargs: t.Any) -> dict[str, t.Any]:
        """Get a message from the control channel

        Parameters
        ----------
        timeout: float
            Timeout in seconds

        Returns
        -------
        The next message

        Raises
        ------
        Empty exception if no message is received before the timeout.
        """
        return self.control_channel.get_msg(*args, **kwargs)

    def complete(self, code: str, cursor_pos: int | None = None) -> str:
        """Tab complete text in the kernel's namespace.

        Parameters
        ----------
        code : str
            The context in which completion is requested.
            Can be anything between a variable name and an entire cell.
        cursor_pos : int, optional
            The position of the cursor in the block of code where the completion was requested.
            Default: ``len(code)``

        Returns
        -------
        The msg_id of the message sent.
        """
        if cursor_pos is None:
            cursor_pos = len(code)
        content = {"code": code, "cursor_pos": cursor_pos}
        msg = self.session.msg("complete_request", content)
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def inspect(self, code: str, cursor_pos: int | None = None, detail_level: int = 0) -> str:
        """Get metadata information about an object in the kernel's namespace.

        It is up to the kernel to determine the appropriate object to inspect.

        Parameters
        ----------
        code : str
            The context in which info is requested.
            Can be anything between a variable name and an entire cell.
        cursor_pos : int, optional
            The position of the cursor in the block of code where the info was requested.
            Default: ``len(code)``
        detail_level : int, optional
            The level of detail for the introspection (0-2)

        Returns
        -------
        The msg_id of the message sent.
        """
        if cursor_pos is None:
            cursor_pos = len(code)
        content = {
            "code": code,
            "cursor_pos": cursor_pos,
            "detail_level": detail_level,
        }
        msg = self.session.msg("inspect_request", content)
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def history(
        self,
        raw: bool = True,
        output: bool = False,
        hist_access_type: str = "range",
        **kwargs: t.Any,
    ) -> str:
        """Get entries from the kernel's history list.

        Parameters
        ----------
        raw : bool
            If True, return the raw input.
        output : bool
            If True, then return the output as well.
        hist_access_type : str
            'range' (fill in session, start and stop params), 'tail' (fill in n)
             or 'search' (fill in pattern param).

        session : int
            For a range request, the session from which to get lines. Session
            numbers are positive integers; negative ones count back from the
            current session.
        start : int
            The first line number of a history range.
        stop : int
            The final (excluded) line number of a history range.

        n : int
            The number of lines of history to get for a tail request.

        pattern : str
            The glob-syntax pattern for a search request.

        Returns
        -------
        The ID of the message sent.
        """
        if hist_access_type == "range":
            kwargs.setdefault("session", 0)
            kwargs.setdefault("start", 0)
        content = dict(raw=raw, output=output, hist_access_type=hist_access_type, **kwargs)
        msg = self.session.msg("history_request", content)
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def kernel_info(self, force: bool = False) -> str:
        """Request kernel info

        Returns
        -------
        The msg_id of the message sent
        """
        msg = self.session.msg("kernel_info_request")
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def kernel_info_interactive(
        self,
        timeout: float | None = None,
    ) -> dict:
        """Get the kernel info.

        Arguments
        ---------
            timeout: Request timeout; default not timeout

        Returns
        -------
            The kernel info
        """
        if self._kernel_info is not None:
            return self._kernel_info

        self.wait_for_ready(timeout)
        return self._kernel_info  # type:ignore[return-value]

    def comm_info(self, target_name: str | None = None) -> str:
        """Request comm info

        Returns
        -------
        The msg_id of the message sent
        """
        content = {} if target_name is None else {"target_name": target_name}
        msg = self.session.msg("comm_info_request", content)
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def execute(
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = None,
        stop_on_error: bool = True,
    ) -> str:
        """Execute code in the kernel.

        Parameters
        ----------
        code : str
            A string of code in the kernel's language.

        silent : bool, optional (default False)
            If set, the kernel will execute the code as quietly possible, and
            will force store_history to be False.

        store_history : bool, optional (default True)
            If set, the kernel will store command history.  This is forced
            to be False if silent is True.

        user_expressions : dict, optional
            A dict mapping names to expressions to be evaluated in the user's
            dict. The expression values are returned as strings formatted using
            :func:`repr`.

        allow_stdin : bool, optional (default self.allow_stdin)
            Flag for whether the kernel can send stdin requests to frontends.

            Some frontends (e.g. the Notebook) do not support stdin requests.
            If raw_input is called from code executed from such a frontend, a
            StdinNotImplementedError will be raised.

        stop_on_error: bool, optional (default True)
            Flag whether to abort the execution queue, if an exception is encountered.

        Returns
        -------
        The msg_id of the message sent.
        """
        if user_expressions is None:
            user_expressions = {}
        if allow_stdin is None:
            allow_stdin = self.allow_stdin

        # Don't waste network traffic if inputs are invalid
        if not isinstance(code, str):
            message = f"code {code!r} must be a string"
            raise ValueError(message)
        validate_string_dict(user_expressions)

        # Create class for content/msg creation. Related to, but possibly
        # not in Session.
        content = {
            "code": code,
            "silent": silent,
            "store_history": store_history,
            "user_expressions": user_expressions,
            "allow_stdin": allow_stdin,
            "stop_on_error": stop_on_error,
        }
        msg = self.session.msg("execute_request", content)
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def execute_interactive(  # noqa: C901
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = None,
        stop_on_error: bool = True,
        timeout: float | None = None,
        output_hook: t.Callable | None = None,
        stdin_hook: t.Callable | None = None,
    ) -> dict[str, t.Any]:
        """Execute code in the kernel interactively

        Output will be redisplayed, and stdin prompts will be relayed as well.

        You can pass a custom output_hook callable that will be called
        with every IOPub message that is produced instead of the default redisplay.

        Parameters
        ----------
        code : str
            A string of code in the kernel's language.

        silent : bool, optional (default False)
            If set, the kernel will execute the code as quietly possible, and
            will force store_history to be False.

        store_history : bool, optional (default True)
            If set, the kernel will store command history.  This is forced
            to be False if silent is True.

        user_expressions : dict, optional
            A dict mapping names to expressions to be evaluated in the user's
            dict. The expression values are returned as strings formatted using
            :func:`repr`.

        allow_stdin : bool, optional (default self.allow_stdin)
            Flag for whether the kernel can send stdin requests to frontends.

        stop_on_error: bool, optional (default True)
            Flag whether to abort the execution queue, if an exception is encountered.

        timeout: float or None (default: None)
            Timeout to use when waiting for a reply

        output_hook: callable(msg)
            Function to be called with output messages.
            If not specified, output will be redisplayed.

        stdin_hook: callable(msg)
            Function to be called with stdin_request messages.
            If not specified, input/getpass will be called.

        Returns
        -------
        reply: dict
            The reply message for this request
        """
        if not self.iopub_channel.is_alive():
            emsg = "IOPub channel must be running to receive output"
            raise RuntimeError(emsg)
        if allow_stdin is None:
            allow_stdin = self.allow_stdin
        if allow_stdin and not self.stdin_channel.is_alive():
            emsg = "stdin channel must be running to allow input"
            raise RuntimeError(emsg)

        if stdin_hook is None:
            stdin_hook = self._stdin_hook_default
        if output_hook is None:
            # default: redisplay plain-text outputs
            output_hook = self._output_hook_default

        # set deadline based on timeout
        if timeout is not None:
            deadline = time.monotonic() + timeout

        with self._interactive_lock:
            self._message_received.clear()
            if self.iopub_channel.msg_ready():
                # Flush the message
                self.iopub_channel.get_msgs()
            msg_id = self.execute(
                code,
                silent=silent,
                store_history=store_history,
                user_expressions=user_expressions,
                allow_stdin=allow_stdin,
                stop_on_error=stop_on_error,
            )

            # wait for output and redisplay it
            while True:
                if not self.connection_ready.is_set():
                    raise RuntimeError("Connection was lost.")

                if timeout is not None:
                    timeout = max(0, deadline - time.monotonic())

                self._message_received.wait(timeout=timeout)

                if allow_stdin:
                    try:
                        req = self.stdin_channel.get_msg(timeout=0)
                        stdin_hook(req)
                        continue
                    except (queue.Empty, TimeoutError):
                        ...

                try:
                    msg = self.iopub_channel.get_msg(timeout=0)
                except (queue.Empty, TimeoutError):
                    if not self.iopub_channel.msg_ready() and (
                        not allow_stdin or not self.stdin_channel.msg_ready()
                    ):
                        self._message_received.clear()
                    continue

                if msg["parent_header"].get("msg_id") != msg_id:
                    self.log.debug(f"Ignoring message not from request: {msg!s}")
                    continue
                output_hook(msg)

                # stop on idle
                if (
                    msg["header"]["msg_type"] == "status"
                    and msg["content"]["execution_state"] == "idle"
                ):
                    break

            # output is done, get the reply
            if timeout is not None:
                timeout = max(0, deadline - time.monotonic())
            return self._recv_reply(msg_id, timeout=timeout)

    def is_alive(self) -> bool:
        """Is the kernel process still running?"""
        if self._hb_channel is not None:
            # We don't have access to the KernelManager,
            # so we use the heartbeat.
            return self._hb_channel.is_beating()
        # no heartbeat and not local, we can't tell if it's running,
        # so naively return True
        return True

    def is_complete(self, code: str) -> str:
        """Ask the kernel whether some code is complete and ready to execute.

        Returns
        -------
        The ID of the message sent.
        """
        msg = self.session.msg("is_complete_request", {"code": code})
        self.shell_channel.send(msg)
        return msg["header"]["msg_id"]

    def input(self, string: str) -> None:
        """Send a string of raw input to the kernel.

        This should only be called in response to the kernel sending an
        ``input_request`` message on the stdin channel.

        Returns
        -------
        The ID of the message sent.
        """
        content = {"value": string}
        msg = self.session.msg("input_reply", content)
        self.stdin_channel.send(msg)

    def shutdown(self, restart: bool = False) -> str:
        """Request an immediate kernel shutdown on the control channel.

        Upon receipt of the (empty) reply, client code can safely assume that
        the kernel has shut down and it's safe to forcefully terminate it if
        it's still alive.

        The kernel will send the reply via a function registered with Python's
        atexit module, ensuring it's truly done as the kernel is done with all
        normal operation.

        Returns
        -------
        The msg_id of the message sent
        """
        # Send quit message to kernel. Once we implement kernel-side setattr,
        # this should probably be done that way, but for now this will do.
        msg = self.session.msg("shutdown_request", {"restart": restart})
        self.control_channel.send(msg)
        return msg["header"]["msg_id"]

    def wait_for_ready(self, timeout: float | None = None) -> None:  # noqa: C901
        """Waits for a response when a client is blocked

        - Sets future time for timeout
        - Blocks on shell channel until a message is received
        - Exit if the kernel has died
        - If client times out before receiving a message from the kernel, send RuntimeError
        - Flush the IOPub channel
        """
        if timeout is None:
            timeout = float("inf")
        abs_timeout = time.time() + timeout

        # This Client was not created by a KernelManager,
        # so wait for kernel to become responsive to heartbeats
        # before checking for kernel_info reply
        while not self.is_alive():
            if time.time() > abs_timeout:
                message = (
                    f"Kernel didn't respond to heartbeats in {timeout:d} seconds and timed out"
                )
                raise RuntimeError(message)
            time.sleep(0.2)

        with self._interactive_lock:
            # Wait for kernel info reply on shell channel
            while True:
                self.kernel_info()
                try:
                    msg = self.shell_channel.get_msg(timeout=1)
                except queue.Empty:
                    pass
                else:
                    if msg["msg_type"] == "kernel_info_reply":
                        # Checking that IOPub is connected. If it is not connected, start over.
                        try:
                            self.iopub_channel.get_msg(timeout=0.2)
                        except queue.Empty:
                            pass
                        else:
                            self._handle_kernel_info_reply(msg)
                            break

                if not self.is_alive():
                    emsg = "Kernel died before replying to kernel_info"
                    raise RuntimeError(emsg)

                # Check if current time is ready check time plus timeout
                if time.time() > abs_timeout:
                    emsg = f"Kernel didn't respond in {timeout:d} seconds"
                    raise TimeoutError(emsg)

            # Flush IOPub channel
            while True:
                try:
                    msg = self.iopub_channel.get_msg(timeout=0.2)
                except queue.Empty:
                    break

    def _handle_kernel_info_reply(self, msg: dict[str, t.Any]) -> None:
        """handle kernel info reply

        sets protocol adaptation version. This might
        be run from a separate thread.
        """
        content = msg["content"]
        self._kernel_info = content
        adapt_version = int(content["protocol_version"].split(".")[0])
        if adapt_version != major_protocol_version:
            self.session.adapt_version = adapt_version

    def _on_open(self, _: websocket.WebSocket) -> None:
        self.log.debug("Websocket connection is ready.")
        self.connection_ready.set()

    def _on_close(self, _: websocket.WebSocket, close_status_code: t.Any, close_msg: t.Any) -> None:
        msg = "Websocket connection is closed"
        if close_status_code or close_msg:
            self.log.info("%s: %s %s", msg, close_status_code, close_msg)
        else:
            self.log.debug(msg)
        self.connection_ready.clear()

    def _on_message(self, _: websocket.WebSocket, message: bytes) -> None:
        channel, msg_list = deserialize_msg_from_ws_v1(message)
        deserialize_msg = self.session.deserialize(msg_list)
        self.log.debug(
            "Received message on channel: {channel}, msg_id: {msg_id}, msg_type: {msg_type}".format(
                channel=channel,
                **(deserialize_msg or {"msg_id": "null", "msg_type": "null"}),
            )
        )

        getattr(self, f"_{channel}_msg_queue").put_nowait(deserialize_msg)
        self._message_received.set()

    def _run_websocket(self) -> None:
        if self.kernel_socket is None:
            self.log.error("No websocket defined.")
            return
        try:
            self.kernel_socket.run_forever(
                ping_interval=self.ping_interval, reconnect=self.reconnect_interval
            )
        except ValueError as e:
            self.log.error(
                "Unable to open websocket connection with %s",
                self.kernel_socket.url,
                exc_info=e,
            )
        except BaseException as e:
            self.log.error("Websocket listener thread stopped.", exc_info=e)

    def _output_hook_default(self, msg: dict[str, t.Any]) -> None:
        """Default hook for redisplaying plain-text output"""
        sys.stdout.flush()
        sys.stderr.flush()
        msg_type = msg["header"]["msg_type"]
        content = msg["content"]
        if msg_type == "stream":
            stream = getattr(sys, content["name"])
            stream.write(content["text"])
        elif msg_type in ("display_data", "execute_result"):
            sys.stdout.write(content["data"].get("text/plain", ""))
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif msg_type == "error":
            sys.stderr.write("\n".join(content["traceback"]))

    def _stdin_hook_default(self, msg: dict[str, t.Any]) -> None:
        """Handle an input request"""
        content = msg["content"]
        prompt = getpass if content.get("password", False) else input

        # wrap SIGINT handler
        real_handler = signal.getsignal(signal.SIGINT)

        def double_int(sig, frame):
            # call real handler (forwards sigint to kernel),
            # then raise local interrupt, stopping local raw_input
            real_handler(sig, frame)  # type:ignore[operator,misc]
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, double_int)

        try:
            raw_data = prompt(content["prompt"])
        except EOFError:
            # turn EOFError into EOF character
            raw_data = "\x04"
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            return
        finally:
            # restore SIGINT handler
            signal.signal(signal.SIGINT, real_handler)

        # only send stdin reply if there *was not* another request
        # or execution finished while we were reading.
        if not (self.stdin_channel.msg_ready() or self.shell_channel.msg_ready()):
            self.input(raw_data)

    def _recv_reply(
        self, msg_id: str, timeout: float | None = None, channel: str = "shell"
    ) -> dict[str, t.Any]:
        """Receive and return the reply for a given request"""
        if timeout is not None:
            deadline = time.monotonic() + timeout
        while True:
            if timeout is not None:
                timeout = max(0, deadline - time.monotonic())
            try:
                if channel == "control":
                    reply = self.control_channel.get_msg(timeout=timeout)
                else:
                    reply = self.shell_channel.get_msg(timeout=timeout)
            except queue.Empty as e:
                msg = "Timeout waiting for reply"
                raise TimeoutError(msg) from e
            if reply["parent_header"].get("msg_id") != msg_id:
                self.log.debug("Ignoring message not from request: %s", msg_id)
                continue
            return reply
