import os

''' Methods that are not part of the core language '''

class Os():

    ''' Statics for OS methods '''

    @staticmethod
    def _load(filename):
        ''' Load a source file '''
        raise NotImplementedError

    @staticmethod
    def _save(filename, sourcecode):
        ''' Save source to a file '''
        raise NotImplementedError

class Shell():

    ''' Statics for interactive mode '''

    @staticmethod
    def _list():
        raise NotImplementedError

    @staticmethod
    def _run():
        raise NotImplementedError

    @staticmethod
    def _clear():
        raise NotImplementedError
