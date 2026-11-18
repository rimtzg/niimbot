import hashlib
import os
import struct
import sys


BASE_ADDR = 0x01010000
EXPECTED_STOCK_LEN = 125016
EXPECTED_STOCK_MD5 = "455f420bb63b46469747c199d14497a4"

# Addresses in B1 3.08 firmware
ADDR_FMUL = 0x0102639A
ADDR_DENSITY_BYTE = 0x0002072C
ADDR_ALIGN_FLAG = 0x00020623
ADDR_RFID_STRUCT = 0x0002087C

# Float pools and motor ramp in B1 3.08
FLOAT_COEFF_SITES = [
    (0x01012E0C, 74.4),
    (0x01012E10, 60.0),
    (0x01012E14, 60.8),
    (0x01012E18, 120.0),
    (0x01017604, 20.0),
    (0x01017618, 50.0),
    (0x0101761C, 30.0),
    (0x01017620, 150.0),
    (0x01017624, 100.0),
    (0x01017628, 90.0),
    (0x01017D50, 10.0),
    (0x01017D54, 30.0),
    (0x01017D58, 50.0),
    (0x01017D5C, 120.0),
    (0x01017D60, 100.0),
]
ADDR_MOTOR_RAMP = 0x0102D47C
ADDR_RFID_CURVE_SITES = [0x01017130, 0x0102384C, 0x01023990]
ADDR_SET_DENSITY_THROTTLE = 0x0101EA14

# Renderer detour hook sites and caves in B1 3.08
ADDR_HOOK_124 = 0x010171F2
ADDR_HOOK_844 = 0x01017912
ADDR_CAVE_A = 0x0102CDC8
ADDR_CAVE_B = 0x0102CE24

# align3 addresses in B1 3.08:
# In 3.08, 0x101288a does NOT skip the align block while [0x20034 + 4] == 1 (Pass 1 of 0x1011e5e).
# Therefore, [0x20623] must ONLY be set to 1 inside Pass 2 of 0x1011e5e (at 0x1011ecc),
# right where [0x20034 + 4] is cleared to 0 (0x1011ed0).
ADDR_ALIGN3_HELPER = 0x01010140
ADDR_ALIGN3_PASS2_HOOK = 0x01011ECC
ADDR_ALIGN3_TAG_CHECK = 0x010128C6
ADDR_MODE3_DIR_HELPER = 0x01010148
ADDR_MODE3_CASE8_STEP_BL = 0x01018B26
ADDR_STEP_MOTOR = 0x010180F8

# align7 addresses in B1 3.08
ADDR_ALIGN7_HELPER = 0x01010160
ALIGN7_POOLS = [
    (0x01012E0C, 16),
    (0x01017604, 4),
    (0x01017618, 20),
    (0x01017D50, 20),
]
ALIGN7_RAMP = (0x0102D47C, 200)
ALIGN7_BL_SITES = [
    0x01012CB8,
    0x01012CCE,
    0x01012D82,
    0x01012D98,
    0x0101720C,
    0x01017230,
    0x0101723E,
    0x0101724C,
    0x0101727A,
    0x01017288,
    0x0101729A,
    0x01017958,
    0x01017A36,
    0x01017994,
    0x010179DA,
    0x010179E8,
    0x010179FA,
    0x01017A24,
]


def file_offset(vaddr):
    return vaddr - BASE_ADDR


def compute_md5(data):
    return hashlib.md5(data).hexdigest()


def encode_thumb_bl(source_addr, target_addr):
    imm32 = target_addr - (source_addr + 4)
    if imm32 % 2 != 0 or not (-(1 << 24) <= imm32 < (1 << 24)):
        raise ValueError(f"BL out of range: {hex(source_addr)} -> {hex(target_addr)}")
    imm25 = imm32 & 0x1FFFFFF
    s_bit = (imm25 >> 24) & 1
    i1_bit = (imm25 >> 23) & 1
    i2_bit = (imm25 >> 22) & 1
    imm10 = (imm25 >> 12) & 0x3FF
    imm11 = (imm25 >> 1) & 0x7FF
    j1_bit = i1_bit ^ s_bit ^ 1
    j2_bit = i2_bit ^ s_bit ^ 1
    hw1 = 0xF000 | (s_bit << 10) | imm10
    hw2 = 0xD000 | (j1_bit << 13) | (j2_bit << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def apply_fullquality_base(fw_data, target_coeff=400.0, feed_mult=1.5):
    try:
        # 1. RFID curve flag sites: movs r1, #3 -> movs r1, #0
        for site_addr in ADDR_RFID_CURVE_SITES:
            off = file_offset(site_addr)
            if fw_data[off:off + 2] != b"\x03\x21":
                raise ValueError(f"Unexpected bytes at RFID curve site {hex(site_addr)}")
            fw_data[off:off + 2] = b"\x00\x21"

        # 1b. SetDensity (0x0101EA14): prevent overwriting [0x000204ce] = 3 when no RFID tag is present
        off_sd = file_offset(ADDR_SET_DENSITY_THROTTLE)
        if fw_data[off_sd:off_sd + 2] != b"\x0b\x70":
            raise ValueError(f"Unexpected bytes at SetDensity throttle site {hex(ADDR_SET_DENSITY_THROTTLE)}")
        fw_data[off_sd:off_sd + 2] = b"\x00\xbf"

        # 2. Set all 15 float coefficients to target_coeff (400.0f)
        packed_coeff = struct.pack("<f", float(target_coeff))
        for site_addr, expected_val in FLOAT_COEFF_SITES:
            off = file_offset(site_addr)
            current_val = struct.unpack("<f", fw_data[off:off + 4])[0]
            if abs(current_val - expected_val) > 0.5:
                raise ValueError(f"Float mismatch at {hex(site_addr)}: got {current_val}, expected {expected_val}")
            fw_data[off:off + 4] = packed_coeff

        # 3. Scale 64-entry motor line-period table by feed_mult (1.5x)
        ramp_off = file_offset(ADDR_MOTOR_RAMP)
        for idx in range(64):
            entry_off = ramp_off + (2 * idx)
            val = struct.unpack("<H", fw_data[entry_off:entry_off + 2])[0]
            if 100 <= val <= 40000:
                scaled_val = min(int(val * feed_mult), 65535)
                fw_data[entry_off:entry_off + 2] = struct.pack("<H", scaled_val)
            else:
                break
    except Exception as exc:
        raise RuntimeError(f"Failed applying fullquality base patch: {exc}") from exc


def apply_density_coeff_hooks(fw_data):
    try:
        # 1. Build Cave A @ 0x0102CDC8 (68 bytes): scale(r0) + mtable + literal pool
        cave_a_code = bytes.fromhex(
            "10b5"  # push {r4, lr}
            "0d4c"  # ldr  r4, [pc, #52]  -> &density (0x0002072c)
            "2478"  # ldrb r4, [r4]
            "7f21"  # movs r1, #0x7f
            "0c40"  # ands r4, r1
            "012c"  # cmp  r4, #1
            "00d2"  # bhs  +0
            "0124"  # movs r4, #1
            "052c"  # cmp  r4, #5
            "00d9"  # bls  +0
            "0524"  # movs r4, #5
            "013c"  # subs r4, r4, #1
            "a400"  # lsls r4, r4, #2
            "0849"  # ldr  r1, [pc, #32]  -> mtable
            "0959"  # ldr  r1, [r1, r4]
            "084b"  # ldr  r3, [pc, #32]  -> fmul | 1
            "9847"  # blx  r3
            "10bd"  # pop  {r4, pc}
        )
        mtable_addr = ADDR_CAVE_A + len(cave_a_code)
        mtable_bytes = struct.pack("<5f", 0.675, 0.75625, 0.8375, 0.91875, 1.0)
        pool_bytes = struct.pack(
            "<III",
            ADDR_DENSITY_BYTE,
            mtable_addr,
            ADDR_FMUL | 1,
        )
        cave_a = cave_a_code + mtable_bytes + pool_bytes
        if len(cave_a) != 68:
            raise ValueError(f"Invalid Cave A length: {len(cave_a)}")

        off_a = file_offset(ADDR_CAVE_A)
        if fw_data[off_a:off_a + len(cave_a)] != b"\x00" * len(cave_a):
            raise ValueError("Cave A space is not all zeros")
        fw_data[off_a:off_a + len(cave_a)] = cave_a

        # 2. Build Cave B @ 0x0102CE24 (44 bytes): det124 and det844
        addr_det124 = ADDR_CAVE_B
        det124 = (
            b"\x0f\xb5"                                      # push {r0-r3, lr}
            + b"\x0e\x98"                                    # ldr  r0, [sp, #0x38]
            + encode_thumb_bl(addr_det124 + 4, ADDR_CAVE_A)  # bl   scale
            + b"\x0e\x90"                                    # str  r0, [sp, #0x38]
            + b"\x0f\xbc"                                    # pop  {r0-r3}
            + b"\x16\x46"                                    # mov  r6, r2 (displaced)
            + b"\xff\x36"                                    # adds r6, #0xff (displaced)
            + b"\x00\xbd"                                    # pop  {pc}
        )
        addr_det844 = ADDR_CAVE_B + len(det124)
        det844 = (
            b"\x0f\xb5"                                      # push {r0-r3, lr}
            + b"\x0f\x98"                                    # ldr  r0, [sp, #0x3c]
            + encode_thumb_bl(addr_det844 + 4, ADDR_CAVE_A)  # bl   scale
            + b"\x0f\x90"                                    # str  r0, [sp, #0x3c]
            + b"\x10\x98"                                    # ldr  r0, [sp, #0x40]
            + encode_thumb_bl(addr_det844 + 12, ADDR_CAVE_A) # bl   scale
            + b"\x10\x90"                                    # str  r0, [sp, #0x40]
            + b"\x0f\xbc"                                    # pop  {r0-r3}
            + b"\x14\x46"                                    # mov  r4, r2 (displaced)
            + b"\x06\x46"                                    # mov  r6, r0 (displaced)
            + b"\x00\xbd"                                    # pop  {pc}
        )
        cave_b = det124 + det844
        if len(cave_b) != 44:
            raise ValueError(f"Invalid Cave B length: {len(cave_b)}")

        off_b = file_offset(ADDR_CAVE_B)
        if fw_data[off_b:off_b + len(cave_b)] != b"\x00" * len(cave_b):
            raise ValueError("Cave B space is not all zeros")
        fw_data[off_b:off_b + len(cave_b)] = cave_b

        # 3. Install 4-byte BL hooks at Renderer 1 (0x10171f2) and Renderer 2 (0x1017912)
        off_h124 = file_offset(ADDR_HOOK_124)
        if fw_data[off_h124:off_h124 + 4] != b"\x16\x46\xff\x36":
            raise ValueError("Unexpected bytes at Renderer 1 hook site")
        fw_data[off_h124:off_h124 + 4] = encode_thumb_bl(ADDR_HOOK_124, addr_det124)

        off_h844 = file_offset(ADDR_HOOK_844)
        if fw_data[off_h844:off_h844 + 4] != b"\x14\x46\x06\x46":
            raise ValueError("Unexpected bytes at Renderer 2 hook site")
        fw_data[off_h844:off_h844 + 4] = encode_thumb_bl(ADDR_HOOK_844, addr_det844)
    except Exception as exc:
        raise RuntimeError(f"Failed applying density_coeff hooks: {exc}") from exc


def apply_align3_patch(fw_data):
    try:
        # 1. NOP the tag-present check in the align block (0x10128c6: 1f d1 -> 00 bf)
        off_tc = file_offset(ADDR_ALIGN3_TAG_CHECK)
        if fw_data[off_tc:off_tc + 2] != b"\x1f\xd1":
            raise ValueError(f"Unexpected bytes at ALIGN3_TAG_CHECK: {fw_data[off_tc:off_tc + 2].hex()}")
        fw_data[off_tc:off_tc + 2] = b"\x00\xbf"

        # 2. Place ALIGN3_HELPER at 0x1010140 (8 bytes):
        # Called from 0x1011ecc (Pass 2 of 0x1011e5e, right when [0x20034 + 4] is cleared to 0):
        #   adds r0, #0x20    ; 20 30 (r0 = 0x20600 + 0x20 = 0x20620)
        #   movs r1, #1       ; 01 21 (r1 = 1)
        #   strb r1, [r0, #3] ; c1 70 (sets [0x00020623] = 1)
        #   bx   lr           ; 70 47 (returns to 0x1011ed0: strb r6, [r4, #4])
        helper = b"\x20\x30\x01\x21\xc1\x70\x70\x47"
        off_h = file_offset(ADDR_ALIGN3_HELPER)
        if fw_data[off_h:off_h + len(helper)] != b"\x00" * len(helper):
            raise ValueError("ALIGN3_HELPER space is not zero")
        fw_data[off_h:off_h + len(helper)] = helper

        # 3. Replace `adds r0, #0x20; strb r6, [r0, #3]` (20 30 c6 70) at 0x1011ecc with BL ALIGN3_HELPER
        off_hook = file_offset(ADDR_ALIGN3_PASS2_HOOK)
        if fw_data[off_hook:off_hook + 4] != b"\x20\x30\xc6\x70":
            raise ValueError(f"Unexpected bytes at 0x1011ecc: {fw_data[off_hook:off_hook + 4].hex()}")
        fw_data[off_hook:off_hook + 4] = encode_thumb_bl(ADDR_ALIGN3_PASS2_HOOK, ADDR_ALIGN3_HELPER)

        # 4. In Mode 3 gap seek (0x101875e), case 7 computes (label_len_mm - 12.7) * 64.
        # Without an RFID tag, label_len_mm is 0, so (0 - 12.7) * 64 = -812.8f, which __aeabi_f2uiz (0x1026896)
        # converts to +812 microsteps (12.7 mm, optical sensor -> printhead distance).
        # Case 8 (0x1018b24) must step REVERSE (r0=1) when tagged, but FORWARD (r0=0) when untagged so the
        # detected gap advances 12.7 mm to the printhead before case 9 advances 7.5 mm to the tear bar.
        dir_helper = (
            b"\x00\xb5"                                                    # push {lr}
            + b"\x02\x48"                                                  # ldr  r0, [pc, #8] -> 0x0002087c
            + b"\x00\x7b"                                                  # ldrb r0, [r0, #12] -> tag_present
            + encode_thumb_bl(ADDR_MODE3_DIR_HELPER + 6, ADDR_STEP_MOTOR)  # bl   0x10180f8
            + b"\x00\xbd"                                                  # pop  {pc}
            + struct.pack("<I", ADDR_RFID_STRUCT)                          # 0x0002087c
        )
        if len(dir_helper) != 16:
            raise ValueError(f"Invalid MODE3_DIR_HELPER length: {len(dir_helper)}")

        off_dh = file_offset(ADDR_MODE3_DIR_HELPER)
        if fw_data[off_dh:off_dh + len(dir_helper)] != b"\x00" * len(dir_helper):
            raise ValueError("MODE3_DIR_HELPER space is not zero")
        fw_data[off_dh:off_dh + len(dir_helper)] = dir_helper

        off_c8 = file_offset(ADDR_MODE3_CASE8_STEP_BL)
        expected_c8_bl = encode_thumb_bl(ADDR_MODE3_CASE8_STEP_BL, ADDR_STEP_MOTOR)
        if fw_data[off_c8:off_c8 + 4] != expected_c8_bl:
            raise ValueError(f"Unexpected BL at 0x1018b26: {fw_data[off_c8:off_c8 + 4].hex()}")
        fw_data[off_c8:off_c8 + 4] = encode_thumb_bl(ADDR_MODE3_CASE8_STEP_BL, ADDR_MODE3_DIR_HELPER)
    except Exception as exc:
        raise RuntimeError(f"Failed applying align3 patch: {exc}") from exc


def apply_align7_patch(fw_data, stock_data):
    try:
        # 1. Restore original literal pools and motor ramp from stock 3.08
        for addr, length in ALIGN7_POOLS + [ALIGN7_RAMP]:
            off = file_offset(addr)
            fw_data[off:off + length] = stock_data[off:off + length]

        # Verify non-multiplier literal at 0x1017614 stayed untouched (0x000208c8)
        off_check = file_offset(0x01017614)
        if fw_data[off_check:off_check + 4] != struct.pack("<I", 0x000208C8):
            raise ValueError("Non-multiplier literal at 0x1017614 was modified")

        # 2. Place ALIGN7_HELPER at 0x1010160 (28 bytes)
        # Note: in 3.08 tag-present is at [0x0002087c + 12], so ldrb r2, [r2, #12] is 12 7b
        helper = (
            b"\x04\xb5"                                          # push {r2, lr}
            + b"\x04\x4a"                                        # ldr  r2, [pc, #16] -> 0x0002087c
            + b"\x12\x7b"                                        # ldrb r2, [r2, #12] -> tag-present
            + b"\x01\x2a"                                        # cmp  r2, #1
            + b"\x00\xd0"                                        # beq  +0 (skip override if tagged)
            + b"\x03\x49"                                        # ldr  r1, [pc, #12] -> 400.0f
            + encode_thumb_bl(ADDR_ALIGN7_HELPER + 0xC, ADDR_FMUL)  # bl   fmul (0x102639a)
            + b"\x04\xbd"                                        # pop  {r2, pc}
            + b"\x00\x00"                                        # pad
            + struct.pack("<II", ADDR_RFID_STRUCT, 0x43C80000)   # 0x0002087c, 400.0f
        )
        if len(helper) != 28:
            raise ValueError(f"Invalid ALIGN7_HELPER length: {len(helper)}")

        off_h = file_offset(ADDR_ALIGN7_HELPER)
        if fw_data[off_h:off_h + len(helper)] != b"\x00" * len(helper):
            raise ValueError("ALIGN7_HELPER space is not zero")
        fw_data[off_h:off_h + len(helper)] = helper

        # 3. Redirect all 18 heating multiplier BL fmul sites to ALIGN7_HELPER
        for site_addr in ALIGN7_BL_SITES:
            off_site = file_offset(site_addr)
            expected_bl = encode_thumb_bl(site_addr, ADDR_FMUL)
            if fw_data[off_site:off_site + 4] != expected_bl:
                raise ValueError(f"Unexpected BL at {hex(site_addr)}")
            fw_data[off_site:off_site + 4] = encode_thumb_bl(site_addr, ADDR_ALIGN7_HELPER)
    except Exception as exc:
        raise RuntimeError(f"Failed applying align7 patch: {exc}") from exc


def main():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        stock_path = os.path.join(base_dir, "B1_3.08.bin")
        if not os.path.exists(stock_path):
            sys.exit(f"Missing stock firmware file: {stock_path}")

        with open(stock_path, "rb") as file_obj:
            stock_data = file_obj.read()

        if len(stock_data) != EXPECTED_STOCK_LEN:
            sys.exit(f"Unexpected stock size: {len(stock_data)} (expected {EXPECTED_STOCK_LEN})")
        if compute_md5(stock_data) != EXPECTED_STOCK_MD5:
            sys.exit(f"Unexpected stock MD5: {compute_md5(stock_data)} (expected {EXPECTED_STOCK_MD5})")

        print(f"Loaded stock B1_3.08.bin ({len(stock_data)} bytes, md5={compute_md5(stock_data)})")

        # Build 1: B1_3.08_thirdparty_fullquality.bin
        fw_work = bytearray(stock_data)
        apply_fullquality_base(fw_work)
        out_full = os.path.join(base_dir, "B1_3.08_thirdparty_fullquality.bin")
        with open(out_full, "wb") as file_obj:
            file_obj.write(fw_work)
        print(f"1. Wrote {os.path.basename(out_full)} (md5={compute_md5(fw_work)})")

        # Build 2: B1_3.08_density_coeff.bin
        apply_density_coeff_hooks(fw_work)
        out_dens = os.path.join(base_dir, "B1_3.08_density_coeff.bin")
        with open(out_dens, "wb") as file_obj:
            file_obj.write(fw_work)
        print(f"2. Wrote {os.path.basename(out_dens)} (md5={compute_md5(fw_work)})")

        # Build 3: B1_3.08_density_align7_no_autoseek.bin (density + align7, without align3 cover-close seek)
        fw_no_seek = bytearray(fw_work)
        apply_align7_patch(fw_no_seek, stock_data)
        out_no_seek = os.path.join(base_dir, "B1_3.08_density_align7_no_autoseek.bin")
        with open(out_no_seek, "wb") as file_obj:
            file_obj.write(fw_no_seek)
        print(f"3. Wrote {os.path.basename(out_no_seek)} (md5={compute_md5(fw_no_seek)})")

        # Build 4: B1_3.08_density_align3.bin (fixed Pass 2 hook)
        apply_align3_patch(fw_work)
        out_align3 = os.path.join(base_dir, "B1_3.08_density_align3.bin")
        with open(out_align3, "wb") as file_obj:
            file_obj.write(fw_work)
        print(f"4. Wrote {os.path.basename(out_align3)} (md5={compute_md5(fw_work)})")

        # Build 5: B1_3.08_density_align7.bin (fixed Pass 2 hook + align7)
        apply_align7_patch(fw_work, stock_data)
        out_align7 = os.path.join(base_dir, "B1_3.08_density_align7.bin")
        with open(out_align7, "wb") as file_obj:
            file_obj.write(fw_work)
        print(f"5. Wrote {os.path.basename(out_align7)} (md5={compute_md5(fw_work)})")

    except Exception as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
