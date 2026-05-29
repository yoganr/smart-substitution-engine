using System.Text;
using System.Text.Json;

namespace SmartSubstitution.Api.Settings;

/// <summary>
/// Converts PascalCase/camelCase property names to snake_case for JSON serialization.
/// Equivalent to JsonNamingPolicy.SnakeCaseLower (available natively in .NET 8+).
/// </summary>
public class SnakeCaseNamingPolicy : JsonNamingPolicy
{
    public static readonly SnakeCaseNamingPolicy Instance = new();

    public override string ConvertName(string name)
    {
        if (string.IsNullOrEmpty(name)) return name;
        var sb = new StringBuilder(name.Length + 4);
        for (var i = 0; i < name.Length; i++)
        {
            if (char.IsUpper(name[i]) && i > 0)
                sb.Append('_');
            sb.Append(char.ToLowerInvariant(name[i]));
        }
        return sb.ToString();
    }
}
