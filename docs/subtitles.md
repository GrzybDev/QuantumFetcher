# Subtitles (.srt)

With `--extract-subtitles`, QuantumFetcher turns the TTML captions of each downloaded caption track into a SubRip
file named after the stream, such as `enus_captions.srt`, in the episode folder. QuantumStreamer shows the cues of
that file instead of the track's own captions, so the file can be edited or translated.

## Source: TTML captions

The `mdat` box of each fragment of a caption [track file](track-files.md) holds a TTML document in the
`http://www.w3.org/ns/ttml` namespace. QuantumFetcher reads its `p` elements:

| Part              | Use                                                                             |
|-------------------|---------------------------------------------------------------------------------|
| `begin`, `end`    | When the caption shows and hides, from the start of the fragment; both required |
| Text              | The text of the element and every element in it, such as `span`                 |
| `br`              | A line break                                                                    |
| Other line breaks | Left out, as they only lay out the document; each line is trimmed of spaces     |

| Time expression                              | Example                   | Meaning                                 |
|----------------------------------------------|---------------------------|-----------------------------------------|
| `<hours>:<minutes>:<seconds>`                | `00:00:01.250`, `0:01:02` | Clock time; seconds may have a fraction |
| `<number><unit>`, unit `h`, `m`, `s` or `ms` | `1.5s`, `1500ms`, `0.5m`  | Offset time                             |

A caption's time in the episode is its fragment's start time (from the track's index, divided by the stream's time
scale) plus its TTML time. A document that is not XML, a caption without `begin` or `end`, or another time expression
(such as frames, `10f`) leaves that track without subtitles. The episode's tracks and manifests stay saved, and the
download reports the subtitles it could not save.

## SubRip layout

```text
<number>
<start> --> <end>
<text line>
...

<number>
...
```

| Part      | Format                                     |
|-----------|--------------------------------------------|
| Number    | The cue's number, from 1                   |
| Times     | `HH:MM:SS,mmm`, rounded to the millisecond |
| Text      | One or more lines                          |
| Separator | An empty line between cues                 |

The file is UTF-8 without a byte order mark, with CRLF line ends; it ends with the line end of the last cue's text.

Before writing, QuantumFetcher sorts the cues by start time, leaves out cues without text and joins a cue to the one
before it when both have the same text and it starts less than 0.1 seconds after that one ends, since a caption that
spans two fragments comes in two pieces.

### Episode title

With `--append-episode-title`, the file also gets a cue with the episode's title from 00:00:07,500 to 00:00:09,833,
while the title card is on screen. The episode number follows the `J` that starts the episode ID, so `J1A` and
`J1A-X1` are episode 1; IDs with another number or none get no title.

| Number | Cue                                |
|-------:|------------------------------------|
|      1 | `EPISODE 1: Monarch Solutions`     |
|      2 | `EPISODE 2: Prisoner`              |
|      3 | `EPISODE 3: Deception`             |
|      4 | `EPISODE 4: The Lifeboat Protocol` |

## Existing files

QuantumFetcher never overwrites a `.srt` file, as it may hold edited or translated captions; it logs that it keeps
it. Delete the file to save it again.

QuantumStreamer reads every `.srt` file in the episode folder whose name contains `_captions`, and replaces the
captions of the stream named like the file without its extension. It expects the files in UTF-8.

## Example

Two caption fragments of an invented episode `J1A`, starting at 0 and 2 seconds:

```xml
<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="eng"><body><div>
  <p begin="00:00:00.500" end="00:00:01.750"><span>- Where were you?<br/>- Out.</span></p>
  <p begin="00:00:01.900" end="00:00:02.000">It is late.</p>
</div></body></tt>
```

```xml
<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="eng"><body><div>
  <p begin="0s" end="0.8s">It is late.</p>
</div></body></tt>
```

With `--append-episode-title`, `enus_captions.srt` holds the two pieces of the second caption as one cue:

```text
1
00:00:00,500 --> 00:00:01,750
- Where were you?
- Out.

2
00:00:01,900 --> 00:00:02,800
It is late.

3
00:00:07,500 --> 00:00:09,833
EPISODE 1: Monarch Solutions
```
