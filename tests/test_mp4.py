import dataclasses
import io
import struct
import unittest

from quantumfetcher import mp4
from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest
from support import CHUNK, MANIFEST_URL, PPS, SPS, box, client_manifest, fragment


def children(data):
    return [kind for kind, _ in mp4.boxes(data)]


def find(data, *path):
    for kind in path:
        data = next(payload for child, payload in mp4.boxes(data) if child == kind)
    return bytes(data)


def quantumstreamer_index(data: bytes) -> dict[str, int]:
    """Read the mfra index the way QuantumStreamer's preloadTrack does."""
    mfro_size = struct.unpack(">I", data[-4:])[0]
    mfra = data[-mfro_size:]
    assert struct.unpack(">I", mfra[:4])[0] == mfro_size and mfra[4:8] == b"mfra"
    assert mfra[12:16] == b"tfra"
    version, (sizes, count) = mfra[16], struct.unpack(">II", mfra[24:32])
    entry = ">QQ" if version == 1 else ">II"
    numbers = ((sizes & 0x3F) >> 4) + ((sizes & 0xC) >> 2) + (sizes & 0x3) + 3
    position, index = 32, {}
    for _ in range(count):
        time, offset = struct.unpack_from(entry, mfra, position)
        position += struct.calcsize(entry) + numbers
        index[str(time)] = offset
    return index


class TrackFileTests(unittest.TestCase):
    def setUp(self):
        tracks = ClientManifest.parse(MANIFEST_URL, client_manifest()).tracks
        self.video, _, self.audio, _, self.text, _ = tracks
        self.fragments = [fragment(f"media {number}".encode() * 50) for number in range(3)]

    def write(self, track, fragments, file=None):
        file = file or io.BytesIO()
        writer = mp4.TrackWriter(file, track)
        for data in fragments[writer.fragments :]:
            writer.append(data)
        writer.finish()
        return file.getvalue()

    def test_header_describes_each_kind_of_track(self):
        for track, entry, handler in (
            (self.video, b"avc1", b"vide"),
            (self.audio, b"mp4a", b"soun"),
            (self.text, b"stpp", b"subt"),
        ):
            with self.subTest(track=track.type):
                header = mp4.track_header(track, 7)
                self.assertEqual(children(header), [b"ftyp", b"moov"])
                moov = find(header, b"moov")
                self.assertEqual(children(moov), [b"mvhd", b"trak", b"mvex"])
                stbl = find(moov, b"trak", b"mdia", b"minf", b"stbl")
                self.assertEqual(children(stbl), [b"stsd", b"stts", b"stsc", b"stsz", b"stco"])
                self.assertEqual(children(find(stbl, b"stsd")[8:]), [entry])
                self.assertEqual(find(moov, b"trak", b"mdia", b"hdlr")[8:12], handler)
                self.assertEqual(struct.unpack(">I", find(moov, b"trak", b"tkhd")[20:24]), (7,))
                self.assertEqual(struct.unpack(">I", find(moov, b"mvex", b"trex")[4:8]), (7,))

    def test_video_header_holds_the_parameter_sets(self):
        stbl = find(mp4.track_header(self.video, 1), b"moov", b"trak", b"mdia", b"minf", b"stbl")
        avc1 = find(find(stbl, b"stsd")[8:], b"avc1")
        self.assertEqual(struct.unpack(">HH", avc1[24:28]), (1280, 720))
        avcc = find(avc1[78:], b"avcC")
        self.assertEqual(avcc[:6], bytes([1, *SPS[1:4], 0xFF, 0xE1]))
        self.assertEqual(
            avcc[6:], struct.pack(">H", len(SPS)) + SPS + b"\1" + struct.pack(">H", len(PPS)) + PPS
        )

    def test_audio_header_holds_the_audio_configuration(self):
        stbl = find(mp4.track_header(self.audio, 1), b"moov", b"trak", b"mdia", b"minf", b"stbl")
        mp4a = find(find(stbl, b"stsd")[8:], b"mp4a")
        self.assertEqual(struct.unpack(">HHxxxxI", mp4a[16:28]), (6, 16, 48000 << 16))
        self.assertIn(b"\x05\x02\x11\xb0", find(mp4a[28:], b"esds"))

    def test_rejects_codecs_it_cannot_describe(self):
        for track in (
            dataclasses.replace(self.video, fourcc="WVC1"),
            dataclasses.replace(self.video, codec_private_data=b""),
        ):
            with self.subTest(track=track.fourcc), self.assertRaises(FetchError):
                mp4.track_header(track, 1)

    def test_index_gives_the_manifest_time_and_moof_offset_of_each_fragment(self):
        data = self.write(self.audio, self.fragments)
        index = quantumstreamer_index(data)
        self.assertEqual(list(index), ["0", str(CHUNK), str(2 * CHUNK)])
        for offset, expected in zip(index.values(), self.fragments, strict=True):
            self.assertEqual(data[offset : offset + len(expected)], expected)
        self.assertEqual(
            mp4.read_fragment_index(io.BytesIO(data)),
            [(int(time), offset) for time, offset in index.items()],
        )

    def test_reads_back_the_media_data_of_each_fragment(self):
        data = self.write(self.text, self.fragments)
        self.assertEqual(
            list(mp4.read_fragments(io.BytesIO(data))),
            [(number * CHUNK, f"media {number}".encode() * 50) for number in range(3)],
        )

    def test_carries_on_after_the_last_whole_fragment(self):
        whole = self.write(self.video, self.fragments)
        offsets = list(quantumstreamer_index(whole).values())
        kept = {
            offsets[2] - 5: (1, offsets[1]),
            offsets[2]: (2, offsets[2]),
            offsets[2] + 30: (2, offsets[2]),
        }
        for cut, expected in kept.items():
            with self.subTest(cut=cut):
                file = io.BytesIO(whole[:cut])
                writer = mp4.TrackWriter(file, self.video)
                self.assertEqual((writer.fragments, writer.size), expected)
                self.assertEqual(self.write(self.video, self.fragments, file), whole)

    def test_starts_over_without_a_whole_fragment(self):
        whole = self.write(self.video, self.fragments)
        header = len(mp4.track_header(self.video, 1))
        for cut in (0, 3, header, header + 50):
            with self.subTest(cut=cut):
                writer = mp4.TrackWriter(io.BytesIO(whole[:cut]), self.video)
                self.assertEqual((writer.fragments, writer.size), (0, 0))

    def test_drops_an_index_written_before_an_interruption(self):
        whole = self.write(self.audio, self.fragments)
        writer = mp4.TrackWriter(io.BytesIO(whole), self.audio)
        self.assertEqual(writer.fragments, 3)
        self.assertEqual(self.write(self.audio, self.fragments, io.BytesIO(whole)), whole)

    def test_finishes_only_with_every_fragment(self):
        with self.assertRaisesRegex(FetchError, "2 fragments but the manifest lists 3"):
            self.write(self.audio, self.fragments[:2])

    def test_rejects_what_is_not_a_fragment(self):
        writer = mp4.TrackWriter(io.BytesIO(), self.audio)
        moof = box(b"moof", box(b"mfhd", bytes(8)))
        for data in (b"<html>", box(b"mdat", b"x"), moof + box(b"mdat"), self.fragments[0][:-1]):
            with self.subTest(data=data[:12]), self.assertRaises(FetchError):
                writer.append(data)

    def test_rejects_files_without_an_index(self):
        for data in (b"", b"short", bytes(64)):
            with self.subTest(data=data), self.assertRaises(FetchError):
                mp4.read_fragment_index(io.BytesIO(data))


if __name__ == "__main__":
    unittest.main()
