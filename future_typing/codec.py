import codecs
import encodings
import io
import sys
from tokenize import NAME, NUMBER, OP, STRING, cookie_re, tokenize, untokenize
from typing import Any, List, Tuple

from .utils import Token, transform_tokens

utf_8 = encodings.search_function("utf8")


def decode(
    content: bytes, errors: str = "strict", typing_module_name: str = "typing___"
) -> Tuple[str, int]:
    """
    Replace generic type hints and `|` union operator if needed to be interpreted
    """
    if not content:
        return "", 0

    lines = io.BytesIO(content).readlines()
    first_line = lines[0].decode("utf-8", errors)
    try:
        second_line = lines[1].decode("utf-8", errors)
    except IndexError:
        second_line = None

    typing_import_line = 0
    # A custom encoding is set or none
    if cookie_re.match(first_line) or not first_line.strip("\n") or \
        (second_line and (cookie_re.match(second_line) or not second_line.strip("\n"))):
        typing_import_line = 1
        # avoid recursion problems
        if "future_typing" in first_line:
            lines[0] = cookie_re.sub("# -*- coding: utf-8", first_line).encode("utf-8")

        # to account that the shebang might be the first line
        if second_line:
            if "future_typing" in second_line:
                lines[1] = cookie_re.sub("# -*- coding: utf-8", second_line).encode("utf-8")

    preserved_lines = []
    remaining_lines = []
    docstring_started = False
    future_import_found = False
    
    for line in lines:
        preserved_lines = []
    remaining_lines = []
    docstring_started = False
    future_import_found = False

    for line in lines:
        decoded_line = line.decode("utf-8", errors)
        if (
            decoded_line == "\n"
            or decoded_line.startswith("#!")
            or cookie_re.match(decoded_line)
            or (
                decoded_line.strip().startswith('"""')
                and not docstring_started
            )
            or (
                docstring_started
                and not decoded_line.strip().endswith('"""')
            )
            or (
                decoded_line.strip().startswith("from __future__")
                and not future_import_found
            )
        ):
            preserved_lines.append(line)
            if (
                (decoded_line.strip().startswith('"""')
                or decoded_line.strip().endswith('"""'))
                and not (
                    decoded_line.strip().startswith('"""')
                    and decoded_line.strip().endswith('"""')
                )
            ):
                docstring_started = not docstring_started
            if decoded_line.strip().startswith("from __future__"):
                future_import_found = True
        else:
            remaining_lines.append(line)
            break
        
    remaining_lines.extend(lines[len(preserved_lines) :])

    if sys.version_info < (3, 10):
        remaining_lines.insert(
            0,
            f"import typing as {typing_module_name}\n".encode("utf-8"),
        )

    content = b"".join(preserved_lines + remaining_lines)

    g = tokenize(io.BytesIO(content).readline)
    result: List[Token] = []
    tokens_to_change: List[Token] = []

    for tp, val, *_ in g:
        if tp in (NUMBER, NAME, STRING) or _is_in_generic(tp, val, tokens_to_change):
            tokens_to_change.append((tp, val))
        else:
            result.extend(transform_tokens(tokens_to_change, typing_module_name))
            result.append((tp, val))
            tokens_to_change = []

    res = untokenize(result).decode("utf-8", errors)
    return res, len(content)


def _is_in_generic(tp: int, val: str, tokens: List[Token]) -> bool:
    if tp == OP and val in "|[]":
        return True

    if tp == STRING or tp == OP and val == ",":
        o, c = 0, 0
        for _, val in tokens:
            if val == "[":
                o += 1
            if val == "]":
                c += 1
        return o > c

    return False


class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
    def _buffer_decode(self, input, errors, final):  # pragma: no cover
        if not final:
            return "", 0

        return decode(input, errors)


def search_function(_: Any) -> codecs.CodecInfo:
    return codecs.CodecInfo(
        encode=utf_8.encode,
        decode=decode,  # type: ignore[arg-type]
        streamreader=utf_8.streamreader,
        streamwriter=utf_8.streamwriter,
        incrementalencoder=utf_8.incrementalencoder,
        incrementaldecoder=IncrementalDecoder,
        name="future_typing",
    )


def register():  # pragma: no cover
    codecs.register(search_function)
