# NameData compile

Aggregates every Unreal **`StringTable`** export whose asset filename matches **`ST_*.json`** under the versioned json tree into one **`NameData.json`**. Use this to look up **localization keys → strings** (item names, quest text, AI display names, region labels, etc.) without opening each source file.

**Wiki / website viewer:** open [`NameData.html`](../../NameData.html) to search tables and copy JSON.

## Output shape

- **`entries`**: keyed by path relative to the json root. Each value has **`parsed`**:
  - **`kind`**: `stringTable` (normal) or `nonStandard` / `unknown` when the first export is not a standard `KeysToEntries` map.
  - **`keysToEntries`**: flat `key → string` for string tables.
  - **`keyCount`**, **`tableNamespace`**, **`exportName`** when applicable.
- **`counts.totalKeys`**: sum of keys across all parsed string tables.
- **`issues.atypicalExports`**: files that did not parse as a standard string table (still listed with a short summary).

## Command

From the repository root (with `website/data.config.json` pointing at your game export):

```bash
python website/tools/NameData/CompileNameData.py
```

Or run the full pipeline:

```bash
python website/tools/compiledata.py
```

Environment overrides match other compilers: `RSDW_JSON_ROOT` or `RSDW_NAME_SOURCE_DIR` to the folder that contains **`RSDragonwilds`**.
