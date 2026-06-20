"""Test-only readline stub.

Some conda Python builds on macOS can segfault while importing the compiled
readline extension during pytest startup. Pytest only imports readline early
as an stdio-capture workaround, so an empty module is enough for tests.
"""
