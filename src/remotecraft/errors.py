"""Domain errors that can be translated into stable API responses."""


class RemoteCraftError(RuntimeError):
    """Base class for expected application errors."""

    code = "remotecraft_error"
    status_code = 500


class ConfigurationError(RemoteCraftError):
    code = "configuration_error"
    status_code = 500


class InvalidRequestError(RemoteCraftError):
    code = "invalid_request"
    status_code = 422


class NotFoundError(RemoteCraftError):
    code = "not_found"
    status_code = 404


class ConflictError(RemoteCraftError):
    code = "conflict"
    status_code = 409


class RemoteCommandError(RemoteCraftError):
    code = "remote_command_failed"
    status_code = 502


class StoreError(RemoteCraftError):
    code = "store_error"
    status_code = 500


class UpstreamError(RemoteCraftError):
    code = "upstream_error"
    status_code = 502
