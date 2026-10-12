import struct

MANIFEST_URL = "http://cdn.test/quantum/J1A.ism/manifest?tkn=secret"
CHUNK = 20_000_000
SPS = bytes.fromhex("6742c01eab40")
PPS = bytes.fromhex("68ce3c80")
VIDEO = {2_000_000: (1280, 720), 500_000: (640, 360)}
AUDIO = {"enus": "eng", "esmx": "spa"}
TEXT = {"enus_captions": "eng", "eses_captions": "spa"}
KEY = bytes.fromhex("ba7abb27039b72fd13eb70387e0fcb41e1d0eb54be8f136df0bae22adcfb40f1")


def encrypt(data: bytes) -> bytes:
    return bytes(byte ^ KEY[index % len(KEY)] for index, byte in enumerate(data))


def client_manifest(chunks: int = 3) -> bytes:
    """A client manifest shaped like the episodes' own, with every chunk lasting CHUNK."""
    timeline = "".join(f'<c n="{number}" d="{CHUNK}"/>' for number in range(chunks))
    codec = (b"\0\0\0\1" + SPS + b"\0\0\0\1" + PPS).hex().upper()
    levels = "".join(
        f'<QualityLevel Index="{index}" Bitrate="{bitrate}" FourCC="H264" MaxWidth="{width}" '
        f'MaxHeight="{height}" CodecPrivateData="{codec}"/>'
        for index, (bitrate, (width, height)) in enumerate(VIDEO.items())
    )
    streams = [
        f'<StreamIndex Type="video" Chunks="{chunks}" QualityLevels="{len(VIDEO)}" '
        'MaxWidth="1280" MaxHeight="720" DisplayWidth="1280" DisplayHeight="720" '
        f'Url="QualityLevels({{bitrate}})/Fragments(video={{start time}})">{levels}{timeline}'
        "</StreamIndex>"
    ]
    for name, language in AUDIO.items():
        streams.append(
            f'<StreamIndex Type="audio" Name="{name}" Language="{language}" Chunks="{chunks}" '
            f'QualityLevels="1" Url="QualityLevels({{bitrate}})/Fragments({name}={{start time}})">'
            '<QualityLevel Index="0" Bitrate="256000" FourCC="AACL" SamplingRate="48000" '
            f'Channels="6" BitsPerSample="16" CodecPrivateData="11B0"/>{timeline}</StreamIndex>'
        )
    for name, language in TEXT.items():
        streams.append(
            f'<StreamIndex Type="text" Name="{name}" Language="{language}" Subtype="CAPT" '
            f'Chunks="{chunks}" QualityLevels="1" '
            f'Url="QualityLevels({{bitrate}})/Fragments({name}={{start time}})">'
            f'<QualityLevel Index="0" Bitrate="256000" FourCC="TTML"/>{timeline}</StreamIndex>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?><SmoothStreamingMedia MajorVersion="2" '
        f'MinorVersion="0" Duration="{chunks * CHUNK}">{"".join(streams)}</SmoothStreamingMedia>'
    ).encode()


def fragment_url(name: str, bitrate: int, start_time: int) -> str:
    return (
        "http://cdn.test/quantum/J1A.ism/"
        f"QualityLevels({bitrate})/Fragments({name}={start_time})?tkn=secret"
    )


def box(kind: bytes, *payload: bytes) -> bytes:
    content = b"".join(payload)
    return struct.pack(">I4s", 8 + len(content), kind) + content


def fragment(payload: bytes, track_id: int = 1) -> bytes:
    """A movie fragment like the server sends: moof with mfhd and traf/tfhd, then mdat."""
    tfhd = box(b"tfhd", struct.pack(">II", 0, track_id))
    moof = box(b"moof", box(b"mfhd", struct.pack(">II", 0, 1)), box(b"traf", tfhd))
    return moof + box(b"mdat", payload)
