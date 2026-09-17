# Configuration

[Back to README](../README.md) · [Installation](installation.md) · [Tools](tools.md)

## Locating seamly2d.exe

Every tool that shells out to Seamly2D (`render_pattern`, `validate_pattern`)
needs to find `seamly2d.exe`. Detection order:

1. The `--seamly2d-exe` flag passed to the server at startup.
2. `seamly2d` / `seamly2d.exe` on `PATH`.
3. Common Windows install locations:
   - `C:\Program Files (x86)\Seamly2D\seamly2d.exe`
   - `C:\Program Files\Seamly2D\seamly2d.exe`

If none of those apply (a non-standard install location, or a portable copy),
pass the path explicitly:

```bash
uv run seamly2d-mcp --seamly2d-exe "D:\Tools\Seamly2D\seamly2d.exe"
```

Or in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "seamly2d": {
      "command": "uv",
      "args": [
        "--directory",
        "E:/new begin/seamly2d MCP",
        "run",
        "seamly2d-mcp",
        "--seamly2d-exe",
        "D:/Tools/Seamly2D/seamly2d.exe"
      ]
    }
  }
}
```

## Absolute paths matter

`seamly2d.exe`'s CLI does not resolve relative filename arguments against its
own working directory the way most CLIs do -- a relative path silently fails
to open. `cli_bridge.py` resolves every path it hands to the executable to an
absolute path automatically, so this is only relevant if you're calling
`seamly2d.exe` directly outside of this server.

## File-write safety

`update_measurements`, `update_increment`, and `set_pattern_notes` all copy
the original file to `<path>.bak` (overwriting any previous backup of the
same file) before writing. There's no automatic restore tool yet -- if an
edit goes wrong, copy the `.bak` file back over the original manually.

## Known client quirks

Verified live against Claude Desktop:

- **Program Files permissions**: Seamly2D writes a lock file next to any
  pattern file it opens. A pattern living under `C:\Program Files (x86)\...`
  isn't writable by a standard user, so `render_pattern`/`validate_pattern`
  fail there with exit code 66 ("lock file could not be created"). Keep
  working pattern files somewhere normal (Documents, a project folder) --
  this isn't specific to this server, it's how Seamly2D always behaves.
- **Optional parameters may need to be passed explicitly as `null`**: this
  server's JSON Schema is spec-correct (`anyOf: [type, null]`, proper
  `default`, excluded from `required`) -- confirmed by dumping
  `render_pattern`'s schema directly. Some MCP clients' own tool-call
  validation layer flattens that into "must be present," rejecting an
  omitted optional argument even though the server allows it. If a tool call
  fails with an "expected nonoptional, received undefined" style error for
  an argument you didn't set, pass it explicitly as `null` instead of
  omitting it.

## Render output formats

`render_pattern`'s `format` argument accepts: `svg`, `pdf`, `pdf_tiled`,
`png`, `jpg`, `bmp`, `tif`, `ppm`, `obj`, `ps`, `eps`, and DXF variants
(`dxf_r10` through `dxf_2013`, plus `_aama` suffixed versions for AAMA-style
export). See [tools.md](tools.md#render_pattern) for the full mapping to
Seamly2D's `-f` numbers.
