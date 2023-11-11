from __future__ import annotations

import os
from typing import Any, Dict, Generator, Generic, Type, TypeAlias, TypeGuard, TypeVar, Union

StrOrBytesPath: TypeAlias = str | bytes | os.PathLike[str] | os.PathLike[bytes]  # stable

# Generic type vars for function
_T = TypeVar("_T")
_T1 = TypeVar("_T1")

# Standard naming for generic dict.
KT = TypeVar("KT")  # Key Type
VT = TypeVar("VT")  # Value Type


def check_key_dict_type(d: Any | dict[Any, _T1], expected_key_type: Type[_T]) -> TypeGuard[dict[_T, _T1]]:
    """Checks if `d` is a dictionary with key type of `expected_type`. If d is not a dictionary, is empty, or it's
    first key is not of type `expected_key_type` will return false.

    :param Any d: Type to check
    :param Type[_T] expected_key_type: Expected type of key
    :return bool: True only if `d` is a dict with at least one key, and the key type is `expected_key_type`
    """
    return (
        isinstance(d, dict)
        and (key := next(iter(d.keys()), None)) is not None  # type: ignore
        and isinstance(key, expected_key_type)  # Statement is lazily evaluated, key will always exist
    )


class RecursiveDict(Generic[KT, VT], Dict[KT, Union[VT, "RecursiveDict[KT, VT]"]]):
    """A recursive dict that holds key type KT, and value type VT | Itself."""

    @staticmethod
    def __is_recursive_dict(d: VT | RecursiveDict[KT, VT]) -> TypeGuard[RecursiveDict[KT, VT]]:
        """Checks if `d` is a RecursiveDict. If d is not a RecursiveDict, it must be a leaf node.

        :param VT | RecursiveDict[KT, VT] d: Either a `RecursiveDict`, or a possible leaf node
        :return bool: If d is a `RecursiveDict` then return True, otherwise False
        """
        return isinstance(d, RecursiveDict)

    @staticmethod
    def __is_leaf(d: VT | RecursiveDict[KT, VT]) -> TypeGuard[VT]:
        """Checks if the value taken from a recursive dict is a leaf node.

        This is done by checking if the value is not a Recursive Dict

        :param VT | RecursiveDict[KT, VT] d: _description_
        :return TypeGuard[VT]: true if d is of the RecursiveDict leaf type
        """
        return not RecursiveDict.__is_recursive_dict(d)

    def leaves_of_dict(self) -> Generator[tuple[list[KT], VT], None, None]:
        """Gets the leaves of the recursive dict with the key values required to reach that state.
        Leaves are determined by any type that is not a recursive dict, and as such can be other dictionaries or other
        nested types.

        :yield Generator[tuple[list[KT], VT], None, None]: Returns a generator which yields
            ([route to dict], tree values)
        """
        for key, val in self.items():
            if RecursiveDict.__is_recursive_dict(val):
                for k, path in val.leaves_of_dict():
                    yield [key] + k, path
                # elif not isinstance(val, dict):
            elif RecursiveDict.__is_leaf(val):
                yield [key], val

            # No else, this will catch all legal possibilities
            # The elif is to mostly appease the type checker
