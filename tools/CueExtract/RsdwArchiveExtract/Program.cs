using System.Text.Encodings.Web;
using System.Text.Json;
using CUE4Parse.Compression;
using CUE4Parse.FileProvider;
using CUE4Parse.FileProvider.Objects;
using CUE4Parse.MappingsProvider;
using CUE4Parse.UE4.Assets;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.ControlRig;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Versions;
using CUE4Parse.Utils;
using CUE4Parse_Conversion.Textures;
using CUE4Parse_Conversion.Textures.BC;
using CUE4Parse_Conversion.UEFormat.Enums;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace RsdwArchiveExtract;

internal static class Program
{
    private static readonly System.Text.Json.JsonSerializerOptions ManifestJsonOptions = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        WriteIndented = true
    };

    private static readonly JsonSerializerSettings ExportJsonSettings = new()
    {
        Formatting = Formatting.Indented,
        ReferenceLoopHandling = ReferenceLoopHandling.Ignore
    };

    private static readonly string[] ExportKeyOrder =
    [
        "Type",
        "Name",
        "Outer",
        "Class",
        "Super",
        "Template",
        "Flags",
        "Properties",
        "SerializedSparseClassDataStruct",
        "SerializedSparseClassData"
    ];

    public static int Main(string[] args)
    {
        try
        {
            var options = CliOptions.Parse(args);
            if (options.ShowHelp)
            {
                PrintHelp();
                return 0;
            }

            options.Validate();
            return Run(options);
        }
        catch (CliException ex)
        {
            Console.Error.WriteLine($"error: {ex.Message}");
            Console.Error.WriteLine("Run with --help for usage.");
            return 2;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return 1;
        }
    }

    private static int Run(CliOptions options)
    {
        var retocRoot = Path.GetFullPath(options.RetocRoot!);
        var usmapPath = Path.GetFullPath(options.Usmap!);
        var outputRoot = options.Output is null ? null : Path.GetFullPath(options.Output);

        Console.WriteLine($"retoc root: {retocRoot}");
        Console.WriteLine($"usmap:      {usmapPath}");
        if (outputRoot is not null) Console.WriteLine($"output:     {outputRoot}");
        Console.WriteLine($"mode:       {(options.DryRun ? "dry-run" : "export")}");

        RegisterArchiveObjectTypes();
        TryInitializeCompression();

        var version = new VersionContainer(EGame.GAME_UE5_6, ETexturePlatform.DesktopMobile);
        var provider = new DefaultFileProvider(retocRoot, SearchOption.AllDirectories, version)
        {
            MappingsContainer = new FileUsmapTypeMappingsProvider(usmapPath)
        };

        Console.WriteLine("initializing CUE4Parse provider...");
        provider.Initialize();
        provider.PostMount();

        var selectors = options.AssetSelectors
            .Select(selector => NormalizeAssetSelector(selector, retocRoot))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var names = options.NameSelectors
            .Select(StripAnyKnownExtension)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        var files = provider.Files.Values
            .Where(IsPackageFile)
            .Where(file => MatchesSelection(file, selectors, names, options.Prefixes))
            .OrderBy(file => file.Path, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var selectionLimit = options.Limit ?? (options.DryRun ? 20 : int.MaxValue);
        if (!options.All && selectionLimit != int.MaxValue)
        {
            files = files.Take(selectionLimit).ToList();
        }

        Console.WriteLine($"registered files: {provider.Files.Count:N0}");
        Console.WriteLine($"selected packages: {files.Count:N0}");

        if (files.Count == 0)
        {
            Console.WriteLine("No packages matched the requested selection.");
            return 0;
        }

        if (options.DryRun)
        {
            foreach (var file in files)
            {
                Console.WriteLine(file.Path);
            }

            return 0;
        }

        Directory.CreateDirectory(outputRoot!);
        CopyUsmap(usmapPath, outputRoot!);

        var results = new List<ArchiveExportResult>();
        var counters = new ArchiveCounters();
        var startedAt = DateTimeOffset.UtcNow;

        foreach (var (file, index) in files.Select((file, index) => (file, index + 1)))
        {
            Console.WriteLine($"[{index}/{files.Count}] {file.Path}");
            var result = ProcessPackage(provider, file, outputRoot!, options.Force);
            counters.Add(result);
            results.Add(result);

            if (result.Succeeded)
            {
                var jsonNote = result.JsonSkipped ? "json skipped" : result.JsonPath is not null ? "json wrote" : "json none";
                var textureNote = result.TextureSkippedCount > 0 || result.TexturePaths.Count > 0
                    ? $"textures wrote {result.TexturePaths.Count}, skipped {result.TextureSkippedCount}"
                    : "textures none";
                Console.WriteLine($"  ok: {jsonNote}; {textureNote}");
            }
            else
            {
                Console.WriteLine($"  failed: {result.Error}");
            }
        }

        var manifestPath = options.Manifest ?? Path.Combine(outputRoot!, "ArchiveExtractManifest.json");
        var manifest = new ArchiveExtractManifest
        {
            StartedAtUtc = startedAt,
            FinishedAtUtc = DateTimeOffset.UtcNow,
            RetocRoot = retocRoot,
            Usmap = usmapPath,
            Output = outputRoot!,
            SelectedPackageCount = files.Count,
            JsonWrittenCount = counters.JsonWritten,
            JsonSkippedCount = counters.JsonSkipped,
            TextureWrittenCount = counters.TextureWritten,
            TextureSkippedCount = counters.TextureSkipped,
            FailedPackageCount = counters.FailedPackages,
            Results = results
        };

        File.WriteAllText(manifestPath, System.Text.Json.JsonSerializer.Serialize(manifest, ManifestJsonOptions));
        Console.WriteLine($"manifest: {manifestPath}");
        Console.WriteLine(
            "done: " +
            $"json wrote {counters.JsonWritten:N0}, json skipped {counters.JsonSkipped:N0}, " +
            $"textures wrote {counters.TextureWritten:N0}, textures skipped {counters.TextureSkipped:N0}, " +
            $"failed {counters.FailedPackages:N0} package(s)");

        return counters.FailedPackages == 0 ? 0 : 1;
    }

    private static ArchiveExportResult ProcessPackage(DefaultFileProvider provider, GameFile file, string outputRoot, bool force)
    {
        var result = new ArchiveExportResult
        {
            PackagePath = NormalizeSeparators(file.Path)
        };

        try
        {
            var package = provider.LoadPackage(file);
            var exports = package.GetExports().ToList();

            var jsonPath = ExpectedJsonPath(outputRoot, file.Path);
            if (!force && File.Exists(jsonPath))
            {
                result.JsonPath = jsonPath;
                result.JsonSkipped = true;
            }
            else
            {
                Directory.CreateDirectory(Path.GetDirectoryName(jsonPath)!);
                File.WriteAllText(jsonPath, SerializeExportsForArchive(exports) + Environment.NewLine);
                result.JsonPath = jsonPath;
            }

            foreach (var textureResult in ExportTextures(outputRoot, file.Path, exports, force))
            {
                if (textureResult.Skipped)
                {
                    result.TextureSkippedCount++;
                }
                else
                {
                    result.TexturePaths.Add(textureResult.Path);
                }
            }

            result.Succeeded = true;
        }
        catch (Exception ex)
        {
            result.Succeeded = false;
            result.Error = ex.ToString();
        }

        return result;
    }

    private static string SerializeExportsForArchive(IReadOnlyCollection<UObject> exports)
    {
        var serializer = Newtonsoft.Json.JsonSerializer.Create(ExportJsonSettings);
        var token = JToken.FromObject(exports, serializer);
        if (token is JArray arr)
        {
            foreach (var child in arr.OfType<JObject>())
            {
                NormalizeExportObject(child);
            }
        }

        return token.ToString(Formatting.Indented);
    }

    private static void NormalizeExportObject(JObject obj)
    {
        obj.Remove("Package");
        var ordered = new JObject();

        foreach (var key in ExportKeyOrder)
        {
            var prop = obj.Property(key);
            if (prop is null) continue;
            prop.Remove();
            ordered.Add(prop);
        }

        foreach (var prop in obj.Properties().ToList())
        {
            if (prop.Name == "Package")
            {
                prop.Remove();
                continue;
            }

            prop.Remove();
            ordered.Add(prop);
        }

        obj.RemoveAll();
        foreach (var prop in ordered.Properties())
        {
            obj.Add(prop);
        }
    }

    private static IEnumerable<TextureExportResult> ExportTextures(
        string outputRoot,
        string packagePath,
        IReadOnlyCollection<UObject> exports,
        bool force)
    {
        foreach (var export in exports)
        {
            if (export is not UTexture texture)
            {
                continue;
            }

            var baseRelative = TextureOutputBaseRelative(packagePath, texture.Name);
            if (!force && texture is not UTexture2DArray)
            {
                var existingSingleTexture = ExistingTexturePath(outputRoot, baseRelative);
                if (existingSingleTexture is not null)
                {
                    yield return new TextureExportResult(existingSingleTexture, true);
                    continue;
                }
            }

            var bitmaps = DecodeTexture(texture);
            if (bitmaps.Count == 0)
            {
                continue;
            }

            for (var i = 0; i < bitmaps.Count; i++)
            {
                var bitmap = bitmaps[i];
                if (bitmap is null)
                {
                    continue;
                }

                var relativeNoExt = bitmaps.Count > 1 ? $"{baseRelative}_{i}" : baseRelative;
                var existing = ExistingTexturePath(outputRoot, relativeNoExt);
                if (!force && existing is not null)
                {
                    yield return new TextureExportResult(existing, true);
                    continue;
                }

                var imageData = bitmap.Encode(ETextureFormat.Png, saveHdrAsHdr: true, out var ext);
                if (string.IsNullOrWhiteSpace(ext) || imageData.Length == 0)
                {
                    continue;
                }

                var outPath = CombineUnderRoot(outputRoot, "textures/" + relativeNoExt + "." + ext);
                Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
                File.WriteAllBytes(outPath, imageData);
                yield return new TextureExportResult(outPath, false);
            }
        }
    }

    private static void RegisterArchiveObjectTypes()
    {
        ObjectTypeRegistry.RegisterClass("RigHierarchy", typeof(SafeRigHierarchy));
    }

    private static List<CTexture?> DecodeTexture(UTexture texture)
    {
        try
        {
            return texture switch
            {
                UTexture2DArray array => (array.DecodeTextureArray(ETexturePlatform.DesktopMobile) ?? []).Cast<CTexture?>().ToList(),
                UTextureCube cube => [cube.Decode(ETexturePlatform.DesktopMobile)?.ToPanorama()],
                _ => [texture.Decode(ETexturePlatform.DesktopMobile)]
            };
        }
        catch (Exception ex)
        {
            Console.WriteLine($"  texture warning: {texture.Name}: {ex.Message}");
            return [];
        }
    }

    private static string? ExistingTexturePath(string outputRoot, string relativeNoExt)
    {
        foreach (var ext in new[] { ".png", ".hdr", ".tga", ".jpg", ".jpeg" })
        {
            var path = CombineUnderRoot(outputRoot, "textures/" + relativeNoExt + ext);
            if (File.Exists(path))
            {
                return path;
            }
        }

        return null;
    }

    private static string ExpectedJsonPath(string outputRoot, string packagePath)
    {
        var relative = StripPackageExtension(NormalizeSeparators(packagePath)).TrimStart('/') + ".json";
        return CombineUnderRoot(outputRoot, "json/" + relative);
    }

    private static string TextureOutputBaseRelative(string packagePath, string exportName)
    {
        var package = StripPackageExtension(NormalizeSeparators(packagePath)).TrimStart('/');
        var packageName = GetAssetName(package);
        if (string.Equals(packageName, exportName, StringComparison.OrdinalIgnoreCase))
        {
            return package;
        }

        var slash = package.LastIndexOf('/');
        return slash >= 0 ? package[..(slash + 1)] + exportName : exportName;
    }

    private static void CopyUsmap(string usmapPath, string outputRoot)
    {
        var dest = CombineUnderRoot(outputRoot, "usmap/" + Path.GetFileName(usmapPath));
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        File.Copy(usmapPath, dest, overwrite: true);
    }

    private static void TryInitializeCompression()
    {
        var detexPath = Path.Combine(AppContext.BaseDirectory, DetexHelper.DLL_NAME);
        if (!File.Exists(detexPath))
        {
            DetexHelper.LoadDll(detexPath);
        }

        if (File.Exists(detexPath))
        {
            DetexHelper.Initialize(detexPath);
        }

        foreach (var directory in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            var oodlePath = Path.Combine(directory, "oo2core_9_win64.dll");
            if (File.Exists(oodlePath))
            {
                OodleHelper.Initialize(oodlePath);
                break;
            }
        }

        foreach (var directory in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            var zlibPath = Path.Combine(directory, "zlib-ng2.dll");
            if (File.Exists(zlibPath))
            {
                ZlibHelper.Initialize(zlibPath);
                break;
            }
        }
    }

    private static bool MatchesSelection(
        GameFile file,
        HashSet<string> assetSelectors,
        HashSet<string> nameSelectors,
        IReadOnlyList<string> prefixes)
    {
        var packagePath = StripPackageExtension(NormalizeSeparators(file.Path));
        var assetName = GetAssetName(packagePath);
        var hasSelectors = assetSelectors.Count > 0 || nameSelectors.Count > 0 || prefixes.Count > 0;

        if (!hasSelectors)
        {
            return true;
        }

        if (assetSelectors.Contains(packagePath))
        {
            return true;
        }

        if (nameSelectors.Contains(assetName))
        {
            return true;
        }

        return prefixes.Any(prefix => assetName.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsPackageFile(GameFile file)
    {
        var path = NormalizeSeparators(file.Path);
        return path.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase) ||
               path.EndsWith(".umap", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizeAssetSelector(string selector, string retocRoot)
    {
        var normalized = NormalizeSeparators(selector.Trim().Trim('"'));

        if (Path.IsPathFullyQualified(normalized))
        {
            var full = Path.GetFullPath(normalized);
            var rel = Path.GetRelativePath(retocRoot, full);
            if (!rel.StartsWith("..", StringComparison.Ordinal))
            {
                normalized = NormalizeSeparators(rel);
            }
        }

        normalized = normalized.TrimStart('/');
        normalized = StripPackageExtension(normalized);

        if (normalized.StartsWith("Game/", StringComparison.OrdinalIgnoreCase))
        {
            return "RSDragonwilds/Content/" + normalized["Game/".Length..];
        }

        if (normalized.StartsWith("Engine/", StringComparison.OrdinalIgnoreCase) &&
            !normalized.StartsWith("Engine/Content/", StringComparison.OrdinalIgnoreCase))
        {
            return "Engine/Content/" + normalized["Engine/".Length..];
        }

        return normalized;
    }

    private static string StripPackageExtension(string path)
    {
        var stripped = StripAnyKnownExtension(path);
        return stripped.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase) ||
               stripped.EndsWith(".umap", StringComparison.OrdinalIgnoreCase)
            ? Path.ChangeExtension(stripped, null) ?? stripped
            : stripped;
    }

    private static string StripAnyKnownExtension(string value)
    {
        foreach (var ext in new[] { ".uasset", ".umap", ".json", ".png", ".hdr" })
        {
            if (value.EndsWith(ext, StringComparison.OrdinalIgnoreCase))
            {
                return value[..^ext.Length];
            }
        }

        return value;
    }

    private static string GetAssetName(string packagePath)
    {
        var normalized = NormalizeSeparators(packagePath);
        var slash = normalized.LastIndexOf('/');
        return slash >= 0 ? normalized[(slash + 1)..] : normalized;
    }

    private static string CombineUnderRoot(string root, string relativePath)
    {
        var localRelative = NormalizeSeparators(relativePath).TrimStart('/').Replace('/', Path.DirectorySeparatorChar);
        var rootFull = Path.GetFullPath(root);
        var combined = Path.GetFullPath(Path.Combine(rootFull, localRelative));

        if (!combined.StartsWith(rootFull.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(combined, rootFull, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"refusing to write outside output root: {relativePath}");
        }

        return combined;
    }

    private static string NormalizeSeparators(string value) => value.Replace('\\', '/');

    private static void PrintHelp()
    {
        Console.WriteLine("""
RSDW Archive CUE4Parse extractor

Usage:
  dotnet run --project tools/CueExtract/RsdwArchiveExtract -- [options]

Required:
  --retoc-root <path>   Root of retoc to-legacy output containing RSDragonwilds and Engine.
  --usmap <path>        Matching RSDragonwilds .usmap file.
  --out <path>          Archive dataset output root. Required unless --dry-run is used.

Selection:
  --asset <path>        Exact package path. Repeatable. /Game/... maps to RSDragonwilds/Content/...
  --name <asset>        Exact asset name, e.g. ITEM_Resources_BluriteOre. Repeatable.
  --prefix <prefixes>   Comma-separated asset prefixes. Empty means no prefix filtering.
  --limit <n>           Maximum selected packages.
  --all                 Export all packages. Required for broad exports without --limit.

Mode:
  --dry-run             Print selected package paths without exporting.
  --force               Re-export existing JSON/textures.
  --manifest <path>     Manifest path. Default: <out>/ArchiveExtractManifest.json.
  --help                Show this help.
""");
    }
}

internal sealed class CliOptions
{
    public string? RetocRoot { get; private set; }
    public string? Usmap { get; private set; }
    public string? Output { get; private set; }
    public string? Manifest { get; private set; }
    public bool DryRun { get; private set; }
    public bool All { get; private set; }
    public bool Force { get; private set; }
    public bool ShowHelp { get; private set; }
    public int? Limit { get; private set; }
    public List<string> AssetSelectors { get; } = [];
    public List<string> NameSelectors { get; } = [];
    public List<string> Prefixes { get; } = [];

    public static CliOptions Parse(string[] args)
    {
        var options = new CliOptions();

        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            switch (arg)
            {
                case "--help":
                case "-h":
                    options.ShowHelp = true;
                    break;
                case "--retoc-root":
                    options.RetocRoot = RequireValue(args, ref i, arg);
                    break;
                case "--usmap":
                    options.Usmap = RequireValue(args, ref i, arg);
                    break;
                case "--out":
                    options.Output = RequireValue(args, ref i, arg);
                    break;
                case "--manifest":
                    options.Manifest = RequireValue(args, ref i, arg);
                    break;
                case "--dry-run":
                    options.DryRun = true;
                    break;
                case "--all":
                    options.All = true;
                    break;
                case "--force":
                    options.Force = true;
                    break;
                case "--asset":
                    options.AssetSelectors.AddRange(SplitCsv(RequireValue(args, ref i, arg)));
                    break;
                case "--name":
                    options.NameSelectors.AddRange(SplitCsv(RequireValue(args, ref i, arg)));
                    break;
                case "--prefix":
                    options.Prefixes.Clear();
                    options.Prefixes.AddRange(SplitCsv(RequireValue(args, ref i, arg)));
                    break;
                case "--limit":
                    var rawLimit = RequireValue(args, ref i, arg);
                    if (!int.TryParse(rawLimit, out var limit) || limit < 1)
                    {
                        throw new CliException("--limit must be a positive integer");
                    }
                    options.Limit = limit;
                    break;
                default:
                    throw new CliException($"unknown option '{arg}'");
            }
        }

        return options;
    }

    public void Validate()
    {
        if (ShowHelp) return;

        if (string.IsNullOrWhiteSpace(RetocRoot)) throw new CliException("--retoc-root is required");
        if (!Directory.Exists(RetocRoot)) throw new CliException($"--retoc-root does not exist: {RetocRoot}");
        if (string.IsNullOrWhiteSpace(Usmap)) throw new CliException("--usmap is required");
        if (!File.Exists(Usmap)) throw new CliException($"--usmap does not exist: {Usmap}");

        if (!DryRun && string.IsNullOrWhiteSpace(Output))
        {
            throw new CliException("--out is required unless --dry-run is used");
        }

        if (!DryRun && !All && Limit is null && AssetSelectors.Count == 0 && NameSelectors.Count == 0)
        {
            throw new CliException("broad export requires --limit, --asset, --name, or --all");
        }
    }

    private static string RequireValue(string[] args, ref int index, string optionName)
    {
        if (index + 1 >= args.Length || args[index + 1].StartsWith("--", StringComparison.Ordinal))
        {
            throw new CliException($"{optionName} requires a value");
        }

        index++;
        return args[index];
    }

    private static IEnumerable<string> SplitCsv(string value)
    {
        return value
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(item => item.Length > 0);
    }
}

internal sealed class CliException(string message) : Exception(message);

internal sealed class TextureExportResult(string path, bool skipped)
{
    public string Path { get; } = path;
    public bool Skipped { get; } = skipped;
}

internal sealed class ArchiveExportResult
{
    public required string PackagePath { get; init; }
    public bool Succeeded { get; set; }
    public string? Error { get; set; }
    public string? JsonPath { get; set; }
    public bool JsonSkipped { get; set; }
    public List<string> TexturePaths { get; init; } = [];
    public int TextureSkippedCount { get; set; }
}

internal sealed class ArchiveCounters
{
    public int JsonWritten { get; private set; }
    public int JsonSkipped { get; private set; }
    public int TextureWritten { get; private set; }
    public int TextureSkipped { get; private set; }
    public int FailedPackages { get; private set; }

    public void Add(ArchiveExportResult result)
    {
        if (!result.Succeeded)
        {
            FailedPackages++;
            return;
        }

        if (result.JsonSkipped)
        {
            JsonSkipped++;
        }
        else if (result.JsonPath is not null)
        {
            JsonWritten++;
        }

        TextureWritten += result.TexturePaths.Count;
        TextureSkipped += result.TextureSkippedCount;
    }
}

internal sealed class ArchiveExtractManifest
{
    public DateTimeOffset StartedAtUtc { get; init; }
    public DateTimeOffset FinishedAtUtc { get; init; }
    public required string RetocRoot { get; init; }
    public required string Usmap { get; init; }
    public required string Output { get; init; }
    public int SelectedPackageCount { get; init; }
    public int JsonWrittenCount { get; init; }
    public int JsonSkippedCount { get; init; }
    public int TextureWrittenCount { get; init; }
    public int TextureSkippedCount { get; init; }
    public int FailedPackageCount { get; init; }
    public List<ArchiveExportResult> Results { get; init; } = [];
}

internal class SafeRigHierarchy : URigHierarchy
{
    protected override void WriteJson(JsonWriter writer, Newtonsoft.Json.JsonSerializer serializer)
    {
        WriteBaseObjectJson(writer, serializer);

        if (Elements is { Length: > 0 })
        {
            writer.WritePropertyName(nameof(Elements));
            serializer.Serialize(writer, Elements);
        }
    }

    private void WriteBaseObjectJson(JsonWriter writer, Newtonsoft.Json.JsonSerializer serializer)
    {
        writer.WritePropertyName("Type");
        writer.WriteValue(ExportType);

        writer.WritePropertyName(nameof(Name));
        writer.WriteValue(Name);

        writer.WritePropertyName(nameof(Flags));
        writer.WriteValue(Flags.ToStringBitfield());

        if (Class is { Object.Value: { } clas })
        {
            writer.WritePropertyName(nameof(Class));
            writer.WriteValue(clas.GetFullName());
        }

        if (Outer is not null && Outer is not ResolvedPackageObject)
        {
            writer.WritePropertyName(nameof(Outer));
            serializer.Serialize(writer, Outer);
        }
        else if (Owner is not null)
        {
            writer.WritePropertyName("Package");
            writer.WriteValue(Owner.Name);
        }

        if (Super != null)
        {
            writer.WritePropertyName(nameof(Super));
            serializer.Serialize(writer, Super);
        }

        if (Template != null)
        {
            writer.WritePropertyName(nameof(Template));
            serializer.Serialize(writer, Template);
        }

        if (Properties.Count > 0)
        {
            writer.WritePropertyName(nameof(Properties));
            writer.WriteStartObject();
            foreach (var property in Properties)
            {
                writer.WritePropertyName(property.ArrayIndex > 0 ? $"{property.Name.Text}[{property.ArrayIndex}]" : property.Name.Text);
                serializer.Serialize(writer, property.Tag);
            }
            writer.WriteEndObject();
        }

        if (SerializedSparseClassDataStruct != null)
        {
            writer.WritePropertyName(nameof(SerializedSparseClassDataStruct));
            writer.WriteValue(SerializedSparseClassDataStruct.GetFullName());

            writer.WritePropertyName(nameof(SerializedSparseClassData));
            serializer.Serialize(writer, SerializedSparseClassData);
        }
    }
}
