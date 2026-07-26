import struct
from pathlib import Path


def _build_mfra(offsets: list[int], timestamps: list[int]) -> bytes:
    """Build the final mfra box with tfra and mfro.

    Args:
        offsets: Absolute byte offsets to the start of each moof box
        timestamps: Presentation timestamps corresponding to each fragment
    """
    # tfra box
    tfra = bytearray()
    tfra += b"\x01\x00\x00\x00"  # version=1 (using 64-bit times/offsets), flags=0
    tfra += struct.pack(">I", 1)  # track_ID
    tfra += struct.pack(">I", 0)  # length_size_of_traf_num, trun_num, sample_num
    tfra += struct.pack(">I", len(timestamps))  # number_of_entry

    for time, offset in zip(timestamps, offsets):
        tfra += struct.pack(">Q", time)
        tfra += struct.pack(">Q", offset)
        tfra += b"\x01\x01\x01"  # traf_number=1, trun_number=1, sample_number=1

    tfra_box = struct.pack(">I", 8 + len(tfra)) + b"tfra" + tfra

    # mfro box (Movie Fragment Random Access Offset)
    mfro = bytearray()
    mfro += b"\x00\x00\x00\x00"  # version=0, flags=0
    # size of mfra box = 8 (mfra header) + len(tfra_box) + 16 (mfro_box size)
    mfra_size = 8 + len(tfra_box) + 16
    mfro += struct.pack(">I", mfra_size)
    mfro_box = struct.pack(">I", 16) + b"mfro" + mfro

    # mfra box
    mfra = tfra_box + mfro_box
    return struct.pack(">I", 8 + len(mfra)) + b"mfra" + mfra


def post_process_media_file(file_path: Path):
    """Scan an ISMV/ISMA/ISMT file produced by yt-dlp, extract moof timestamps, and append mfra."""
    offsets = []
    timestamps = []

    with open(file_path, "rb+") as f:
        data = f.read()
        pos = 0
        current_time = 0
        while pos < len(data) and pos + 8 <= len(data):
            size = int.from_bytes(data[pos : pos + 4], "big")
            box_type = data[pos + 4 : pos + 8]

            if size == 0:
                break

            if box_type == b"moof":
                moof_data = data[pos : pos + size]
                time = current_time

                # Find tfdt inside this moof
                tfdt_pos = moof_data.find(b"tfdt")
                if tfdt_pos != -1:
                    tfdt_size = int.from_bytes(
                        moof_data[tfdt_pos - 4 : tfdt_pos], "big"
                    )
                    tfdt_box = moof_data[tfdt_pos - 4 : tfdt_pos - 4 + tfdt_size]
                    version = tfdt_box[8]
                    if version == 1:
                        time = int.from_bytes(tfdt_box[12:20], "big")
                    else:
                        time = int.from_bytes(tfdt_box[12:16], "big")
                    current_time = time

                # Accumulate current_time for next moof using trun/tfhd just in case
                tfhd_pos = moof_data.find(b"tfhd")
                default_duration = 0
                if tfhd_pos != -1:
                    tfhd_size = int.from_bytes(
                        moof_data[tfhd_pos - 4 : tfhd_pos], "big"
                    )
                    tfhd_box = moof_data[tfhd_pos - 4 : tfhd_pos - 4 + tfhd_size]
                    flags = int.from_bytes(tfhd_box[9:12], "big")
                    offset = 12
                    if flags & 0x000001:
                        offset += 8  # base_data_offset
                    if flags & 0x000002:
                        offset += 4  # sample_description_index
                    if flags & 0x000008:
                        default_duration = int.from_bytes(
                            tfhd_box[offset : offset + 4], "big"
                        )

                trun_pos = moof_data.find(b"trun")
                if trun_pos != -1:
                    trun_size = int.from_bytes(
                        moof_data[trun_pos - 4 : trun_pos], "big"
                    )
                    trun_box = moof_data[trun_pos - 4 : trun_pos - 4 + trun_size]
                    flags = int.from_bytes(trun_box[9:12], "big")
                    sample_count = int.from_bytes(trun_box[12:16], "big")

                    p = 16
                    if flags & 0x0001:
                        p += 4
                    if flags & 0x0004:
                        p += 4

                    moof_duration = 0
                    for _ in range(sample_count):
                        duration = default_duration
                        if flags & 0x0100:
                            duration = int.from_bytes(trun_box[p : p + 4], "big")
                            p += 4
                        if flags & 0x0200:
                            p += 4
                        if flags & 0x0400:
                            p += 4
                        if flags & 0x0800:
                            p += 4
                        moof_duration += duration

                    current_time += moof_duration

                offsets.append(pos)
                timestamps.append(time)

            # Use 64-bit size if needed (unlikely for yt-dlp moofs, but safe for mdat)
            if size == 1:
                size = int.from_bytes(data[pos + 8 : pos + 16], "big")

            pos += size

        if not offsets:
            raise ValueError(
                "No moof boxes found in the file, cannot build mfra index."
            )

        mfra_box = _build_mfra(offsets, timestamps)

        # Check if an mfra already exists (unlikely from yt-dlp, but just in case)
        if data[-4:] == b"mfro":
            # Overwrite existing mfra
            mfro_size = int.from_bytes(data[-8:-4], "big")
            f.seek(len(data) - mfro_size)
        else:
            f.seek(len(data))

        f.write(mfra_box)
