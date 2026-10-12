import unittest
import xml.etree.ElementTree as ET

from quantumfetcher.errors import FetchError
from quantumfetcher.manifest import ClientManifest, StreamType, server_manifest
from support import CHUNK, MANIFEST_URL, PPS, SPS, client_manifest, fragment_url

SMIL = {"smil": "http://www.w3.org/2001/SMIL20/Language"}


class ClientManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ClientManifest.parse(MANIFEST_URL, client_manifest())

    def track(self, name, bitrate=256000):
        return next(
            track
            for track in self.manifest.tracks
            if (track.name, track.bitrate) == (name, bitrate)
        )

    def test_reads_a_track_for_each_quality_level(self):
        self.assertEqual(
            [
                (track.type, track.name, track.language, track.bitrate)
                for track in self.manifest.tracks
            ],
            [
                (StreamType.VIDEO, "video", None, 2_000_000),
                (StreamType.VIDEO, "video", None, 500_000),
                (StreamType.AUDIO, "enus", "eng", 256000),
                (StreamType.AUDIO, "esmx", "spa", 256000),
                (StreamType.TEXT, "enus_captions", "eng", 256000),
                (StreamType.TEXT, "eses_captions", "spa", 256000),
            ],
        )

    def test_reads_what_describing_a_track_needs(self):
        video, audio = self.track("video", 500_000), self.track("enus")
        self.assertEqual((video.fourcc, video.width, video.height), ("H264", 640, 360))
        self.assertEqual(video.codec_private_data, b"\0\0\0\1" + SPS + b"\0\0\0\1" + PPS)
        self.assertEqual(
            (audio.fourcc, audio.sampling_rate, audio.channels, audio.bits_per_sample),
            ("AACL", 48000, 6, 16),
        )
        self.assertEqual(audio.codec_private_data, b"\x11\xb0")
        self.assertEqual((audio.timescale, audio.duration), (10_000_000, 3 * CHUNK))

    def test_fragments_sit_next_to_the_manifest_and_keep_its_query(self):
        track = self.track("enus_captions")
        self.assertEqual(track.start_times, (0, CHUNK, 2 * CHUNK))
        self.assertEqual(track.fragment_url(CHUNK), fragment_url("enus_captions", 256000, CHUNK))

    def test_timeline_follows_durations_times_and_repeats(self):
        xml = (
            b'<SmoothStreamingMedia Duration="155"><StreamIndex Type="audio" Name="a" '
            b'Url="Q({bitrate})/F(a={start_time})"><QualityLevel Bitrate="1" FourCC="AACL"/>'
            b'<c t="100" d="10"/><c d="20" r="2"/><c d="5"/></StreamIndex></SmoothStreamingMedia>'
        )
        (track,) = ClientManifest.parse("http://cdn.test/a.ism/Manifest", xml).tracks
        self.assertEqual((track.start_times, track.duration), ((100, 110, 130, 150), 155))
        self.assertEqual(track.fragment_url(130), "http://cdn.test/a.ism/Q(1)/F(a=130)")

    def test_skips_streams_of_unknown_types(self):
        xml = b'<SmoothStreamingMedia><StreamIndex Type="data" Url="x"/></SmoothStreamingMedia>'
        self.assertEqual(ClientManifest.parse("http://cdn.test/m", xml).tracks, ())

    def test_rejects_invalid_manifests(self):
        broken = client_manifest().replace(b'Bitrate="500000"', b'Bitrate="fast"')
        for xml in (b"not xml", b"<html/>", broken):
            with self.subTest(xml=xml[:20]), self.assertRaises(FetchError):
                ClientManifest.parse(MANIFEST_URL, xml)

    def test_local_copy_offers_only_the_kept_tracks(self):
        kept = [self.track("video", 500_000), self.track("esmx"), self.track("enus_captions")]
        root = ET.fromstring(self.manifest.local_copy(kept))
        streams = root.findall("StreamIndex")
        self.assertEqual(
            [
                (stream.get("Type"), stream.get("Name"), stream.get("QualityLevels"))
                for stream in streams
            ],
            [("video", None, "1"), ("audio", "esmx", "1"), ("text", "enus_captions", "1")],
        )
        video = streams[0]
        (level,) = video.findall("QualityLevel")
        self.assertEqual((level.get("Index"), level.get("Bitrate")), ("0", "500000"))
        self.assertEqual((video.get("MaxWidth"), video.get("MaxHeight")), ("640", "360"))
        self.assertEqual(
            [chunk.attrib for chunk in video.findall("c")],
            [{"n": str(number), "d": str(CHUNK)} for number in range(3)],
        )

    def test_server_manifest_names_the_client_manifest_and_each_track_file(self):
        tracks = [self.track("video", 500_000), self.track("enus"), self.track("enus_captions")]
        files = [(track, f"{track.name}.file") for track in tracks]
        root = ET.fromstring(server_manifest("J1A.ismc", files))
        meta = root.find("smil:head/smil:meta[@name='clientManifestRelativePath']", SMIL)
        self.assertEqual(meta.get("content"), "J1A.ismc")
        elements = root.findall("smil:body/smil:switch/*", SMIL)
        self.assertEqual(
            [
                (
                    element.tag.split("}")[1],
                    element.get("src"),
                    element.get("systemBitrate"),
                    element.find("smil:param[@name='trackName']", SMIL).get("value"),
                )
                for element in elements
            ],
            [
                ("video", "video.file", "500000", "video"),
                ("audio", "enus.file", "256000", "enus"),
                ("textstream", "enus_captions.file", "256000", "enus_captions"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
