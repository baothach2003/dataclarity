import importlib


def load():
    return importlib.import_module("stages.predict")
