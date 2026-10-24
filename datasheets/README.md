# Documentation

The PDFs are third-party copyrighted documents and are not part of this repository
(`datasheets/*.pdf` is git-ignored). Download them into this folder from the sources below.

| Local file name | Content | Source |
|---|---|---|
| `manual-RND_320_KA3300_mul_man.pdf` | RND 320-KA3305P user manual EN/DE, remote command syntax V5.10 | [Distrelec](https://media.distrelec.com/Web/Downloads/_m/an/RND_320_KA3300_mul_man.pdf) |
| `specs-A700000010994516.pdf` | Datasheet / specifications | [RS Components](https://docs.rs-online.com/0924/A700000010994516.pdf) |
| `safety-A700000010994188.pdf` | Safety booklet (RND lab power supplies) | [RS Components](https://docs.rs-online.com/85a1/A700000010994188.pdf) |
| `calibration-A700000010994092.pdf` | Calibration procedure (front panel) | [RS Components](https://docs.rs-online.com/d9a5/A700000010994092.pdf) |
| `USB Driver installation V3.0.pdf` | USB driver installation guide (not needed on Windows 10/11, the device enumerates as a CDC serial port) | Software ZIP on the [Distrelec product page](https://www.distrelec.ch/en/bench-top-power-supply-30v-5a-150w-programmable-cee-rnd-lab-rnd-320-ka3305p/p/30061865) |
| `manual-KORAD_KA3000_series_V2.0_tameson.pdf` | Korad KA3000 series manual, remote command syntax V2.0 (readable STATUS? table) | [Tameson](https://storage.tameson.com/asset/Products/Manuals/EN/korad_ka3305p_manual.pdf) |
| `commands-RND_320-KAXXXX_V2.0_mikrocontroller.net.pdf` | RND 320-KA single-channel command list V2.0 incl. STATUS? bit table | [mikrocontroller.net](https://mikrocontroller.net/attachment/535122/RND_320-KAXXXX_COMMANDS.pdf) |

Product pages: [RS Components 283-2739](https://uk.rs-online.com/web/p/bench-power-supplies/2832739) ·
[Distrelec 300-61-865](https://www.distrelec.ch/en/bench-top-power-supply-30v-5a-150w-programmable-cee-rnd-lab-rnd-320-ka3305p/p/30061865)
(both list the product as discontinued, links may disappear).

Further references:

- [sigrok wiki: Korad KAxxxxP series](https://sigrok.org/wiki/Korad_KAxxxxP_series) — protocol notes and quirks of the Korad family
- [ManualsLib: RND 320-KA3305P](https://www.manualslib.com/manual/1545686/Rnd-320-Ka3305p.html) — online copy of the user manual

The protocol behaviour actually measured on firmware V4.0 is documented in the main [README](../README.md#findings-on-v40).
