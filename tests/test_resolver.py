#! /usr/bin/env python3
import pytest

from audio_feeder import resolver as afr


###
#  Resolver tests
#
def test_resolver_construction():
    # Just test that we can actually make a resolver without throwing an error
    afr.Resolver()


###
# get_resolver tests


def test_get_resolver_is():
    r1 = afr.get_resolver()
    r2 = afr.get_resolver()

    assert r1 is r2
