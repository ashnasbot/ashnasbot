from ._framework import *  # noqa
from ._common import chat_cmd

COMMANDS = {
    # Command          Show   Func
    '!chat':            (1, chat_cmd),
}
