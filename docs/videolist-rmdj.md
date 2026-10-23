# videoList.rmdj

`data/videoList.rmdj` in the game folder lists the live-action episodes the game streams: a JSON object that maps each
episode ID to the URL of the episode's [client manifest](client-manifest.md), encrypted with a repeating XOR key. The
game finds each episode through it. QuantumFetcher reads it to find the manifests to download, and writes it when
patching or building the list.

## Layout

The file has no header, checksum or compression. Each byte is the byte of the JSON text at the same position, XORed
with the key byte at that position modulo 32:

```text
encrypted[i] = text[i] XOR key[i mod 32]
```

The key is 32 bytes long:

```text
ba 7a bb 27 03 9b 72 fd 13 eb 70 38 7e 0f cb 41
e1 d0 eb 54 be 8f 13 6d f0 ba e2 2a dc fb 40 f1
```

XOR undoes itself, so the same operation encrypts and decrypts, and the file is exactly as long as its JSON text.

## JSON

The decrypted text is a single JSON object:

| Part  | Type   | Meaning                                                                                           |
|-------|--------|---------------------------------------------------------------------------------------------------|
| Name  | string | The episode ID, such as `J1A` or `J1A-X1-X2`; the episode folder and its files are named after it |
| Value | string | The URL of the episode's client manifest                                                          |

The game's own list has 45 entries: `J1 - 4K Test` and the IDs of the parts of each episode and their variants, from
`J1A` to `J4BB-X2`. Its URLs point at `<name>.ism/manifest` on the streaming server and end with a query string,
which the game and QuantumFetcher also add to every fragment URL.

QuantumFetcher accepts any object whose names and values are all strings. Anything else stops the command with an
error that names the file: `Not a video list: ...` when the decrypted bytes are not JSON, and
`A video list must map episode IDs to manifest URLs` for another JSON value or a value that is not a string.

### Layout differences

The game reads both layouts:

|             | The game's list                         | Lists QuantumFetcher writes                 |
|-------------|-----------------------------------------|---------------------------------------------|
| Indentation | One tab                                 | Four spaces                                 |
| Name, value | `"J1A" : "..."`                         | `"J1A": "..."`                              |
| Line ends   | CRLF, with blank lines between episodes | LF, without blank lines                     |
| End of file | `}` and CRLF                            | `}` without a line end                      |
| Characters  | ASCII                                   | ASCII, other characters as `\uXXXX` escapes |

## Copies beside the list

| File                      | Written by                                                                  | Holds                                                       |
|---------------------------|-----------------------------------------------------------------------------|-------------------------------------------------------------|
| `videoList_original.rmdj` | `videolist patch` the first time, or QuantumStreamer before its first patch | A byte copy of the game's list, with the episodes' own URLs |
| `<list>.old`              | `videolist build`, once                                                     | The first list that `build` replaced, as it was             |

Once the list is patched, the episodes' own URLs are only in `videoList_original.rmdj`, so the commands that need
them use that copy:

| Command                                 | Reads                                                                                | Writes                                                                                                              |
|-----------------------------------------|--------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| `download`, `formats`, `videolist dump` | `videoList_original.rmdj` when it exists, else `videoList.rmdj`                      |                                                                                                                     |
| `videolist patch`                       | `videoList_original.rmdj`, copied from `videoList.rmdj` first when it does not exist | `videoList.rmdj`                                                                                                    |
| `videolist build`                       | A JSON file                                                                          | `videoList_original.rmdj` when it exists, else `videoList.rmdj`, keeping the first list it replaces as `<list>.old` |

`--videolist-path` names another file to use instead. `videolist patch` then keeps its original as
`<name>_original<extension>` beside it.

A patched list points every episode at `http://<host>:<port>/<episode ID>/manifest`, with the ID written as it is,
spaces included. Patching again starts from `videoList_original.rmdj`, so it can change the server.

## Example

A list in the game's layout with two invented URLs (tabs and CRLF line ends shown as `\t` and `\r\n`):

```text
{\r\n
\t"J1A" : "http://cdn.example/J1A.ism/manifest?tkn=1",\r\n
\t"J1B" : "http://cdn.example/J1B.ism/manifest?tkn=1"\r\n
}\r\n
```

Its first 48 encrypted bytes, with the text they decrypt to:

| Offset | Encrypted bytes                                   | Text                  |
|--------|---------------------------------------------------|-----------------------|
| 0x00   | `c1 77 b1 2e 21 d1 43 bc 31 cb 4a 18 5c 67 bf 35` | `{\r\n\t"J1A" : "htt` |
| 0x10   | `91 ea c4 7b dd eb 7d 43 95 c2 83 47 ac 97 25 de` | `p://cdn.example/`    |
| 0x20   | `f0 4b fa 09 6a e8 1f d2 7e 8a 1e 51 18 6a b8 35` | `J1A.ism/manifest`    |

The first byte is `{` (0x7b) XOR 0xba = 0xc1. `videolist dump` prints the same list as:

```json
{
    "J1A": "http://cdn.example/J1A.ism/manifest?tkn=1",
    "J1B": "http://cdn.example/J1B.ism/manifest?tkn=1"
}
```

`videolist patch` with the default server keeps the file as `videoList_original.rmdj` and writes this text, encrypted,
to `videoList.rmdj`:

```json
{
    "J1A": "http://127.0.0.1:10000/J1A/manifest",
    "J1B": "http://127.0.0.1:10000/J1B/manifest"
}
```
