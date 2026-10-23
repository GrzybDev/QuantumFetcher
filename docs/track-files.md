# Track files (.ismv, .isma, .ismt)

QuantumFetcher saves each downloaded track, one quality level of a stream in the
[client manifest](client-manifest.md), as a fragmented MP4 file in the episode folder: a header that describes the
track, the track's fragments as the server sent them, and an `mfra` index of when and where each fragment starts.
QuantumStreamer serves the fragments from the index, and the header lets media players open the file on its own.

## Names

| Track    | File name                                   | Example                         |
|----------|---------------------------------------------|---------------------------------|
| Video    | `<episode ID>_video_<bitrate>.ismv`         | `J1A_video_12000000.ismv`       |
| Audio    | `<episode ID>_<stream name>_<bitrate>.isma` | `J1A_enus_256000.isma`          |
| Captions | `<episode ID>_<stream name>_<bitrate>.ismt` | `J1A_enus_captions_256000.ismt` |

While a track downloads, its file is `<file name>.part`; it gets its name once the index is written. A track whose
file exists is not downloaded again. Older versions of QuantumFetcher named the track files differently, so their
tracks are downloaded again under these names.

## Layout

```text
ftyp                      file type
moov                      track header
  mvhd
  trak
    tkhd
    mdia
      mdhd
      hdlr
      minf
        vmhd, smhd or sthd
        dinf
          dref
            url
        stbl
          stsd
            avc1 (with avcC), mp4a (with esds) or stpp
          stts, stsc, stsz, stco
  mvex
    mehd
    trex
moof, mdat                first fragment
moof, mdat                second fragment
...
mfra                      fragment index
  tfra
  mfro
```

Every box starts with its size in bytes (a 32-bit unsigned integer that counts the whole box) and its four-letter
type. A full box follows them with a version (8 bits) and flags (24 bits). All numbers are big-endian. QuantumFetcher
writes 32-bit sizes and reads 64-bit ones (size 1) too.

## Header

The header describes the one track of the file with the values from the client manifest: the stream's time scale,
its duration (the end of its last fragment) and the quality level's codec setup. Its track ID is the one the first
fragment's `tfhd` gives. Offsets below count from the start of each box. Fields not listed are zero.

### ftyp

| Offset | Type       | Value                               |
|-------:|------------|-------------------------------------|
|      8 | char[4]    | Major brand `isml`                  |
|     12 | uint32     | Minor version 1                     |
|     16 | char[4][2] | Compatible brands `piff` and `iso2` |

### moov boxes

| Box                    | Version, flags | Offset | Type      | Value                                                                                     |
|------------------------|----------------|-------:|-----------|-------------------------------------------------------------------------------------------|
| `mvhd`                 | 1, 0           |     28 | uint32    | Time scale                                                                                |
|                        |                |     32 | uint64    | Duration                                                                                  |
|                        |                |     40 | uint32    | Rate 0x00010000 (1.0)                                                                     |
|                        |                |     44 | uint16    | Volume 0x0100 (1.0)                                                                       |
|                        |                |     56 | int32[9]  | Unity matrix                                                                              |
|                        |                |    116 | uint32    | Next track ID: the track ID + 1                                                           |
| `tkhd`                 | 1, 7           |     28 | uint32    | Track ID                                                                                  |
|                        |                |     36 | uint64    | Duration                                                                                  |
|                        |                |     56 | uint16    | Volume: 0x0100 for audio, 0 otherwise                                                     |
|                        |                |     60 | int32[9]  | Unity matrix                                                                              |
|                        |                |     96 | uint32    | Width, 16.16 fixed point; 0 for audio and captions                                        |
|                        |                |    100 | uint32    | Height, 16.16 fixed point; 0 for audio and captions                                       |
| `mdhd`                 | 1, 0           |     28 | uint32    | Time scale                                                                                |
|                        |                |     32 | uint64    | Duration                                                                                  |
|                        |                |     40 | uint16    | Language: three 5-bit letters, each its ASCII code minus 0x60; `und` without a valid code |
| `hdlr`                 | 0, 0           |     16 | char[4]   | Handler: `vide`, `soun` or `subt`                                                         |
|                        |                |     32 | string    | `VideoHandler`, `SoundHandler` or `SubtitleHandler`, ending with a zero byte              |
| `vmhd`                 | 0, 1           |     12 | 8 bytes   | Graphics mode and colour: zero (video)                                                    |
| `smhd`                 | 0, 0           |     12 | 4 bytes   | Balance: zero (audio)                                                                     |
| `sthd`                 | 0, 0           |        |           | No fields (captions)                                                                      |
| `dref`                 | 0, 0           |     12 | uint32    | 1 entry: a `url ` full box with flags 1, the media being in this file                     |
| `stsd`                 | 0, 0           |     12 | uint32    | 1 entry: the sample entry below                                                           |
| `stts`, `stsc`, `stco` | 0, 0           |     12 | uint32    | 0 entries                                                                                 |
| `stsz`                 | 0, 0           |     12 | uint32[2] | Sample size 0 and 0 samples                                                               |
| `mehd`                 | 1, 0           |     12 | uint64    | Duration                                                                                  |
| `trex`                 | 0, 0           |     12 | uint32    | Track ID                                                                                  |
|                        |                |     16 | uint32    | Default sample description 1                                                              |

The `tkhd` flags mark the track as enabled, in the movie and in its preview. The sample tables are empty because
the fragments describe the samples.

### Sample entries

Each sample entry starts with six reserved bytes and data reference index 1 (uint16 at offset 14).

| Entry  | Offset | Type      | Value                                                                                                |
|--------|-------:|-----------|------------------------------------------------------------------------------------------------------|
| `avc1` |     32 | uint16    | Width                                                                                                |
|        |     34 | uint16    | Height                                                                                               |
|        |     36 | uint32[2] | Resolution 0x00480000 (72 dpi) across and down                                                       |
|        |     48 | uint16    | Frame count 1                                                                                        |
|        |     82 | uint16    | Depth 0x0018                                                                                         |
|        |     84 | int16     | -1                                                                                                   |
|        |     86 | box       | `avcC`                                                                                               |
| `mp4a` |     24 | uint16    | Channels; 2 when the manifest gives none                                                             |
|        |     26 | uint16    | Bits per sample; 16 when the manifest gives none                                                     |
|        |     32 | uint32    | Sampling rate, 16.16 fixed point                                                                     |
|        |     36 | box       | `esds`                                                                                               |
| `stpp` |     16 | string    | Namespace `http://www.w3.org/ns/ttml`, then empty schema and MIME type strings, each zero-terminated |

`avcC` holds version 1, the profile, compatibility and level bytes of the first sequence parameter set,
`0xFC` | (NAL unit length - 1), `0xE0` | the number of sequence parameter sets, each set with a 16-bit length, then the
number of picture parameter sets and each of them with a 16-bit length. The sets come from `CodecPrivateData`, where
each NAL unit follows a `00 00 01` or `00 00 00 01` start code; type 7 is a sequence and type 8 a picture parameter
set.

`esds` (a full box, version 0) holds MPEG-4 descriptors, each a tag byte, its length in 7-bit groups and its content:

| Tag  | Descriptor               | Content                                                                                                                                        |
|------|--------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| 0x03 | Elementary stream        | ID 0 (uint16) and flags 0, then 0x04 and 0x06                                                                                                  |
| 0x04 | Decoder configuration    | Object type 0x40 (MPEG-4 audio), stream type byte 0x15 (audio), buffer size 0, maximum and average bitrate (uint32, from `Bitrate`), then 0x05 |
| 0x05 | Decoder-specific info    | `CodecPrivateData`: the AAC audio configuration                                                                                                |
| 0x06 | Sync layer configuration | Predefined 2                                                                                                                                   |

Only these codecs can be described; a track in another one stops its episode with
`Cannot describe <type> tracks in <codec>`, and video codec data without both parameter sets stops it with
`The video codec data lacks a sequence or picture parameter set`.

## Fragments

Each fragment is stored exactly as the server sent it: a `moof` box followed by its `mdat` box, in the order of the
timeline. QuantumFetcher rejects a fragment that is anything else, and reads the track ID from `moof/traf/tfhd`. The
`mdat` of a caption fragment holds a TTML document (see [Subtitles](subtitles.md)).

## Fragment index

The file ends with an `mfra` box that indexes every fragment:

| Box    | Version, flags | Offset | Type    | Value                                                                 |
|--------|----------------|-------:|---------|-----------------------------------------------------------------------|
| `tfra` | 1, 0           |     12 | uint32  | Track ID                                                              |
|        |                |     16 | uint32  | Sizes of the traf, trun and sample numbers: 0, so each takes one byte |
|        |                |     20 | uint32  | Number of entries: one for each fragment                              |
|        |                |     24 | entries | 19 bytes each, below                                                  |
| `mfro` | 0, 0           |     12 | uint32  | Size of the whole `mfra` box                                          |

| Entry offset | Type   | Value                                                                                     |
|-------------:|--------|-------------------------------------------------------------------------------------------|
|            0 | uint64 | The fragment's start time from the client manifest's timeline, in the stream's time scale |
|            8 | uint64 | The offset of the fragment's `moof` box from the start of the file                        |
|           16 | uint8  | traf number 1                                                                             |
|           17 | uint8  | trun number 1                                                                             |
|           18 | uint8  | Sample number 1                                                                           |

QuantumStreamer reads the `mfra` size from the last four bytes of the file, then the `tfra` entries, and serves the
`moof` and `mdat` at the offset whose time equals the start time the game asks for. QuantumFetcher reads the index
back the same way, to read the captions of a downloaded track; it also reads version 0 entries (32-bit times and
offsets) and larger traf, trun and sample numbers.

## Downloading and resuming

QuantumFetcher fetches several fragments of a track at once and appends them to the `.part` file in timeline order,
writing the header before the first one. It writes the index only once the file holds as many fragments as the
timeline lists, and otherwise stops the episode with `The file has <n> fragments but the manifest lists <m>`.

When a `.part` file is left from an interrupted download, QuantumFetcher keeps its header and every whole
`moof`/`mdat` pair, cuts off whatever follows them (a fragment cut short, or an index written before the
interruption) and carries on with the next fragment. Without a whole fragment it starts the file over.

## Example

The audio track `J1A_enus_256000.isma` of an invented episode: one AAC stream `enus` at 256000 bits per second, with
a time scale of 10000000 and two fragments of two seconds whose `mdat` boxes hold placeholder bytes. Offsets and
sizes are in bytes:

```text
offset  size  box
     0    24  ftyp
    24   624  moov
    32   120    mvhd
   152   436    trak
   160   104      tkhd
   264   324      mdia
   272    44        mdhd
   316    45        hdlr
   361   227        minf
   369    16          smhd
   385    36          dinf
   421   167          stbl
   429    91            stsd (mp4a with esds)
   520    16            stts
   536    16            stsc
   552    20            stsz
   572    16            stco
   588    60    mvex
   648    48  moof          fragment starting at 0
   696    90  mdat
   786    48  moof          fragment starting at 20000000
   834    97  mdat
   931    86  mfra
   939    62    tfra
  1001    16    mfro
```

The `mfra` box, from offset 931 to the end of the file:

```text
00 00 00 56 6d 66 72 61                      mfra, 86 bytes
00 00 00 3e 74 66 72 61 01 00 00 00          tfra, 62 bytes, version 1
00 00 00 01                                  track ID 1
00 00 00 00                                  one-byte traf, trun and sample numbers
00 00 00 02                                  2 entries
00 00 00 00 00 00 00 00                      time 0
00 00 00 00 00 00 02 88                      moof at 648
01 01 01                                     traf 1, trun 1, sample 1
00 00 00 00 01 31 2d 00                      time 20000000
00 00 00 00 00 00 03 12                      moof at 786
01 01 01                                     traf 1, trun 1, sample 1
00 00 00 10 6d 66 72 6f 00 00 00 00          mfro, 16 bytes
00 00 00 56                                  mfra size 86
```

When the game asks for `Fragments(enus=20000000)` at bitrate 256000, QuantumStreamer serves the 145 bytes from offset
786: the second `moof` and its `mdat`.
