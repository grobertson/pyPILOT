# -*- coding: utf-8 -*-
from .helpers import Os, Shell


class PilotCore():

    ''' Base implementation of PILOT '''

    def load(filename):
        """Load a PILOT program from a file..."""
        source = Os._load(filename)

    def save(filename, sourcecode):
        """Save a PILOT program to a file..."""
        result = Os._save(filename, sourcecode)


    def __init__(self, *args, **kwargs):
        pass

    def _a(self, *args):
        ''' A: (Answer)'''
        raise NotImplementedError

    def _r(self, *args):
        ''' R: (Remark)'''
        raise NotImplementedError

    def _c(self, *args):
        ''' C: (Compute)'''
        raise NotImplementedError

    def _t(self, *args):
        ''' T: (Type)'''
        raise NotImplementedError

    def _m(self, *args):
        ''' M: (Match)'''
        raise NotImplementedError

    def _y(self, *args):
        ''' Y: (Yes)'''
        raise NotImplementedError

    def _n(self, *args):
        ''' N: (No)'''
        raise NotImplementedError

    def _j(self, *args):
        ''' J: (Jump)'''
        raise NotImplementedError

    def _u(self, *args):
        ''' U: (Use)'''
        raise NotImplementedError

    def _e(self, *args):
        ''' E: (End ("Subroutine" called by "U"se))'''
        raise NotImplementedError
