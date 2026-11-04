"""Length-prefixed text frames for the internal socket protocol.

A frame is a 2-byte big-endian length followed by that many bytes of UTF-8 text.
"""

HEADER_SIZE = 2
MAX_PAYLOAD = 65535


def encode_frame(text):
    """Encode ``text`` as one frame.

    The length field counts the bytes of the UTF-8 payload. A payload longer
    than MAX_PAYLOAD bytes raises ValueError.
    """
    payload = text.encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    return len(payload).to_bytes(HEADER_SIZE, "big") + payload


def decode_frame(data, offset=0):
    """Decode the frame starting at ``offset``; return (text, next_offset).

    Raises ValueError if ``data`` ends before the frame is complete.
    """
    body_start = offset + HEADER_SIZE
    if len(data) < body_start:
        raise ValueError("incomplete header")
    size = int.from_bytes(data[offset:body_start], "big")
    end = body_start + size
    if len(data) < end:
        raise ValueError("incomplete frame")
    return data[body_start:end].decode("utf-8"), end


def decode_stream(data):
    """Decode a buffer holding any number of consecutive frames into a list of texts."""
    texts = []
    offset = 0
    while offset < len(data):
        text, offset = decode_frame(data, offset)
        texts.append(text)
    return texts
