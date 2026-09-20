PATTERN_DRAFTING_STRATEGY = """\
Seamly2D pattern-drafting workflow

0. Decide file-based or live.
   - Most tools here read or write .sm2d/.smis/.smms XML files on disk, or
     shell out to seamly2d.exe for a one-shot headless export -- no Seamly2D
     needs to be running.
   - If a live_* tool exists for what you're doing, and live_ping/live_status
     succeeds, prefer it: it acts on whatever pattern is actually open right
     now (including unsaved edits) and changes appear in the window
     immediately, no reopening the file. Falls back to the file-based tools
     if live_ping fails (no running Seamly2D with the Ribben addon enabled)
     or no live_* equivalent exists yet (rendering is file-only so far --
     see step 6).

1. Find or create the measurement file.
   - list_measurement_files to see what's already there, or
   - read_measurements on an existing .smis/.smms to see current values, or
   - create_measurement_file to start a new individual (.smis) profile from
     body measurements the user gives you. Use Seamly2D's standard
     measurement names (height, neck_circ, bust_circ, waist_circ, hip_circ,
     shoulder_length, etc.) -- read_measurements on a sample file shows the
     naming convention if unsure.

2. Inspect the pattern before changing it.
   - read_pattern (or live_read_pattern) to see its description, linked
     measurement file, current increments, and what draft blocks (pieces) it
     contains.
   - list_increments (or live_list_increments, which also reports each
     increment's currently-computed value and whether its formula is valid)
     if you only need the parametric variables.
   - list_points (or live_list_points) to see what points already exist in a
     draft block, when you're about to extend an existing draft.

3. Make measurement or increment changes.
   - update_measurements to change body measurements in place.
   - update_increment (or live_update_increment) to change a pattern's
     formula-driven variable (e.g. ease allowances, drops, widths). Only
     existing increments can be updated -- this never invents a new variable
     other formulas can't see.
   - File-based writes back up the original file to <path>.bak automatically
     first.

4. Draft new geometry from scratch, when there's no existing draft to edit.
   - create_pattern to start a new file with one empty draft block.
   - add_point_single (or live_add_point_single) at least once, for a
     starting anchor point -- the only point type with no dependencies.
   - Then chain add_point_end_line/add_point_along_line/add_line (each with
     a live_* equivalent) to build up the draft: most manual construction
     steps ("go up 3cm, then right 2cm") are a chain of add_point_end_line
     calls.
   - add_spline (or live_add_spline) for a curved edge between two points
     (Seamly2D's "Curve" tool -- each end takes its own angle+length tangent
     handle) and add_arc (or live_add_arc) for a circular arc around a
     center point.
   - Every add_* call references points by name or id -- use list_points to
     find them (add_spline/add_arc reference by the id they returned).
   - Finally, add_piece (or live_add_piece) to build a seam-allowance
     outline from the points/curves you just drafted -- an ordered, closed
     list of nodes around the boundary (consecutive points imply a straight
     edge; a spline/arc node replaces the edge between its neighbors with
     that curve). This is required before render_pattern will export
     anything from a from-scratch draft -- it refuses an empty scene
     otherwise (render_pattern itself is still file-only). list_pieces (or
     live_list_pieces) shows what's there.

5. Validate before showing results.
   - validate_pattern loads the edited file in Seamly2D's silent test mode
     and reports whether it rebuilds without error. Run this after any
     update_increment/update_measurements edit, and after any add_* geometry
     call, before rendering -- so a broken formula or bad reference is caught
     before the user sees a failed export.

6. Render to show the user.
   - render_pattern with format="png" for a quick visual the user can see
     inline; use "pdf" or "dxf_*" variants when they want a file to print or
     take to a cutter. Pass mfile explicitly if the pattern's own relative
     measurements path won't resolve outside of Seamly2D's own working
     directory. Only works once the draft has at least one piece (step 4) --
     a from-scratch draft with no pieces yet has nothing to export.

7. If you used the file-based tools, tell the user to reopen the file in
   Seamly2D to see the edits in the GUI -- there is no way to push a
   file-based update into an already-open window. If you used the live_*
   tools instead, the open window already reflects the change.
"""
