PATTERN_DRAFTING_STRATEGY = """\
Seamly2D pattern-drafting workflow

There is no live connection to a running Seamly2D window -- every tool here
reads or writes .sm2d/.smis/.smms XML files on disk, or shells out to
seamly2d.exe for a one-shot headless export. Follow this order:

1. Find or create the measurement file.
   - list_measurement_files to see what's already there, or
   - read_measurements on an existing .smis/.smms to see current values, or
   - create_measurement_file to start a new individual (.smis) profile from
     body measurements the user gives you. Use Seamly2D's standard
     measurement names (height, neck_circ, bust_circ, waist_circ, hip_circ,
     shoulder_length, etc.) -- read_measurements on a sample file shows the
     naming convention if unsure.

2. Inspect the pattern before changing it.
   - read_pattern to see its description, linked measurement file, current
     increments, and what draft blocks (pieces) it contains.
   - list_increments if you only need the parametric variables.

3. Make measurement or increment changes.
   - update_measurements to change body measurements in place.
   - update_increment to change a pattern's formula-driven variable (e.g.
     ease allowances, drops, widths). Only existing increments can be
     updated -- this never invents a new variable other formulas can't see.
   - Both back up the original file to <path>.bak automatically before
     writing.

4. Validate before showing results.
   - validate_pattern loads the edited file in Seamly2D's silent test mode
     and reports whether it rebuilds without error. Run this after any
     update_increment/update_measurements edit and before rendering, so a
     broken formula is caught before the user sees a failed export.

5. Render to show the user.
   - render_pattern with format="png" for a quick visual the user can see
     inline; use "pdf" or "dxf_*" variants when they want a file to print or
     take to a cutter. Pass mfile explicitly if the pattern's own relative
     measurements path won't resolve outside of Seamly2D's own working
     directory.

6. Tell the user to reopen the file in Seamly2D to see edits in the GUI --
   there is no way to push a live update into an already-open window.
"""
