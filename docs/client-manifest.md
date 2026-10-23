# Client manifest (.ismc)

The episodes are Smooth Streaming presentations. Their client manifest is an XML document that lists the streams of
an episode, the quality levels of each stream and the timeline of its fragments. The game downloads it from the URL
in [videoList.rmdj](videolist-rmdj.md). QuantumFetcher fetches the same manifest to find the tracks and the URLs of
their fragments, and saves a copy that offers only the downloaded tracks as `<episode ID>.ismc` in the episode
folder, which QuantumStreamer serves to the game instead of the server's.

## Layout

```xml
<SmoothStreamingMedia MajorVersion="2" MinorVersion="0" Duration="...">
  <StreamIndex Type="video" Url="QualityLevels({bitrate})/Fragments(video={start time})" ...>
    <QualityLevel Index="0" Bitrate="..." FourCC="H264" ... />
    ...
    <c d="..." />
    ...
  </StreamIndex>
  <StreamIndex Type="audio" Name="enus" Language="eng" Url="..." ...>
    ...
  </StreamIndex>
  <StreamIndex Type="text" Name="enus_captions" Language="eng" Url="..." ...>
    ...
  </StreamIndex>
</SmoothStreamingMedia>
```

Each `StreamIndex` is a stream, each of its `QualityLevel` elements a track: one quality of that stream, saved in its
own [track file](track-files.md). A track is known by its stream type, stream name and bitrate. The `c` elements give
the stream's fragments, which every quality level shares.

## Elements and attributes

QuantumFetcher reads these elements and attributes:

| Element                | Attribute               | Type                     | Use                                                                                                  |
|------------------------|-------------------------|--------------------------|------------------------------------------------------------------------------------------------------|
| `SmoothStreamingMedia` |                         |                          | The root element; any other root stops with `Expected a Smooth Streaming manifest, not <element>`    |
| `SmoothStreamingMedia` | `TimeScale`             | integer                  | Time units per second; default 10000000                                                              |
| `StreamIndex`          | `Type`                  | `video`, `audio`, `text` | The stream type; streams of other types are left out                                                 |
| `StreamIndex`          | `Name`                  | string                   | The stream name, such as `enus` or `enus_captions`; default the type, so the video stream is `video` |
| `StreamIndex`          | `Language`              | ISO 639-2 code           | The stream's language, such as `eng`; optional                                                       |
| `StreamIndex`          | `TimeScale`             | integer                  | The stream's own time units per second, instead of the root's                                        |
| `StreamIndex`          | `Url`                   | template                 | The fragment URL, relative to the manifest; required                                                 |
| `QualityLevel`         | `Bitrate`               | integer                  | Bits per second; required                                                                            |
| `QualityLevel`         | `FourCC`                | string                   | The codec: `H264` or `AVC1` for video, `AACL` for audio, `TTML` for captions                         |
| `QualityLevel`         | `CodecPrivateData`      | hexadecimal              | The codec setup: the H.264 parameter sets, each after a start code, or the AAC audio configuration   |
| `QualityLevel`         | `MaxWidth` or `Width`   | integer                  | The video width in pixels                                                                            |
| `QualityLevel`         | `MaxHeight` or `Height` | integer                  | The video height in pixels                                                                           |
| `QualityLevel`         | `SamplingRate`          | integer                  | Audio samples per second                                                                             |
| `QualityLevel`         | `Channels`              | integer                  | Audio channels; default 2 in the track header                                                        |
| `QualityLevel`         | `BitsPerSample`         | integer                  | Bits of each audio sample; default 16 in the track header                                            |
| `QualityLevel`         | `NALUnitLengthField`    | integer                  | Bytes of the size before each H.264 NAL unit; default 4                                              |
| `c`                    | `t`                     | integer                  | The fragment's start time; default the end of the fragment before it, 0 for the first                |
| `c`                    | `d`                     | integer                  | The fragment's duration; required                                                                    |
| `c`                    | `r`                     | integer                  | The number of fragments in a row with this duration; default 1                                       |

Other attributes, such as `Chunks`, `Subtype` and `DisplayWidth`, are not read. A document that is not XML, lacks a
required attribute or has a number that is not an integer is rejected with `Invalid manifest <URL>: ...`, and
`download` and `formats` skip that episode with a warning.

### Fragment URLs

| Placeholder in `Url`             | Replaced by                   |
|----------------------------------|-------------------------------|
| `{bitrate}`                      | The quality level's `Bitrate` |
| `{start time}` or `{start_time}` | The fragment's start time     |

Placeholders are matched in any letter case. The template is resolved against the manifest's URL, and the manifest's
query string is added to the result, as the game does. With the manifest at
`http://cdn.example/J1A.ism/manifest?tkn=1`, the `enus` fragment of the 256000 quality level that starts at 20000000
is at `http://cdn.example/J1A.ism/QualityLevels(256000)/Fragments(enus=20000000)?tkn=1`.

### Timeline

Each `c` element adds `r` fragments of duration `d`, the first one starting at `t` when it is given. The end of the
last fragment is the track's duration. For example, `<c t="100" d="10"/><c d="20" r="2"/><c d="5"/>` gives fragments
starting at 100, 110, 130 and 150, and a duration of 155.

The game asks for each fragment by these start times, and QuantumStreamer finds a downloaded fragment by the same
time in the track file's index.

## Local copy

`<episode ID>.ismc` is the server's manifest with these changes:

1. Every `QualityLevel` whose track has no file in the episode folder is removed.
2. Every `StreamIndex` left without quality levels is removed, as are streams of types other than video, audio and
   text.
3. The remaining quality levels of each stream are numbered again in `Index`, from 0, and `QualityLevels` gives their
   count.
4. `MaxWidth` and `MaxHeight` of a `StreamIndex`, where present, give the largest values of its remaining quality
   levels.

Everything else, the timeline and URLs included, stays as the server sent it. The file is UTF-8 with the declaration
`<?xml version='1.0' encoding='utf-8'?>`, indented with two spaces, with LF line ends and no line end after the root
element.

QuantumFetcher writes the local copy together with the [server manifest](server-manifest.md) once the episode folder
holds a video and an audio track of the episode, and writes both again at every download of that episode, so they
also offer the tracks of earlier downloads. Until then the episode keeps streaming from the server, since the game
plays only the tracks the local copy offers.

## Example

An invented episode `J1A` whose server manifest offers two video qualities, two audio streams and two caption streams,
in two fragments of two seconds each. After downloading the 500000 video, the `enus` audio and the `enus_captions`
captions, `J1A.ismc` holds:

```xml
<?xml version='1.0' encoding='utf-8'?>
<SmoothStreamingMedia MajorVersion="2" MinorVersion="0" Duration="40000000">
  <StreamIndex Type="video" Chunks="2" QualityLevels="1" MaxWidth="640" MaxHeight="360" DisplayWidth="1280" DisplayHeight="720" Url="QualityLevels({bitrate})/Fragments(video={start time})">
    <QualityLevel Index="0" Bitrate="500000" FourCC="H264" MaxWidth="640" MaxHeight="360" CodecPrivateData="000000016742C01EAB400000000168CE3C80" />
    <c n="0" d="20000000" />
    <c n="1" d="20000000" />
  </StreamIndex>
  <StreamIndex Type="audio" Name="enus" Language="eng" Chunks="2" QualityLevels="1" Url="QualityLevels({bitrate})/Fragments(enus={start time})">
    <QualityLevel Index="0" Bitrate="256000" FourCC="AACL" SamplingRate="48000" Channels="6" BitsPerSample="16" CodecPrivateData="11B0" />
    <c n="0" d="20000000" />
    <c n="1" d="20000000" />
  </StreamIndex>
  <StreamIndex Type="text" Name="enus_captions" Language="eng" Subtype="CAPT" Chunks="2" QualityLevels="1" Url="QualityLevels({bitrate})/Fragments(enus_captions={start time})">
    <QualityLevel Index="0" Bitrate="256000" FourCC="TTML" />
    <c n="0" d="20000000" />
    <c n="1" d="20000000" />
  </StreamIndex>
</SmoothStreamingMedia>
```

The 2000000 video quality level and the `esmx` and `eses_captions` streams are gone; the video stream's `MaxWidth`
and `MaxHeight` dropped from 1280x720 to the 640x360 of the remaining quality level.
