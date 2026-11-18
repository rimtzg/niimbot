    .syntax unified
    .cpu cortex-m0
    .thumb

    /* ============ Cave A @ 0x0102cdc8 : shared scale + mtable ============ */
    .section .caveA, "ax", %progbits
    .thumb_func
    .global scale
scale:                       @ in: r0=input float ; out: r0 = input * m(density)
    push {r4, lr}
    ldr  r4, =0x0002072c     @ &density (B1 3.08 CFG+4)
    ldrb r4, [r4]
    movs r1, #0x7f
    ands r4, r1              @ d = density & 0x7f
    cmp  r4, #1
    bhs  1f
    movs r4, #1              @ clamp low
1:  cmp  r4, #5
    bls  2f
    movs r4, #5              @ clamp high
2:  subs r4, r4, #1          @ index 0..4
    lsls r4, r4, #2          @ *4
    ldr  r1, =mtable
    ldr  r1, [r1, r4]        @ r1 = m(d)
    ldr  r3, =0x0102639b     @ __aeabi_fmul (0x0102639a) | thumb
    blx  r3                  @ r0 = r0 * r1
    pop  {r4, pc}
    .align 2
    .global mtable
mtable:
    .float 0.675
    .float 0.756250
    .float 0.837500
    .float 0.918750
    .float 1.0
    .ltorg

    /* ============ Cave B @ 0x0102ce24 : renderer detours ============ */
    .section .caveB, "ax", %progbits
    .thumb_func
    .global det124
det124:                      @ Renderer 1 (0x010171f0) detour body
    push {r0-r3, lr}
    ldr  r0, [sp, #0x38]     @ arg5 (renderer input float)
    bl   scale
    str  r0, [sp, #0x38]
    pop  {r0-r3}
    .short 0x4616            @ displaced: mov  r6, r2
    .short 0x36ff            @ displaced: adds r6, #0xff
    pop  {pc}                @ -> 0x010171f6

    .thumb_func
    .global det844
det844:                      @ Renderer 2 (0x01017910) detour body
    push {r0-r3, lr}
    ldr  r0, [sp, #0x3c]     @ arg6 (input float A)
    bl   scale
    str  r0, [sp, #0x3c]
    ldr  r0, [sp, #0x40]     @ arg7 (input float B)
    bl   scale
    str  r0, [sp, #0x40]
    pop  {r0-r3}
    .short 0x4614            @ displaced: mov r4, r2
    .short 0x4606            @ displaced: mov r6, r0
    pop  {pc}                @ -> 0x01017916

    /* ============ Vector-table helpers @ 0x01010140..0x0101017c ============ */
    .section .align3_helper, "ax", %progbits
    .thumb_func
    .global align3_helper
align3_helper:               @ Hooked from 0x01011ecc (Pass 2 of no-chip fallback)
    adds r0, #0x20           @ r0 = 0x00020600 + 0x20 = 0x00020620
    movs r1, #1
    strb r1, [r0, #3]        @ [0x00020623] = 1 (request gap seek)
    bx   lr

    .section .mode3_dir_helper, "ax", %progbits
    .thumb_func
    .global mode3_dir_helper
mode3_dir_helper:            @ Hooked from 0x01018b26 (Mode 3 case 8 step direction)
    push {lr}
    ldr  r0, =0x0002087c     @ RFID struct base
    ldrb r0, [r0, #12]       @ tag_present (1 = reverse if tagged, 0 = forward if untagged)
    bl   0x010180f8          @ step_motor(r0)
    pop  {pc}
    .ltorg

    .section .align7_helper, "ax", %progbits
    .thumb_func
    .global align7_helper
align7_helper:               @ Conditional 400.0f heating multiplier (only when untagged)
    push {r2, lr}
    ldr  r2, =0x0002087c
    ldrb r2, [r2, #12]       @ tag_present ([0x0002087c + 12])
    cmp  r2, #1
    beq  1f
    ldr  r1, =0x43c80000     @ 400.0f
1:  bl   0x0102639a          @ __aeabi_fmul
    pop  {r2, pc}
    .ltorg

    /* ============ Detour stubs (4 bytes each) ============ */
    .section .hook124, "ax", %progbits
    .thumb_func
h124:
    bl   det124              @ replaces 4 bytes at 0x010171f2

    .section .hook844, "ax", %progbits
    .thumb_func
h844:
    bl   det844              @ replaces 4 bytes at 0x01017912
