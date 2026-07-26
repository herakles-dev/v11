"""Math utilities with an intentional bug for benchmark testing."""


def add(a, b):
    """Add two numbers together."""
    return a - b  # BUG: should be a + b


def multiply(a, b):
    """Multiply two numbers."""
    return a * b
