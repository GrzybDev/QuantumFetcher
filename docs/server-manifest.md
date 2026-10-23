# Server manifest (.ism)

`<episode ID>.ism` in the episode folder is a SMIL document that tells QuantumStreamer which
[client manifest](client-manifest.md) to serve to the game and which file holds each downloaded track. QuantumStreamer
loads it when the game starts and serves the episode from the files it names.

## Layout

```xml
<smil xmlns="http://www.w3.org/2001/SMIL20/Language">
  <head>
    <meta name="clientManifestRelativePath" content="<episode ID>.ismc" />
  </head>
  <body>
    <switch>
      <video|audio|textstream src="<track file>" systemBitrate="<bitrate>" systemLanguage="<language>">
        <param name="trackName" value="<stream name>" valuetype="data" />
      </video|audio|textstream>
      ...
    </switch>
  </body>
</smil>
```

| Element                          | Attribute        | Value                                                                     |
|----------------------------------|------------------|---------------------------------------------------------------------------|
| `smil`                           | `xmlns`          | `http://www.w3.org/2001/SMIL20/Language`                                  |
| `head/meta`                      | `name`           | `clientManifestRelativePath`                                              |
| `head/meta`                      | `content`        | The client manifest's file name, relative to the episode folder           |
| `video`, `audio` or `textstream` |                  | One element for each track file, by the stream type: video, audio or text |
| `video`, `audio` or `textstream` | `src`            | The [track file](track-files.md)'s name, relative to the episode folder   |
| `video`, `audio` or `textstream` | `systemBitrate`  | The bitrate of the track's quality level                                  |
| `video`, `audio` or `textstream` | `systemLanguage` | The stream's ISO 639-2 language; left out when the manifest gives none    |
| `param`                          | `name`           | `trackName`                                                               |
| `param`                          | `value`          | The stream name, such as `video`, `enus` or `enus_captions`               |
| `param`                          | `valuetype`      | `data`                                                                    |

The elements follow the order of the tracks in the client manifest. The file is UTF-8 with the declaration
`<?xml version='1.0' encoding='utf-8'?>`, indented with two spaces, with LF line ends and no line end after the root
element.

## How QuantumStreamer uses it

QuantumStreamer reads every `*.ism` file in the episode folder and keys each track by its stream name and bitrate,
`<trackName>_<systemBitrate>`; for `video` elements the name is always `video`. When the game asks for
`QualityLevels(<bitrate>)/Fragments(<name>=<start time>)`, it serves the fragment with that start time from the
matching track file's index; a fragment it does not find there is fetched from the server unless QuantumStreamer's
offline mode is on. A track whose file is missing or has no valid index is skipped.

QuantumStreamer plays an episode from a single server manifest, so before writing `<episode ID>.ism` QuantumFetcher
renames any other `.ism` file in the folder to `<name>.ism.old` and logs a warning. Older versions of QuantumFetcher
wrote the server manifest under another name; the rename keeps such a file from being played instead.

QuantumFetcher writes the server manifest together with the client manifest, once the folder holds a video and an
audio track of the episode, and lists every track of the episode whose file is in the folder.

## Example

The server manifest of an invented episode `J1A` with a 500000 video track, the `enus` audio and the `enus_captions`
captions:

```xml
<?xml version='1.0' encoding='utf-8'?>
<smil xmlns="http://www.w3.org/2001/SMIL20/Language">
  <head>
    <meta name="clientManifestRelativePath" content="J1A.ismc" />
  </head>
  <body>
    <switch>
      <video src="J1A_video_500000.ismv" systemBitrate="500000">
        <param name="trackName" value="video" valuetype="data" />
      </video>
      <audio src="J1A_enus_256000.isma" systemBitrate="256000" systemLanguage="eng">
        <param name="trackName" value="enus" valuetype="data" />
      </audio>
      <textstream src="J1A_enus_captions_256000.ismt" systemBitrate="256000" systemLanguage="eng">
        <param name="trackName" value="enus_captions" valuetype="data" />
      </textstream>
    </switch>
  </body>
</smil>
```

QuantumStreamer keys these tracks as `video_500000`, `enus_256000` and `enus_captions_256000`. The game's request for
`QualityLevels(256000)/Fragments(enus=20000000)` is served from `J1A_enus_256000.isma`.
