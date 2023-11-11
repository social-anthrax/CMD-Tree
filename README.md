
# CMD Tree

A command parser meant for TUI like interaction. Inspired by Fast API's decorators, commands can be registered as a part of a group allowing for more complex commands. A help function is generated using doc strings and introspection to find the number of arguments.

## Features

- Automatic help function. Help is generated from doc strings and checking function properties to determine the number of arguments.
- Configurable length checks.
- If a tuple is given it will be read as (lower-bound, upper-bound) inclusive. Setting either to None will disable the bound check for either lower or upper bound.
- If a list is given it will allow any number of arguments specified in the list.
- default is None where it will set it to be bounded between the length of required arguments and all the arguments automatically. Works with varargs.
- Command groups
- Convenience functions for adding full command branches.
- Default command names derived from function names.

## Usage/Examples

```python
from cmd_tree.tree import Command

commands_root = Command(None)
dict_commands = Command("dict")
get_commands = Command("get")

# Add the get commands to the dict subgroup
dict_commands.add_command_subgroup(get_commands)
# Add dict commands to the root group.
commands_root.add_command_subgroup(dict_commands)


# Can be invoked with `dict get entry`
@get_commands.add_command("entry")
def get_dict_entry(key: str) -> tuple[str, str]:
    """
    Simulates a return of a key and the entry for a key
    :param key:
    :return:
    """
    return key, "hello"


# Variable length argument, can either be invoked with 0 arguments or 2
@dict_commands.add_command("list_len", length_check=[0, 2])
def list_len(a: str | None = None, b: str | None = None):
    if (not a and b) or (not b and a):
        raise RuntimeError
    else:
        return True


# Variable length argument, can be invoked with 2, 3, 4 arguments.
@dict_commands.add_command("optional_custom_length", (2, 4))
def dict_optional_length2(a: str, b: str, optional: str = "Hello", optional2: str = "hello again") -> dict[str, Any]:
    return locals()


# Can be invoked with `test foo`
@commands_root.add_simple_subcommand("test foo")
def simple_subcommand(x: str):
    """Contains docstring"""
    return x


# TODO: Make this an actual test.
print(commands_root.help())  # Show the help tree
print(commands_root.help(show_debug="yes"))  # Show's the location of the functions for debugging purposes.
```
