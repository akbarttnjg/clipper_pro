# Font sources

Bundled files use the SIL Open Font License in the matching `*-OFL.txt` files.

- DM Sans: https://github.com/google/fonts/tree/main/ofl/dmsans — variable font instantiated at weight 600 (default optical size) as DMSans-SemiBold.ttf.
- DM Serif Display: https://github.com/google/fonts/tree/main/ofl/dmserifdisplay — original regular and italic TTFs.
- Montserrat: https://github.com/google/fonts/tree/main/ofl/montserrat — variable font instantiated at weight 700 as Montserrat-Bold.ttf.
- Bebas Neue: https://github.com/google/fonts/tree/main/ofl/bebasneue — original regular TTF.

DM Sans and Montserrat static instances use matching family/subfamily/PostScript name records for consistent local font selection. FontTools is used only when preparing the distribution; it is not a runtime dependency.

Existing DejaVu fonts retain their license in `clipper/fonts/LICENSE-DejaVu.txt`.
