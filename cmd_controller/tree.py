import functools
import inspect
import logging
import types
from collections import deque
from functools import wraps
from typing import Any, Callable, Self, TypeAlias, Union

from pydantic import BaseModel, ConfigDict

from cmd_controller.common_types import RecursiveDict

logger = logging.getLogger(__name__)

LengthBounds: TypeAlias = tuple[int, int | None]

LengthTypes: TypeAlias = list[int] | LengthBounds | int

CallableFunction: TypeAlias = Union[Callable[..., Any], types.FunctionType, types.MethodType]


class CommandNotFoundError(NameError):
    """
    Function not found in command tree.
    Inherits from NameError
    """

    pass


class CommandTypeError(TypeError):
    """
    Inappropriate argument type when invoking command function.
    Inherits from TypeError
    """

    pass


class FunctionHelp(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    cmd_name: str
    function_name: str
    function_signature: inspect.Signature
    doc_string: str | None
    length_check: LengthTypes
    location: str

    @staticmethod
    def pretty_signature(function_sig: inspect.Signature):
        """
        Modified from inspect.Signature
        :param function_sig:
        :return:
        """
        result: list[str] = []
        render_pos_only_separator = False
        render_kw_only_separator = True
        for param in function_sig.parameters.values():
            # Skip if it's string, every input has to be a string anyway
            kind = param.kind
            if param.annotation == str:
                formatted = param.name
            else:
                formatted = str(param)

            if kind == param.kind.POSITIONAL_ONLY:
                render_pos_only_separator = True
            elif render_pos_only_separator:
                # It's not a positional-only parameter, and the flag
                # is set to 'True' (there were pos-only params before.)
                result.append("/")
                render_pos_only_separator = False

            if kind == param.kind.VAR_POSITIONAL:
                # OK, we have an '*args'-like parameter, so we won't need
                # a '*' to separate keyword-only arguments
                render_kw_only_separator = False
            elif kind == param.kind.KEYWORD_ONLY and render_kw_only_separator:
                # We have a keyword-only parameter to render, and we haven't
                # rendered an '*args'-like parameter before, so add a '*'
                # separator to the parameters list ("foo(arg1, *, arg2)" case)
                result.append("*")
                # This condition should be only triggered once, so
                # reset the flag
                render_kw_only_separator = False

            result.append(f"<{formatted}>")

        if render_pos_only_separator:
            # There were only positional-only parameters, hence the
            # flag was not reset to 'False'
            result.append("/")

        rendered = " ".join(result)

        # TODO: pretty print annotations too
        # if function_sig.return_annotation is not inspect.Signature.empty:
        #     anno = formatannotation(self.return_annotation)
        #     rendered += " -> {}".format(anno)

        return rendered

    @classmethod
    def from_function(cls, cmd_name: str, function: CallableFunction) -> Self:
        model = cls(
            cmd_name=cmd_name,
            function_name=function.__name__,
            function_signature=inspect.signature(function),
            doc_string=function.__doc__,
            length_check=function.__dict__[f"__{cmd_name}_length_check__"],
            location=function.__module__,
        )
        return model

    def pretty(self, def_loc: bool = False) -> tuple[str, str]:
        """
        Returns a pretty representation of the function. Does not include command name
        :return: tuple of (pretty signature, "docstring + length check + file loc")
        """
        pretty_sig = self.pretty_signature(self.function_signature)
        docstring = (
            " ".join(
                [
                    stripped
                    for line in self.doc_string.splitlines()
                    if (stripped := line.strip()) and not stripped.startswith(":")
                ]
            )
            if self.doc_string
            else "No docstring set"
        )

        help_string = f"| {docstring} "
        if not isinstance(self.length_check, int) or len(self.function_signature.parameters) != self.length_check:
            help_string += f"| Length check set to {self.length_check}."

        if def_loc:
            help_string += f"| Defined in {self.location}.{self.function_name}"

        return pretty_sig, help_string


class Command:
    """
    A command tree which can have further commands added via :py:func:`Command.add_command` and
    :py:function:`Command.add_simple_subcommand` To start the command call use instance(command: deque[str])
    """

    CommandDict: TypeAlias = dict[str, CallableFunction | Self]

    def __init__(self, subcommand_group_name: str | None):
        """
        Creates a subcommand / root command tree.
        :param subcommand_group_name:  Set to None to create a root command, otherwise set the
                                        name of the group of subcommands
        """
        logger.debug(f"Initialised new command group under {subcommand_group_name}")
        self.subcommands: Command.CommandDict = {}
        self.command_group_name: str | None = subcommand_group_name
        # Always add help.
        self.add_command("help")(self.help)

    @staticmethod
    def __pretty_signature(function: CallableFunction) -> str:
        return f"{function.__module__}.{function.__name__}{str(inspect.signature(function))}"

    def add_command(self, name: str | None = None, length_check: LengthTypes | None = None, unwrap: bool = True):
        """
        Adds a command to the current handler with an optional length check for the number of arguments.
        Can then be called by doing command(deque(["name"]))

        :param str name: Name of subcommand
        :param list[int] | bound | int | None length_check: Argument length for the command to accept.
            If a tuple is given it will be read as (lower-bound, upperbound) inclusive.
            If a list is given it will allow any number of arguments specified in the list.
            default is None where it will set it to be bounded between the length of required arguments and all the
            arguments automatically.
        :param bool unwrap: Unwraps the function from any existing decorators before adding it to the command group
        """

        def add_command_decorator(function: CallableFunction):
            if not length_check:
                # This can be also done with unreadable code, but we're not that kind of girlie :3
                # # fmt: off
                # curr_len_check = (
                #     ((upper or arg_count) - default_len, upper) if (
                #         arg_count := function.__code__.co_argcount, # type: ignore
                #         upper := len([param for param in inspect.signature(function).parameters.values()
                #                 if param.default is param.empty and param.kind != param.VAR_POSITIONAL]),
                #         default_len := len(function.__defaults__ or []),
                #     )[1] or default_len else arg_count)
                # # fmt: on

                parameters = inspect.signature(function).parameters

                # if 0b100 is set so remove upper bound, then function contains varargs. Yes we're doing this.
                # Type ignored as static analysis tools don't recognize the __code__ attribute
                param_len = None if function.__code__.co_flags & 0b100 else len(parameters)  # type: ignore

                # Only set bounds if there are optional params or a var_arg
                if function.__defaults__ or (param_len is None):
                    # Get number of parameters that don't have a default and aren't a variable positional argument
                    lower_bound = len(
                        [
                            param
                            for param in parameters.values()
                            if param.default is param.empty and param.kind != param.VAR_POSITIONAL
                        ]
                    )
                    curr_length_check: LengthTypes = (lower_bound, param_len)
                else:
                    curr_length_check = param_len

            else:
                curr_length_check = length_check

            # Unwrap the function so we can use other wrappers before
            if unwrap:
                function = inspect.unwrap(function)

            @wraps(function)
            def call_with_length_check(*args: Any, **kwargs: Any):
                arg_len = len(args)
                # Check any of the allowed methods for specifying length
                match curr_length_check:
                    case int():
                        if arg_len != curr_length_check:  # simple arg length check
                            raise CommandTypeError(
                                f"{self.__pretty_signature(function)} is set to expect {curr_length_check} "
                                f"args, received {arg_len}."
                            )

                    case list():  # length check is a list of values
                        if arg_len not in curr_length_check:
                            raise CommandTypeError(
                                f"{self.__pretty_signature(function)} is set to expect any length of args from"
                                f" {curr_length_check} received {arg_len}"
                            )

                    case (lower, None):  # Only lower bound is set
                        if not lower <= arg_len:
                            raise CommandTypeError(
                                f"{self.__pretty_signature(function)} is set to expect at least {lower} args,"
                                f" received {arg_len}."
                            )

                    case (lower, upper):  # both bounds are set
                        if not lower <= arg_len <= upper:
                            raise CommandTypeError(
                                f"{self.__pretty_signature(function)} expects between {lower} and {upper} "
                                f"(inclusive) args received {arg_len}."
                            )

                return function(*args, **kwargs)

            # If name is empty set command to be equal to the function name
            command_name = name or function.__name__

            # Use attribute to fetch value when pretty printing
            call_with_length_check.__dict__[f"__{command_name}_length_check__"] = curr_length_check

            # Only add to command tree if the value doesn't already exist.
            if not self.subcommands.get(command_name):
                self.subcommands[command_name] = call_with_length_check
            else:
                raise ValueError(f"Subcommand with {command_name} already exists!")

            return call_with_length_check

        return add_command_decorator

    def add_command_subgroup(self, command_group: Self):
        """
        Adds a Command instance to the command group which can then be accessed using it's branch_name attribute.

        For example::

            root = Command(None)
            root.add_command_group(send_commands)
            cmd = deque("send rekey".split())
            root(cmd)

        :param command_group: subgroup of commands to add to the current command
        :raises ValueError: If a subcommand/ subgroup is already registered with the name of the command_group
        """
        if not command_group.command_group_name:
            raise TypeError("Cannot add root group as a subcommand")
        assert command_group.command_group_name
        if not self.subcommands.get(command_group.command_group_name):
            self.subcommands[command_group.command_group_name] = command_group
        else:
            raise ValueError(f"Subcommand group with {command_group.command_group_name} already exists!")

    def generate_help_dict(self) -> RecursiveDict[str, FunctionHelp]:
        """
        Creates a recursive dict tree with nodes being the [sub]command name, and the leaves being helper functions
        :return RecursiveDict[str, FunctionHelp]:
        """
        help_dict: RecursiveDict[str, FunctionHelp] = RecursiveDict()
        for cmd_or_subgroup_name, func_or_command in self.subcommands.items():
            match func_or_command:
                # Function
                case Command():
                    help_dict[cmd_or_subgroup_name] = func_or_command.generate_help_dict()
                case types.FunctionType() | types.MethodType():
                    # Skip the help function so we don't clutter up page
                    if cmd_or_subgroup_name == "help" and self.command_group_name is not None:
                        continue
                    help_dict[cmd_or_subgroup_name] = FunctionHelp.from_function(cmd_or_subgroup_name, func_or_command)
                case _:
                    raise ValueError(
                        f"Managed to encounter a {type(func_or_command)} without it being a function type. "
                        "Please report as an issue"
                    )

        return help_dict

    def help(self, show_debug: str | None = None) -> str:
        """Shows this help message. If debug is set then show module locations

        :return str: String help message
        """
        debug = bool(show_debug)

        if not self.command_group_name:
            help_arr: list[str] = ["Help"]
        else:
            help_arr: list[str] = [f"Help for {self.command_group_name} subcommand"]
        leaves = list(
            ((pretty := v.pretty(debug)), f'{" ".join(k)} {pretty[0]}')
            for k, v in self.generate_help_dict().leaves_of_dict()
        )

        # TODO: Some function sigs feel far too long, currently shorten justification justification to 100.
        #       Make this more customisable

        ljust_len = len(max(leaves, key=lambda x: len(x[1]))[1]) + 7  # ljust for pretty print
        ljust_len = min(
            ljust_len, 100
        )  # As there are some function signatures that are too long and it's just breaking it.

        for func_help, cmd_path in leaves:
            help_arr.append(cmd_path.ljust(ljust_len) + func_help[1])
            help_arr.append(f"{cmd_path:{ljust_len}} {func_help}")

        help_str = "\n".join(help_arr)
        logger.info(f"\n{help_str}")
        return help_str

    def invoke(self, commands: deque[str]) -> Any:
        """
        Recursively looks up commands in the commands tree and calls with remaining commands
        :raises CommandTypeError: If number of arguments isn't correct for the invoked function
        :raises CommandNotFoundException: If function is not found
        :param commands: Deque of strings. Commands are popped from the left.
        """
        subcommand = commands.popleft()
        if next_command_or_function := self.subcommands.get(subcommand):
            # If we've reached a function we want to return that
            if isinstance(next_command_or_function, Command):
                return next_command_or_function.invoke(commands)
            else:
                # call next command with remaining tokens as arguments
                logger.debug(f"Found {next_command_or_function.__module__}.{next_command_or_function.__name__}")
                return next_command_or_function(*commands)
        else:
            raise CommandNotFoundError("Command not found")

    def func_lookup(self, commands: deque[str]) -> tuple[Self, CallableFunction | None, list[str]]:
        """
        Looks up a function
        :param commands: Deque of strings. Commands are popped from the left.
        :return: If function is found; returns the found handler and function with all unread tokens.
               If function is not found; return the last matched class and None with all unmatched (**not unread**)
               tokens
        """
        subcommand = commands.popleft()
        if next_command := self.subcommands.get(subcommand):
            # If we've reached a function we want to return that
            if isinstance(next_command, Command):
                return next_command.func_lookup(commands)
            else:
                # return found function with remaining tokens
                return self, next_command, [*commands]
        else:
            return self, None, [subcommand, *commands]

    @classmethod
    def _create_with_subcommand_group(cls, subcommand: Self, name: str) -> Self:
        """
        Helper function to allow for easier folding.
        Creates a new Command class and adds the given subcommand group to it.
        :param subcommand:
        :param name:
        :return:
        """
        x = cls(name)
        x.add_command_subgroup(subcommand)
        return x

    def add_simple_subcommand(self, cmd_path: str, length_check: LengthTypes | None = None):
        """
        Allows for simple adding of paths if creating a full subcommand is wasteful.
        :param cmd_path: Relative lookup from self. For example if self is under "send get" and you would like to add
            "send get full path to", cmd_path = "full path to"
        :param length_check: Same as self.add_command
        :return: original function with length check enabled
        """

        def wrapper(function: Union[Callable[..., Any], types.FunctionType]):
            cmd_list = cmd_path.split()
            if len(cmd_list) < 2:  # noqa: PLR2004
                raise TypeError("If command is a single subcommand then use self.add_command !")

            last_found_command, matched_function, cmd_list = self.func_lookup(deque(cmd_list))
            if matched_function is not None:
                raise TypeError(f"Function already exists at {cmd_path}!")

            cmd_name = cmd_list.pop()
            if cmd_list:
                subcommand_name = cmd_list.pop()
                command_cls = Command(subcommand_name)
            else:
                command_cls = last_found_command

            # Wrapped command with length check
            ret = command_cls.add_command(cmd_name, length_check)(function)

            commands = functools.reduce(
                Command._create_with_subcommand_group,
                cmd_list[::-1],
                command_cls,
            )

            # prevents unbounded recursion
            if commands is not last_found_command:
                last_found_command.add_command_subgroup(commands)
            return ret

        return wrapper
