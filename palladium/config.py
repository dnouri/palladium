from copy import deepcopy
import logging
from logging.config import dictConfig
import os
import sys


PALLADIUM_CONFIG_ERROR = """
  Maybe you forgot to set the environment variable PALLADIUM_CONFIG
  to point to your Palladium configuration file?  If so, please
  refer to the manual for more details.
"""


class Config(dict):
    """A dictionary that represents the app's configuration.

    Tries to send a more user friendly message in case of KeyError.
    """
    initialized = False

    def __getitem__(self, name):
        try:
            return super(Config, self).__getitem__(name)
        except KeyError:
            raise KeyError(
                "The required key '{}' was not found in your "
                "configuration. {}".format(name, PALLADIUM_CONFIG_ERROR))


_config = Config()


def get_config(**extra):
    if not _config.initialized:
        _config.update(extra)
        _config.initialized = True
        fnames = os.environ.get('PALLADIUM_CONFIG')
        if fnames is not None:
            fnames = [fname.strip() for fname in fnames.split(',')]
            sys.path.insert(0, os.path.dirname(fnames[0]))
            for fname in fnames:
                with open(fname) as f:
                    _config.update(
                        eval(f.read(), {'environ': os.environ})
                        )
            _initialize_config(_config)

    return _config


def initialize_config(**extra):
    if _config.initialized:
        raise RuntimeError("Configuration was already initialized")
    return get_config(**extra)


def _initialize_config_recursive(props, handlers):
    if isinstance(props, dict):
        for key, value in tuple(props.items()):
            if isinstance(value, dict):
                _initialize_config_recursive(value, handlers)
                for name, handler in handlers.items():
                    if name in value:
                        props[key] = handler(value)
            elif isinstance(value, (list, tuple)):
                _initialize_config_recursive(value, handlers)
    elif isinstance(props, (list, tuple)):
        for i, item in enumerate(props):
            if isinstance(item, dict):
                _initialize_config_recursive(item, handlers)
                for name, handler in handlers.items():
                    if name in item:
                        props[i] = handler(item)
            elif isinstance(item, (list, tuple)):
                _initialize_config_recursive(item, handlers)


class ComponentHandler:
    key = '__factory__'

    def __init__(self, config):
        self.config = config
        self.components = []

    def __call__(self, specification):
        from .util import resolve_dotted_name
        specification = specification.copy()
        factory_dotted_name = specification.pop(self.key)
        factory = resolve_dotted_name(factory_dotted_name)
        component = factory(**specification)
        self.components.append(component)
        return component

    def finish(self):
        for component in self.components:
            if hasattr(component, 'initialize_component'):
                component.initialize_component(self.config)


class CopyHandler:
    key = '__copy__'

    def __init__(self, config):
        self.config = config

    def __call__(self, props):
        dotted_path = props.pop(self.key)
        value = self.config
        for part in dotted_path.split('.'):
            value = value[part]
        value = deepcopy(value)
        if props:
            value.update(props)
        return value


class PythonHandler:
    key = '__python__'

    def __init__(self, config):
        self.config = config

    def __call__(self, props):
        statements = props.pop(self.key)
        if isinstance(statements, list):
            statements = '\n'.join(statements)
        exec(statements, globals(), {'config': self.config})
        return props


def _handlers_phase1(config):
    return {
        Handler.key: Handler(config) for Handler in [
            CopyHandler,
            PythonHandler,
            ]
        }


def _handlers_phase2(config):
    return {
        Handler.key: Handler(config) for Handler in [
            ComponentHandler,
            ]
        }


def _initialize_config(config, handlers1=None, handlers2=None):
    if 'logging' in config:
        dictConfig(config['logging'])
    else:
        logging.basicConfig(level=logging.DEBUG)

    for handlers in [_handlers_phase1(config), _handlers_phase2(config)]:
        _initialize_config_recursive(config, handlers)
        for handler in handlers.values():
            if hasattr(handler, 'finish'):
                handler.finish()

    return config
