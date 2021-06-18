#!/usr/bin/env python3
import argparse

from nmigen import *
from nmigen.build import *
from nmigen_boards.ulx3s import *

from  st7789 import *

from vga import VGA
from ecp5pll import ECP5PLL

# The OLED pins are not defined in the ULX3S platform in nmigen_boards.
oled_resource = [
    Resource("oled_clk",  0, Pins("P4", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="UP")),
    Resource("oled_mosi", 0, Pins("P3", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="UP")),
    Resource("oled_dc",   0, Pins("P1", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="UP")),
    Resource("oled_resn", 0, Pins("P2", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="UP")),
    Resource("oled_csn",  0, Pins("N2", dir="o"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="UP")),
]

#btn_resource = [
#    Resource("btn1",      0, Pins("R1", dir="i"), Attrs(IO_TYPE="LVCMOS33", DRIVE="4", PULLMODE="DOWN")),
#]

class ST7789Test(Elaboratable):
    def elaborate(self, platform):
        if platform:
          clk_in = platform.request(platform.default_clk, dir='-')[0]

        # Constants
        pixel_f           = 25000000
        resolution_x      = 240
        hsync_front_porch = 16
        hsync_pulse_width = 112
        hsync_back_porch  = 2000 # long enough for SPI display to follow fps
        resolution_y      = 240
        vsync_front_porch = 6
        vsync_pulse_width = 8
        vsync_back_porch  = 23

        #clk25 = platform.request("clk25")
        led = [platform.request("led", i) for i in range(8)]

        # OLED
        oled_clk  = platform.request("oled_clk")
        oled_mosi = platform.request("oled_mosi")
        oled_dc   = platform.request("oled_dc")
        oled_resn = platform.request("oled_resn")
        oled_csn  = platform.request("oled_csn")

        # Buttons
        btn = [
            platform.request("button_pwr"),
            platform.request("button_fire", 0),
            platform.request("button_fire", 1),
            platform.request("button_up"),
            platform.request("button_down"),
            platform.request("button_left"),
            platform.request("button_right"),
        ]

        st7789 = ST7789(reset_delay=1000, reset2_delay=500000, vga_sync = 1)
        m = Module()
        m.domains.pixel = cd_pixel = ClockDomain("pixel")
        m.domains.sync  = cd_sync  = ClockDomain("sync")
        m.domains.spi   = cd_spi   = ClockDomain("spi")
        m.submodules.ecp5pll = pll = ECP5PLL()
        pll.register_clkin(clk_in,  platform.default_clk_frequency)
        pll.create_clkout(cd_sync,  platform.default_clk_frequency)
        pll.create_clkout(cd_pixel, pixel_f)
        pll.create_clkout(cd_spi,   pixel_f*4) # min 4x pixel

        m.submodules.vga = vga = VGA(
                resolution_x      = resolution_x+8, # extend picture for SPI display-vga input
                hsync_front_porch = hsync_front_porch,
                hsync_pulse       = hsync_pulse_width,
                hsync_back_porch  = hsync_back_porch,
                resolution_y      = resolution_y+8, # extend picture for SPI display-vga input
                vsync_front_porch = vsync_front_porch,
                vsync_pulse       = vsync_pulse_width,
                vsync_back_porch  = vsync_back_porch,
                bits_x            = 16, # Play around with the sizes because sometimes
                bits_y            = 16  # a smaller/larger value will make it pass timing.
        )
        vga_r = Signal(8)
        vga_g = Signal(8)
        vga_b = Signal(8)
        vga_hsync = Signal()
        vga_vsync = Signal()
        vga_blank = Signal()
        m.d.comb += [
                vga.i_clk_en.eq(1),
                vga.i_test_picture.eq(1),
                vga_r.eq(vga.o_vga_r),
                vga_g.eq(vga.o_vga_g),
                vga_b.eq(vga.o_vga_b),
                vga_hsync.eq(vga.o_vga_hsync),
                vga_vsync.eq(vga.o_vga_vsync),
                vga_blank.eq(vga.o_vga_blank),
        ]

        m.submodules.st7789 = st7789
       
        x = Signal(8)
        y = Signal(8)
        next_pixel = Signal()
 
        m.d.comb += [
            st7789.reset.eq(btn[1]),
            st7789.hsync.eq(vga_hsync),
            st7789.vsync.eq(vga_vsync),
            st7789.blank.eq(vga_blank),
            st7789.color.eq((vga_r[3:8] << 11)|(vga_g[2:8] << 5)|(vga_b[3:8])),
            oled_clk .eq(st7789.spi_clk),
            oled_mosi.eq(st7789.spi_mosi),
            oled_dc  .eq(st7789.spi_dc),
            oled_resn.eq(st7789.spi_resn),
            oled_csn .eq(1),
            next_pixel.eq(st7789.next_pixel),
            x.eq(st7789.x), # to generate chequered pattern when vga_sync = 0
            y.eq(st7789.y), # to generate chequered pattern when vga_sync = 0
        ]

        # chequered pattern from x,y when vga_sync = 0
        #with m.If(x[4] ^ y[4]):
        #    m.d.comb += st7789.color.eq(x[3:8] << 6)
        #with m.Else():
        #    m.d.comb += st7789.color.eq(y[3:8] << 11)

        m.d.comb += [
          led[0].eq(oled_dc),
          led[1].eq(oled_resn),
          led[2].eq(btn[1]),
          led[3].eq(vga_vsync),
        ]

        return m

if __name__ == "__main__":
    variants = {
        '12F': ULX3S_12F_Platform,
        '25F': ULX3S_25F_Platform,
        '45F': ULX3S_45F_Platform,
        '85F': ULX3S_85F_Platform
    }

    # Figure out which FPGA variant we want to target...
    parser = argparse.ArgumentParser()
    parser.add_argument('variant', choices=variants.keys())
    args = parser.parse_args()

    platform = variants[args.variant]()
    
    # Add the OLED resource defined above to the platform so we
    # can reference it below.
    platform.add_resources(oled_resource)

    platform.build(ST7789Test(), do_program=True)
