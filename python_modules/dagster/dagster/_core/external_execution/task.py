import json
import os
import shutil
import tempfile
from copy import copy
from subprocess import Popen
from threading import Thread
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from dagster_external.protocol import (
    DAGSTER_EXTERNAL_DEFAULT_INPUT_FIFO,
    DAGSTER_EXTERNAL_DEFAULT_OUTPUT_FIFO,
    DAGSTER_EXTERNAL_ENV_KEYS,
    ExternalExecutionUserdata,
)

import dagster._check as check
from dagster import OpExecutionContext
from dagster._core.external_execution.context import build_external_execution_context


class ExternalExecutionTask:
    def __init__(
        self,
        command: Sequence[str],
        context: OpExecutionContext,
        userdata: Optional[ExternalExecutionUserdata],
        env: Optional[Mapping[str, str]] = None,
        input_mode: str = "stdio",
        output_mode: str = "stdio",
        input_fifo: Optional[str] = None,
        output_fifo: Optional[str] = None,
    ):
        self._command = command
        self._context = context
        self._userdata = userdata
        self._input_mode = input_mode
        self._output_mode = output_mode
        self._tempdir = None

        if input_mode == "fifo":
            self._validate_fifo("input", input_fifo)
        self._input_fifo = check.opt_str_param(input_fifo, "input_fifo")

        if output_mode == "fifo":
            self._validate_fifo("output", output_fifo)
        self._output_fifo = check.opt_str_param(output_fifo, "output_fifo")

        self.env = copy(env) if env is not None else {}

    def _validate_fifo(self, input_output: str, value: Optional[str]) -> None:
        if value is None or not os.path.exists(value):
            check.failed(
                f'Must provide pre-existing `{input_output}_fifo` when using "fifo"'
                f' `{input_output}_mode`. Set `{input_output}_mode="temp_fifo"` to use a'
                " system-generated temporary FIFO."
            )

    def run(self) -> int:
        write_target, stdin_fd, input_env_vars = self._prepare_input()
        read_target, stdout_fd, output_env_vars = self._prepare_output()

        input_thread = Thread(target=self._write_input, args=(write_target,), daemon=True)
        input_thread.start()
        output_thread = Thread(target=self._read_output, args=(read_target,), daemon=True)
        output_thread.start()

        process = Popen(
            self._command,
            stdin=stdin_fd,
            stdout=stdout_fd,
            env={**os.environ, **self.env, **input_env_vars, **output_env_vars},
        )

        if stdin_fd is not None:
            os.close(stdin_fd)
        if stdout_fd is not None:
            os.close(stdout_fd)

        process.wait()
        input_thread.join()
        output_thread.join()

        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

        return process.returncode

    def _write_input(self, input_target: Union[str, int]) -> None:
        external_context = build_external_execution_context(self._context, self._userdata)
        with open(input_target, "w") as input_stream:
            json.dump(external_context, input_stream)

    def _read_output(self, output_target: Union[str, int]) -> Any:
        with open(output_target, "r") as output_stream:
            for line in output_stream:
                message = json.loads(line)
                if message["method"] == "report_asset_metadata":
                    self._handle_report_asset_metadata(**message["params"])
                elif message["method"] == "log":
                    self._handle_log(**message["params"])

    def _prepare_input(self) -> Tuple[Union[str, int], Optional[int], Mapping[str, str]]:
        if self._input_mode == "stdio":
            stdin_fd, write_target = os.pipe()
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["input_mode"]: "stdio",
            }
        elif self._input_mode == "fifo":
            assert self._input_fifo is not None
            stdin_fd = None
            write_target = self._input_fifo
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["input_mode"]: "fifo",
                DAGSTER_EXTERNAL_ENV_KEYS["input"]: self._input_fifo,
            }
        elif self._input_mode == "temp_fifo":
            stdin_fd = None
            write_target = os.path.join(self.tempdir, DAGSTER_EXTERNAL_DEFAULT_INPUT_FIFO)
            os.mkfifo(write_target)
            write_target = write_target
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["input_mode"]: "fifo",
                DAGSTER_EXTERNAL_ENV_KEYS["input"]: write_target,
            }
        else:
            check.failed(f"Unsupported input mode: {self._input_mode}")
        return write_target, stdin_fd, env

    def _prepare_output(self) -> Tuple[Union[str, int], Optional[int], Mapping[str, str]]:
        if self._output_mode == "stdio":
            read_target, stdout_fd = os.pipe()
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["output_mode"]: "stdio",
            }
        elif self._output_mode == "fifo":
            assert self._output_fifo is not None
            stdout_fd = None
            read_target = self._output_fifo
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["output_mode"]: "fifo",
                DAGSTER_EXTERNAL_ENV_KEYS["output"]: self._output_fifo,
            }
        elif self._output_mode == "temp_fifo":
            stdout_fd = None
            read_target = os.path.join(self.tempdir, DAGSTER_EXTERNAL_DEFAULT_OUTPUT_FIFO)
            os.mkfifo(read_target)
            env = {
                DAGSTER_EXTERNAL_ENV_KEYS["output_mode"]: "fifo",
                DAGSTER_EXTERNAL_ENV_KEYS["output"]: read_target,
            }
        else:
            check.failed(f"Unsupported output mode: {self._output_mode}")
        return read_target, stdout_fd, env

    @property
    def tempdir(self) -> str:
        if self._tempdir is None:
            self._tempdir = tempfile.mkdtemp()
        return self._tempdir

    # ########################
    # ##### HANDLE NOTIFICATIONS
    # ########################

    def _handle_log(self, message: str, level: str = "info") -> None:
        check.str_param(message, "message")
        self._context.log.log(level, message)

    def _handle_report_asset_metadata(self, label: str, value: Any) -> None:
        self._context.add_output_metadata({label: value})
