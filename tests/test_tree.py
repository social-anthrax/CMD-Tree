import unittest
from collections import deque
from typing import Any

from cmd_tree.tree import Command

commands_root = Command(None)
dict_commands = Command("dict")
get_commands = Command("get")


@get_commands.add_command("entry")
def get_dict_entry(key: str) -> tuple[str, str]:
    """
    Simulates a return of a key and the entry for a key
    :param key:
    :return:
    """
    return key, "hello"


@get_commands.add_command("foo")
def foo(value: str):
    """
    This is another test value to evaluate commands
    :param value:
    :return:
    """
    return value


@dict_commands.add_command("str")
def get_str(string: str):
    return string


@dict_commands.add_command("multiple")
def dict_multiple_length(a: str, b: str, c: str):
    return locals()


@dict_commands.add_command("optional")
def dict_optional_length(a: str, b: str, optional: str = "Hello"):
    return locals()


@dict_commands.add_command("optional_custom_length", (2, 4))
def dict_optional_length2(a: str, b: str, optional: str = "Hello", optional2: str = "hello again") -> dict[str, Any]:
    return locals()


@dict_commands.add_command("many_parameters")
def dict_many_parameters(a, b, c, d, e, f, g):  # noqa: PLR0913 # type: ignore
    return locals()


@dict_commands.add_command("varargs")
def dict_vararg(a: str, b: str, c: str, *args: str):
    return locals()


@dict_commands.add_command("list_len", length_check=[0, 2])
def list_len(a: str | None = None, b: str | None = None):
    if (not a and b) or (not b and a):
        raise RuntimeError
    else:
        pass


# This is added to commands_root in a test, this is intentional
def simple_add(x: str):
    return x


@commands_root.add_simple_subcommand("test func")
def simple_add_wrapped(x: str):
    """Contains docstring"""
    return x


def doc_string_test():
    """
    This is a test to see if we can extract the docstrings programmatically.
    """
    pass


dict_commands.add_command_subgroup(get_commands)
commands_root.add_command_subgroup(dict_commands)


class TestProfile(unittest.TestCase):
    @staticmethod
    def __cmd_deque(cmd: str):
        return deque(cmd.split())

    def test_parse_get_key_command(self):
        cmd = self.__cmd_deque("dict get entry 2332")
        self.assertEqual(("2332", "hello"), commands_root.invoke(cmd))

    def test_get_str(self):
        cmd = self.__cmd_deque("dict str test123")
        self.assertEqual("test123", commands_root.invoke(cmd))

    def test_non_existent_parse(self):
        cmd = self.__cmd_deque("dict get invalid")
        self.assertRaises(NameError, commands_root.invoke, cmd)

    def test_doc_string_extraction(self):
        """
        This is a test to see if we can extract the docstrings programmatically.
        """
        # TODO: Make this an actual test.
        print(commands_root.help())
        print(commands_root.help(show_debug="yes"))

    def test_multiple_calls(self):
        cmd = self.__cmd_deque("dict str hi")
        commands_root.invoke(cmd)
        cmd = self.__cmd_deque("dict multiple this is test")
        commands_root.invoke(cmd)
        cmd = self.__cmd_deque("dict optional a b")

    def test_optional_variables(self):
        cmd = self.__cmd_deque("dict str hi")
        commands_root.invoke(cmd)
        cmd = self.__cmd_deque("dict multiple this is test")
        commands_root.invoke(cmd)
        cmd_str = "dict many_parameters " + "a " * 7
        cmd = self.__cmd_deque(cmd_str)
        commands_root.invoke(cmd)

    def test_optional_parameters(self):
        # Excludes optional param
        cmd = self.__cmd_deque("dict optional a b")
        commands_root.invoke(cmd)

        # Includes optional param
        cmd = self.__cmd_deque("dict optional a b c")
        commands_root.invoke(cmd)

        # One arg too little
        cmd = self.__cmd_deque("dict optional a")
        self.assertRaises(TypeError, commands_root.invoke, cmd)

        # One arg too many
        cmd = self.__cmd_deque("dict optional a b c d")
        self.assertRaises(TypeError, commands_root.invoke, cmd)

    def test_optional_parameters_specified_length(self):
        cmd = self.__cmd_deque("dict optional_custom_length a b")
        commands_root.invoke(cmd)

        cmd = self.__cmd_deque("dict optional_custom_length a b c")
        commands_root.invoke(cmd)

        cmd = self.__cmd_deque("dict optional_custom_length a b c d")
        commands_root.invoke(cmd)

        cmd = self.__cmd_deque("dict optional_custom_length a b c d e")
        self.assertRaises(TypeError, commands_root.invoke, cmd)

    def test_varargs(self):
        """
        Tests if a function that accepts varargs accepts the expected number of variables.
        """
        cmd = self.__cmd_deque("dict varargs a b c test1 test2 test3 test4")

        result = commands_root.invoke(cmd)
        self.assertEqual(("test1", "test2", "test3", "test4"), result.get("args"))

        cmd = self.__cmd_deque("dict varargs a b c")
        result = commands_root.invoke(cmd)
        self.assertEqual((), result.get("args"))

    def test_simple_add(self):
        cmd = "root test"
        commands_root.add_simple_subcommand(cmd, None)(simple_add)
        cmd_deque = self.__cmd_deque(cmd + " passed!")
        result = commands_root.invoke(cmd_deque)
        self.assertEqual("passed!", result)

    def test_simple_add_wrapped(self):
        cmd_deque = self.__cmd_deque("test func passed")
        result = commands_root.invoke(cmd_deque)
        self.assertEqual("passed", result)
        self.assertEqual("Contains docstring", simple_add_wrapped.__doc__)

    def test_list_length_check(self):
        cmd = "dict list_len"
        cmd_deque = self.__cmd_deque(cmd + " test1 test2")
        commands_root.invoke(cmd_deque)

        cmd_deque = self.__cmd_deque(cmd)
        commands_root.invoke(cmd_deque)

        cmd_deque = self.__cmd_deque(cmd + " test1")
        self.assertRaises(TypeError, commands_root.invoke, cmd_deque)

    # TODO: Add test for recursion hell via adding self to self in add_simple_subcommand (should be patched,
    #       but add a test)
