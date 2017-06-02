"""
The `webfriend.scripting` module implements a simplistic, straightforward scripting environment
for automating various tasks within the Chromium web browser.

## Overview

The commands implemented in this
module provide simplified, opinionated implementations of common tasks such as loading URLs,
parsing and extracting information from the DOM, injecting and executing Javascript into pages, and
capturing web page screenshots.

## Scripting

Scripts consist of plain text files containing a sequence of commands that are executed in the
order they are written.  Return values of each command are stored after the command executes,
allowing subsequent commands to access useful details about the evaluation of previous commands.

If a command experiences an error the error is either raised as a fatal exception, causing the
script to terminate without evaluating the remaining commands, or the error is specified as
non-fatal.  Non-fatal errors are stored and are accessible to the remaining commands and can be
used to make decisions.
"""

from __future__ import absolute_import
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)  # noqa

from .parser import Friendscript, CommandSequence, IfElseBlock, LoopBlock
from .proxy import CommandProxy, CommandSet
from .scope import Scope
import logging
import gevent
import time
import inspect
from .commands import *  # noqa

PROXIES = dict([(p.as_qualifier(), p) for _, p in ALL_PROXIES])  # noqa
EXEC_OPTIONS = {}


class SyntaxError(Exception):
    pass


def load_and_register_proxy(module, name=None, browser=None, commandset=None):
    mod = __import__(module, fromlist=['*'])

    classes = [
        m[0] for m in inspect.getmembers(mod, inspect.isclass) if m[1].__module__ == module
    ]

    for c in classes:
        if issubclass(c, CommandProxy):
            register_proxy(c.as_qualifier(), c)

            if browser and commandset:
                commandset[c.as_qualifier()] = c(browser, commandset=commandset)


def register_proxy(name, proxy_cls):
    if name in PROXIES:
        raise AttributeError("Proxy '{}' is already registered".format(name))

    if not issubclass(proxy_cls, CommandProxy):
        raise ValueError("Proxy class must be a subclass of CommandProxy")

    PROXIES[name] = proxy_cls

    return PROXIES[name]


def get_all_proxy_commands():
    return CommandSet(proxies=PROXIES).get_command_names()


def execute_script(browser, script, scope=None):
    # setup a new scope if we weren't given one
    if not scope:
        scope = Scope()

    # setup the commandset
    commandset = CommandSet(scope)
    callbacks = set()

    # initalize proxy instances with a common scope
    for name, proxy_cls in PROXIES.items():
        commandset[name] = proxy_cls(browser, commandset=commandset)

    # load and parse the script
    instructions = Friendscript(data=script)

    # tell the commandset about the calling script
    commandset.script = instructions

    # zero out the initial result if it's not there already
    if commandset.default_result_key not in scope:
        scope[commandset.default_result_key] = None

    # show the initial state
    for k, v in scope.items():
        logging.debug('VAR: {}={}'.format(k, v))

    # setup event handlers for this execution
    for handler in instructions.handlers:
        callback_id = browser.default.on(
            handler.pattern,
            _handle_event(handler, commandset, scope)
        )

        logging.debug('Add event handler {}'.format(callback_id))
        callbacks.add(callback_id)

    # enable event reporting now
    browser.default.enable_events()

    # Script Execution starts NOW
    # ---------------------------------------------------------------------------------------------
    try:
        # recursively evaluate all blocks and nested blocks starting from the top level
        for block in instructions.blocks:
            evaluate_block(commandset, block, scope)

    finally:
        # unregister the event handlers we created for this run
        for callback_id in callbacks:
            logging.debug('Remove event handler {}'.format(callback_id))
            browser.default.remove_handler(callback_id)

    # ...and done.
    # ---------------------------------------------------------------------------------------------

    # return the final state after script execution
    return scope


def evaluate_block(commandset, block, scope):
    # Commands
    # ---------------------------------------------------------------------------------------------
    if isinstance(block, CommandSequence):
        # for each command in the pipeline...
        for command in block.commands:
            key, value = commandset.execute(command, scope)

            if key != 'null':
                scope.set(key, value, force=True)

            # perform delay if we have one
            if commandset.has_execution_option('demo.post_command_delay'):
                delay = commandset.get_execution_option('demo.post_command_delay')
                time.sleep(delay / 1e3)

    # If / Else If / Else
    # ---------------------------------------------------------------------------------------------
    elif isinstance(block, IfElseBlock):
        subscope = Scope(parent=scope)

        for subblock in block.get_blocks(commandset, scope=subscope):
            evaluate_block(commandset, subblock, subscope)

    # Loops
    # ---------------------------------------------------------------------------------------------
    elif isinstance(block, LoopBlock):
        loopscope = Scope(parent=scope)

        for i, _, subblock, scope in block.execute_loop(commandset, scope=loopscope):
            evaluate_block(commandset, subblock, scope=scope)


def _handle_event(handler, commandset, scope):
    def handle(e):
        def actual(event):
            local_scope_data = {
                'event': event,
            }

            if handler.isolated:
                local_scope = Scope(local_scope_data)
            else:
                local_scope = Scope(local_scope_data, scope)

            # execute all commands, accumulating output into the local state
            for sequence in handler.sequences:
                for command in sequence.commands:
                    key, value = commandset.execute(command, local_scope)

                    # setting the resultkey to "null" explicitly discards the result
                    if key != 'null':
                        local_scope[key] = value

            return local_scope

        gevent.spawn(actual, e)

    return handle
