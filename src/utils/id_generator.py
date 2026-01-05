"""ID generation utilities for LibreChat compatibility."""

import secrets
import string


def generate_nanoid(length: int = 21) -> str:
    """
    Generate a nanoid-style ID compatible with LibreChat validation and Kubernetes labels.

    LibreChat expects IDs that are exactly 21 characters long and contain
    only letters (A-Z, a-z), numbers (0-9), underscores (_), and hyphens (-).

    Kubernetes labels require the first and last characters to be alphanumeric,
    so we ensure IDs always start and end with a letter or number.

    Args:
        length: Length of the ID to generate (default: 21 for LibreChat compatibility)

    Returns:
        A string ID that matches LibreChat's validation pattern: /^[A-Za-z0-9_-]{21}$/
        and is also valid as a Kubernetes label value.
    """
    alphanumeric = string.ascii_letters + string.digits
    full_alphabet = alphanumeric + "_-"

    if length == 1:
        return secrets.choice(alphanumeric)
    elif length == 2:
        return secrets.choice(alphanumeric) + secrets.choice(alphanumeric)

    # First and last chars must be alphanumeric for Kubernetes label compatibility
    first = secrets.choice(alphanumeric)
    middle = "".join(secrets.choice(full_alphabet) for _ in range(length - 2))
    last = secrets.choice(alphanumeric)
    return first + middle + last


def generate_session_id() -> str:
    """Generate a session ID compatible with LibreChat."""
    return generate_nanoid(21)


def generate_file_id() -> str:
    """Generate a file ID compatible with LibreChat."""
    return generate_nanoid(21)


def generate_execution_id() -> str:
    """Generate an execution ID compatible with LibreChat."""
    return generate_nanoid(21)


def generate_request_id() -> str:
    """Generate a request ID for error tracking."""
    return generate_nanoid(21)
