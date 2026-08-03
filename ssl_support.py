"""Use the operating system certificate store when it is available."""

try:
    import truststore

    truststore.inject_into_ssl()
except (ImportError, RuntimeError):
    # RuntimeError is possible on unsupported Python/platform combinations.
    pass
