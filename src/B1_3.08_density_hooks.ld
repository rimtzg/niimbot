/* Linker script for B1_3.08_density_hooks.s (Niimbot B1 firmware 3.08).
 *
 * Places each section at its fixed flash address in B1_3.08.bin (base 0x01010000):
 *   .align3_helper    0x01010140 ( 8 B)
 *   .mode3_dir_helper 0x01010148 (16 B)
 *   .align7_helper    0x01010160 (28 B)
 *   .caveA            0x0102cdc8 (68 B)
 *   .caveB            0x0102ce24 (44 B)
 *   .hook124          0x010171f2 ( 4 B)
 *   .hook844          0x01017912 ( 4 B)
 */
SECTIONS {
  . = 0x01010140; .align3_helper : { *(.align3_helper) }
  . = 0x01010148; .mode3_dir_helper : { *(.mode3_dir_helper) }
  . = 0x01010160; .align7_helper : { *(.align7_helper) }
  . = 0x0102cdc8; .caveA : { *(.caveA) }
  . = 0x0102ce24; .caveB : { *(.caveB) }
  . = 0x010171f2; .hook124 : { *(.hook124) }
  . = 0x01017912; .hook844 : { *(.hook844) }
  /DISCARD/ : { *(.ARM.attributes) *(.comment) }
}
